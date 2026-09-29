"""
Counterparty web footprint via Similarweb.

Shell forwarders and front consignees used in diversion schemes often have a website
with almost no real traffic, or traffic concentrated in a sanctioned jurisdiction. A
new shell is not on any sanctions list yet, so this adds an independent signal.

For each party with a website in the manifest (`consignee_website`, `notify_party_website`,
..., or a `websites` map {party: domain}) it reads monthly visits and traffic by country,
and applies fixed, configurable thresholds. The output is a due-diligence LEAD for a human
to review, never a finding: low traffic alone proves nothing.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
from pathlib import Path

from .base import ROOT, Bulletin, Context, read_text, secret

PARTY_FIELDS = ("shipper", "consignee", "notify_party", "forwarder", "end_user")
VISITS_URL = ("{base}/v1/website/{domain}/total-traffic-and-engagement/visits"
              "?country=world&granularity=monthly&main_domain_only=false")
GEO_URL = "{base}/v4/website/{domain}/geo/total-traffic-by-country?main_domain_only=false"
LEAD = "A due-diligence lead for review, not a finding."


def normalize_domain(value: str) -> str:
    """'https://www.Example.com/about' -> 'example.com'"""
    d = str(value).strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split("?")[0].split(":")[0]
    return d[4:] if d.startswith("www.") else d


def party_websites(manifest: dict) -> list[tuple[str, str, str]]:
    """(party name, domain, manifest field) for every party that has a website on file."""
    out, seen = [], set()
    for field in PARTY_FIELDS:
        site, party = manifest.get(f"{field}_website"), manifest.get(field)
        if site:
            out.append((str(party or field).split(",")[0].strip(), normalize_domain(site), f"manifest.{field}"))
    for party, site in (manifest.get("websites") or {}).items():
        out.append((str(party), normalize_domain(site), "manifest.websites"))
    return [p for p in out if p[1] and not (p[1] in seen or seen.add(p[1]))]


class SimilarwebSource:
    def __init__(self, name: str = "Similarweb web footprint", api_key_env: str = "SIMILARWEB_API_KEY",
                 base_url: str = "https://api.similarweb.com", visits_url: str = VISITS_URL,
                 geo_url: str = GEO_URL, sample_dir: str | None = None, min_monthly_visits: float = 1000,
                 watch_share: float = 0.3, watch_countries: dict | None = None, **_):
        self.name, self.base = name, base_url.rstrip("/")
        self.visits_url, self.geo_url = visits_url, geo_url
        self.key = None if sample_dir else secret(api_key_env)
        self.key_env, self.sample_dir = api_key_env, sample_dir
        self.min_visits, self.watch_share = float(min_monthly_visits), float(watch_share)
        # ISO 3166-1 numeric code -> name, as Similarweb reports countries
        self.watch = {int(k): v for k, v in (watch_countries or {}).items()}

    # -------------------------------------------------------------- data access
    def _sample(self, kind: str, domain: str) -> Path:
        p = Path(self.sample_dir) / f"{domain}.{kind}.json"
        return p if p.is_absolute() else ROOT / p

    def _get(self, kind: str, domain: str) -> dict | None:
        """Parsed response, or None when Similarweb has no data for the domain."""
        if self.sample_dir:
            p = self._sample(kind, domain)
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        if not self.key:
            raise RuntimeError(f"no API key (set {self.key_env})")
        url = (self.visits_url if kind == "visits" else self.geo_url).format(
            base=self.base, domain=urllib.parse.quote(domain))
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"api_key": self.key})
        try:
            return json.loads(read_text(url, ttl_s=24 * 3600))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):  # Similarweb answers unknown / too-small domains this way
                return None
            raise RuntimeError(f"Similarweb HTTP {exc.code}") from None  # never echo the URL: it holds the key

    @staticmethod
    def avg_visits(data: dict | None) -> float | None:
        vals = [float(v["visits"]) for v in (data or {}).get("visits") or [] if v.get("visits") is not None]
        return sum(vals) / len(vals) if vals else None

    @staticmethod
    def top_country(data: dict | None) -> dict | None:
        recs = [r for r in (data or {}).get("records") or [] if r.get("share") is not None]
        return max(recs, key=lambda r: float(r["share"])) if recs else None

    # -------------------------------------------------------------- rules
    def fetch(self, ctx: Context) -> list[Bulletin]:
        out = []
        for party, domain, where in party_websites(ctx.manifest):
            if self.sample_dir and not self._sample("visits", domain).exists():
                continue  # not in the sample dataset: only the live API can speak for real domains
            page = f"https://www.similarweb.com/website/{domain}/"

            def flag(severity: str, text: str, **extra):
                out.append(Bulletin(source=self.name, category="Counterparty", severity=severity,
                                    text=f"'{party}' ({where}), website {domain}: {text} {LEAD}",
                                    url=page, extra={"party": party, "domain": domain, **extra}))

            visits = self.avg_visits(self._get("visits", domain))
            if visits is None:
                flag("MEDIUM", "no measurable web traffic in Similarweb data.")
                continue
            if visits < self.min_visits:
                flag("HIGH", f"negligible web footprint, ~{visits:,.0f} visits/month "
                             f"(threshold {self.min_visits:,.0f}); consistent with a shell or front company.",
                     visits=visits)
            top = self.top_country(self._get("geo", domain))
            if top and int(top.get("country", -1)) in self.watch and float(top["share"]) >= self.watch_share:
                flag("HIGH", f"{float(top['share']):.0%} of web traffic comes from "
                             f"{self.watch[int(top['country'])]}, a sanctioned jurisdiction.",
                     top_country=top)
        return out
