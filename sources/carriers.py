"""
Carrier schedules and rates -> the candidate route library the agents choose from.

  * RouteCSVSource       - your own route library / rate sheet (one row per option)
  * DCSAScheduleSource   - carriers exposing the DCSA Commercial Schedules standard
                           (point-to-point routings), priced from a rate sheet CSV

A route dict:
  {id, name, via[], transit_days, est_cost_usd, notes, carrier, parties[], legs[{mode, pts}]}
"""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse
from datetime import datetime

from .base import dig, read_text, secret
from .geo import find_place, legs_from_via

_MODE = {"VESSEL": "sea", "BARGE": "sea", "FEEDER": "sea", "RAIL": "land", "TRUCK": "land",
         "ROAD": "land", "AIR": "air", "sea": "sea", "rail": "land", "truck": "land", "land": "land", "air": "air"}


def _same_place(a: str, b: str) -> bool:
    pa, pb = find_place(a.split("(")[0]), find_place(b.split("(")[0])
    if pa and pb:
        return pa["name"] == pb["name"]
    return a.split(",")[0].strip().lower() in b.lower() or b.split(",")[0].strip().lower() in a.lower()


def _num(v) -> int | None:
    try:
        return int(float(re.sub(r"[^\d.]", "", str(v)))) if str(v).strip() else None
    except ValueError:
        return None


class RateSheet:
    """CSV: origin, destination, key (route_id or service name), est_cost_usd"""

    def __init__(self, url: str | None):
        self.rows = list(csv.DictReader(io.StringIO(read_text(url)))) if url else []

    def price(self, origin: str, destination: str, key: str) -> int | None:
        for r in self.rows:
            if r.get("key", "").strip().lower() == key.lower() and _same_place(r["origin"], origin) \
                    and _same_place(r["destination"], destination):
                return _num(r.get("est_cost_usd"))
        return None


class RouteCSVSource:
    """CSV columns: route_id, origin, destination, name, via (|-sep), modes (|-sep per segment),
    transit_days, est_cost_usd, carrier, parties (|-sep), notes"""

    def __init__(self, name: str, url: str, **_):
        self.name, self.url = name, url

    def routes(self, manifest: dict) -> dict:
        out = {}
        for r in csv.DictReader(io.StringIO(read_text(self.url))):
            if not (_same_place(r["origin"], str(manifest.get("origin", "")))
                    and _same_place(r["destination"], str(manifest.get("destination", "")))):
                continue
            via = [v.strip() for v in r["via"].split("|") if v.strip()]
            modes = [m.strip() for m in (r.get("modes") or "").split("|") if m.strip()] or None
            out[r["route_id"]] = {
                "id": r["route_id"], "name": r["name"], "via": via,
                "transit_days": _num(r.get("transit_days")), "est_cost_usd": _num(r.get("est_cost_usd")),
                "notes": r.get("notes", ""), "carrier": r.get("carrier", ""),
                "parties": [p.strip() for p in (r.get("parties") or "").split("|") if p.strip()],
                "legs": legs_from_via(via, modes), "source": self.name,
            }
        return out


class DCSAScheduleSource:
    """DCSA Commercial Schedules 'point-to-point routes'. `url` is the carrier's base URL
    (or a saved JSON response). Costs come from `rate_sheet`."""

    def __init__(self, name: str, url: str, api_key_env: str | None = None,
                 api_key_header: str = "Authorization", rate_sheet: str | None = None,
                 max_options: int = 4, **_):
        self.name, self.url, self.max_options = name, url, max_options
        self.headers = {api_key_header: secret(api_key_env)} if secret(api_key_env) else {}
        self.rates = RateSheet(rate_sheet)

    def _query_url(self, manifest: dict) -> str:
        if not self.url.startswith("http"):
            return self.url  # saved response file
        o, d = find_place(str(manifest.get("origin", ""))), find_place(str(manifest.get("destination", "")))
        q = {"placeOfReceipt": (o or {}).get("code", ""), "placeOfDelivery": (d or {}).get("code", "")}
        return f"{self.url.rstrip('/')}/point-to-point-routes?{urllib.parse.urlencode(q)}"

    def routes(self, manifest: dict) -> dict:
        data = json.loads(read_text(self._query_url(manifest), self.headers))
        options = data if isinstance(data, list) else data.get("routings") or data.get("results") or []
        origin, dest = str(manifest.get("origin", "")), str(manifest.get("destination", ""))

        def _end(opt, key):
            return str(dig(opt, f"{key}.location.UNLocationCode") or dig(opt, f"{key}.location.locationName") or "")

        options = [o for o in options
                   if not _end(o, "placeOfReceipt") or (_same_place(_end(o, "placeOfReceipt"), origin)
                                                        and _same_place(_end(o, "placeOfDelivery"), dest))]
        out = {}
        for i, opt in enumerate(options[: self.max_options], start=1):
            legs = opt.get("legs") or []
            via, modes = [], []
            for leg in legs:
                dep = dig(leg, "departure.location.UNLocationCode") or dig(leg, "departure.location.locationName")
                arr = dig(leg, "arrival.location.UNLocationCode") or dig(leg, "arrival.location.locationName")
                if dep and (not via or via[-1] != dep):
                    via.append(dep)
                if arr:
                    via.append(arr)
                modes.append(_MODE.get(str(dig(leg, "transport.modeOfTransport", "VESSEL")).upper(), "sea"))
            names = [dig(leg, "transport.servicePartners.0.carrierServiceName") or
                     dig(leg, "transport.carrierServiceName") for leg in legs]
            svc = " / ".join(dict.fromkeys(n for n in names if n)) or f"Option {i}"
            carrier = dig(legs[0], "transport.servicePartners.0.carrierCode", "") if legs else ""
            days = opt.get("transitTime")
            if days is None and legs:
                try:
                    t0 = datetime.fromisoformat(str(dig(legs[0], "departure.dateTime")).replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(str(dig(legs[-1], "arrival.dateTime")).replace("Z", "+00:00"))
                    days = (t1 - t0).days
                except Exception:
                    days = None
            rid = f"DCSA_{i}"
            via_names = [(find_place(v) or {}).get("name", v) for v in via]
            out[rid] = {
                "id": rid, "name": svc, "via": via_names, "transit_days": _num(days),
                "est_cost_usd": self.rates.price(str(manifest.get("origin", "")),
                                                 str(manifest.get("destination", "")), svc),
                "notes": f"{len(legs)} legs via DCSA schedule", "carrier": carrier, "parties": [],
                "legs": legs_from_via(via, modes), "source": self.name,
            }
        return out
