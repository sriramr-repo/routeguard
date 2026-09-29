"""
Export controls.

  * ExportControlRulesSource - your control-list mapping (HS-code prefixes and/or cargo
                               keywords -> control code, regime, licence rule). Seed it
                               from the EU dual-use Annex I / US Commerce Control List
                               with your classification team.
  * TradeGovCSLSource        - US Consolidated Screening List API (data.trade.gov):
                               screens every shipment party across the US export-control
                               lists (Entity List, Denied Persons, Unverified, MEU, SDN...).
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse

from .base import Bulletin, Context, read_text, secret
from .geo import find_place
from .sanctions import shipment_parties


def _hs_code(manifest: dict) -> str:
    hs = str(manifest.get("hs_code") or "")
    if not hs:
        m = re.search(r"HS\s*([0-9][0-9.]{3,})", str(manifest.get("cargo", "")), re.I)
        hs = m.group(1) if m else ""
    return re.sub(r"\D", "", hs)


def _dest_country(manifest: dict) -> str:
    if manifest.get("destination_country"):
        return str(manifest["destination_country"]).upper()
    pl = find_place(str(manifest.get("destination", "")).split("(")[0])
    if pl:
        return pl["country"]
    m = re.search(r",\s*([A-Z]{2})\b", str(manifest.get("destination", "")))
    return m.group(1) if m else ""


def _licence_on_file(manifest: dict) -> bool:
    v = str(manifest.get("export_licence") or manifest.get("export_license") or "").strip().lower()
    return bool(v) and not v.startswith(("none", "no ", "n/a", "not ")) and v not in ("no", "false", "-")


class ExportControlRulesSource:
    """CSV columns: hs_prefix, keywords (|-separated), control_code, regime, licence_required,
    destinations (ISO-2 |-separated, or * for all), note."""

    def __init__(self, name: str, url: str, **_):
        self.name, self.url = name, url

    def rules(self) -> list[dict]:
        return list(csv.DictReader(io.StringIO(read_text(self.url))))

    def fetch(self, ctx: Context) -> list[Bulletin]:
        m = ctx.manifest
        hs, cargo = _hs_code(m), str(m.get("cargo", "")).lower()
        dest = _dest_country(m)
        out, seen = [], set()
        for r in self.rules():
            pref = re.sub(r"\D", "", r.get("hs_prefix") or "")
            kws = [k.strip().lower() for k in (r.get("keywords") or "").split("|") if k.strip()]
            hs_hit = bool(pref) and hs.startswith(pref)
            kw_hit = any(k in cargo for k in kws)
            if not (hs_hit or kw_hit):
                continue
            dests = [d.strip().upper() for d in (r.get("destinations") or "*").split("|")]
            if "*" not in dests and dest not in dests:
                continue
            code = (r.get("control_code") or "").strip()
            if code in seen:
                continue
            seen.add(code)
            licensed = _licence_on_file(m)
            required = (r.get("licence_required") or "yes").strip().lower() in ("yes", "true", "1", "always")
            sev = "CRITICAL" if required and not licensed else "HIGH" if required else "MEDIUM"
            state = ("no export licence on file" if not licensed
                     else f"licence on file ({m.get('export_licence')}); confirm it covers this item and end user")
            out.append(Bulletin(
                source=self.name, category="Export Control", severity=sev,
                text=(f"Cargo matches {r.get('regime', '')} control {r.get('control_code', '')} "
                      f"({'HS ' + pref if hs_hit else 'keyword'}), destination {dest or 'unknown'}: "
                      f"{'licence required' if required else 'check licence requirement'}; {state}. "
                      f"{r.get('note', '')}").strip(),
                extra={"rule": r}))
        return out


class TradeGovCSLSource:
    """US Consolidated Screening List. Needs a free subscription key from developer.trade.gov."""

    ENDPOINT = "https://data.trade.gov/consolidated_screening_list/v1/search"

    def __init__(self, name: str = "US Consolidated Screening List", api_key_env: str = "TRADE_GOV_API_KEY",
                 min_score: float = 90, **_):
        self.name, self.key, self.min_score = name, secret(api_key_env), min_score

    def fetch(self, ctx: Context) -> list[Bulletin]:
        if not self.key:
            raise RuntimeError("no API key (set TRADE_GOV_API_KEY)")
        out = []
        for party, where in shipment_parties(ctx.manifest, ctx.routes):
            q = urllib.parse.urlencode({"name": party, "fuzzy_name": "true"})
            data = json.loads(read_text(f"{self.ENDPOINT}?{q}", {"subscription-key": self.key}, ttl_s=6 * 3600))
            for hit in (data.get("results") or [])[:3]:
                score = float(hit.get("score") or 100)
                if score < self.min_score:
                    continue
                out.append(Bulletin(
                    source=self.name, category="Export Control",
                    severity="CRITICAL" if score >= 98 else "HIGH",
                    text=(f"'{party}' ({where}) matches '{hit.get('name')}' on {hit.get('source', 'CSL')}"
                          f" (score {score:.0f}; programs: {', '.join(hit.get('programs') or []) or 'n/a'})."),
                    url=hit.get("source_list_url", ""), extra={"hit": hit}))
        return out
