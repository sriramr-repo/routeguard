"""
Sanctions screening.

  * SanctionsListSource  - loads a published list (OFAC SDN, EU consolidated, UK)
                           and screens every party in the shipment and on each route
  * CountryEmbargoSource - flags routes that call at ports in jurisdictions you
                           configure as comprehensively sanctioned

Screening here is a transparent, deterministic name match. It surfaces hits and
near-misses for the agents and a human; it is NOT a substitute for your
compliance team's screening provider.
"""

from __future__ import annotations

import csv
import io
import re
from difflib import SequenceMatcher

from .base import Bulletin, Context, read_text
from .geo import find_place

_SUFFIXES = {"llc", "ltd", "limited", "inc", "co", "corp", "company", "fze", "fzco", "fz", "llp",
             "gmbh", "ag", "sa", "sas", "srl", "spa", "bv", "nv", "jsc", "pjsc", "ojsc", "plc",
             "the", "and", "of", "trading", "group", "holding", "holdings"}


def normalize(name: str) -> str:
    toks = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return " ".join(t for t in toks if t not in _SUFFIXES)


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    jacc = len(ta & tb) / len(ta | tb)
    return max(jacc, SequenceMatcher(None, na, nb).ratio())


# ------------------------------------------------------------------ list parsers
# Each returns list of {"name", "program", "type"}

def _parse_ofac_sdn(text: str) -> list[dict]:
    # OFAC SDN.CSV: no header. ent_num, SDN_Name, SDN_Type, Program, Title, Call_Sign, ...
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) >= 4 and r[1].strip() and r[1].strip() != "-0-":
            rows.append({"name": r[1].strip(), "type": r[2].strip().strip("-0-"),
                         "program": r[3].strip()})
    return rows


def _parse_uk(text: str) -> list[dict]:
    # UK consolidated list CSV: a 'Last Updated' line, then a header with Name 1..Name 6.
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if "Name 6" in l or l.lower().startswith("name")), 0)
    rows = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        if "Name 6" in r:
            name = " ".join(filter(None, (r.get(f"Name {i}", "").strip() for i in (1, 2, 3, 4, 5, 6))))
        else:
            name = (r.get("Name") or r.get("name") or "").strip()
        if name:
            rows.append({"name": name, "type": (r.get("Group Type") or "").strip(),
                         "program": (r.get("Regime") or r.get("Regime Name") or "UK").strip()})
    return rows


def _parse_eu(text: str) -> list[dict]:
    # EU Financial Sanctions Files (FSF) CSV: ';'-separated, one row per alias.
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    name_col = next((c for c in reader.fieldnames or [] if "WholeName" in c), None)
    prog_col = next((c for c in reader.fieldnames or [] if "Programme" in c), None)
    type_col = next((c for c in reader.fieldnames or [] if "SubjectType" in c and "Code" in c), None)
    rows = []
    for r in reader:
        name = (r.get(name_col) or "").strip() if name_col else ""
        if name:
            rows.append({"name": name, "program": (r.get(prog_col) or "EU").strip() if prog_col else "EU",
                         "type": (r.get(type_col) or "").strip() if type_col else ""})
    return rows


def _parse_generic(text: str, name_column="name", program_column="program", delimiter=",") -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text), delimiter=delimiter):
        if (r.get(name_column) or "").strip():
            rows.append({"name": r[name_column].strip(), "program": (r.get(program_column) or "").strip(),
                         "type": ""})
    return rows


PARSERS = {"ofac_sdn_csv": _parse_ofac_sdn, "uk_csv": _parse_uk, "eu_fsf_csv": _parse_eu,
           "generic_csv": _parse_generic}


def shipment_parties(manifest: dict, routes: dict) -> list[tuple[str, str]]:
    """(party name, where it came from). Includes route operators/terminals if listed."""
    out = []
    for field in ("shipper", "consignee", "notify_party", "forwarder", "carrier", "end_user"):
        v = manifest.get(field)
        if v:
            out.append((str(v).split(",")[0].strip(), f"manifest.{field}"))
    for p in manifest.get("parties", []) or []:
        out.append((str(p), "manifest.parties"))
    for r in routes.values():
        for p in r.get("parties", []) or []:
            out.append((p, f"route {r['id']}"))
        if r.get("carrier"):
            out.append((r["carrier"], f"route {r['id']} carrier"))
    return out


class SanctionsListSource:
    def __init__(self, name: str, url: str, format: str = "ofac_sdn_csv", hit_threshold: float = 0.9,
                 review_threshold: float = 0.78, parser_options: dict | None = None, **_):
        self.name, self.url, self.format = name, url, format
        self.hit, self.review = hit_threshold, review_threshold
        self.opts = parser_options or {}
        self._entries: list[dict] | None = None

    def entries(self) -> list[dict]:
        if self._entries is None:
            self._entries = PARSERS[self.format](read_text(self.url, ttl_s=6 * 3600), **self.opts)
        return self._entries

    def fetch(self, ctx: Context) -> list[Bulletin]:
        out = []
        entries = self.entries()
        for party, where in shipment_parties(ctx.manifest, ctx.routes):
            best, score = None, 0.0
            for e in entries:
                s = similarity(party, e["name"])
                if s > score:
                    best, score = e, s
            if not best or score < self.review:
                continue
            exact = score >= self.hit
            out.append(Bulletin(
                source=self.name, category="Sanctions", severity="CRITICAL" if exact else "HIGH",
                text=(f"{'Match' if exact else 'Possible match (needs review)'}: '{party}' ({where}) vs listed "
                      f"'{best['name']}' [{best['program'] or 'program n/a'}], similarity {score:.2f}."),
                extra={"party": party, "where": where, "listed": best, "score": score}))
        return out


class CountryEmbargoSource:
    """Flags any candidate route calling at a port in a configured jurisdiction (ISO-2)."""

    def __init__(self, name: str, countries: dict | list, **_):
        self.name = name
        # {"IR": "US OFAC Iran program; EU/UK restrictive measures"} or ["IR", ...]
        self.countries = countries if isinstance(countries, dict) else {c: "configured embargo" for c in countries}

    def fetch(self, ctx: Context) -> list[Bulletin]:
        out = []
        for r in ctx.routes.values():
            for tok in r.get("via", []):
                pl = find_place(tok)
                if pl and pl["country"] in self.countries:
                    out.append(Bulletin(
                        source=self.name, category="Sanctions", severity="CRITICAL",
                        text=(f"Route {r['id']} passes through {pl['name']} ({pl['country']}), a jurisdiction under "
                              f"{self.countries[pl['country']]}."),
                        location=pl["name"], lat=pl["lat"], lon=pl["lon"]))
        dest = find_place(str(ctx.manifest.get("destination", "")))
        if dest and dest["country"] in self.countries:
            out.append(Bulletin(source=self.name, category="Sanctions", severity="CRITICAL",
                                text=f"Destination {dest['name']} is in {dest['country']}: {self.countries[dest['country']]}.",
                                location=dest["name"], lat=dest["lat"], lon=dest["lon"]))
        return out
