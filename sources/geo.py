"""
Geography helpers: port lookup (UN/LOCODE), maritime chokepoints, route geometry,
and matching free-text bulletins to places on a candidate route.

The port table is a starter set of major ports; extend data/ports.csv as needed.
"""

from __future__ import annotations

import csv
import math
import re
from functools import lru_cache

from .base import ROOT

# name, lat, lon, text aliases (lower-case regex fragments)
CHOKEPOINTS = {
    "Suez Canal":         (30.50, 32.35, r"suez|port said|great bitter lake"),
    "Bab el-Mandeb":      (12.60, 43.30, r"bab[\s-]?(el|al)[\s-]?mandeb|bab[\s-]?al[\s-]?mandab"),
    "Red Sea":            (20.00, 38.50, r"red sea"),
    "Gulf of Aden":       (12.50, 47.00, r"gulf of aden"),
    "Strait of Hormuz":   (26.50, 56.40, r"hormuz"),
    "Gulf of Oman":       (24.50, 58.50, r"gulf of oman"),
    "Strait of Malacca":  (2.50, 101.50, r"malacca|singapore strait"),
    "Panama Canal":       (9.10, -79.70, r"panama canal|gat[uú]n|miraflores|cristobal|crist[oó]bal|balboa"),
    "Cape of Good Hope":  (-35.50, 20.00, r"cape of good hope|cape route|agulhas"),
    "Strait of Gibraltar": (36.00, -5.60, r"gibraltar"),
    "Bosporus":           (41.10, 29.05, r"bosp[ho]*rus|istanbul strait|dardanelles|turkish straits"),
    "Black Sea":          (43.00, 34.00, r"black sea"),
    "Caspian Sea":        (41.50, 50.50, r"caspian|alat|aktau|turkmenbashi"),
    "Taiwan Strait":      (24.00, 119.50, r"taiwan strait"),
    "English Channel":    (50.50, 0.00, r"english channel|dover strait"),
    "Gulf of Guinea":     (2.00, 3.00, r"gulf of guinea"),
}


@lru_cache(maxsize=1)
def ports() -> dict[str, dict]:
    """UN/LOCODE -> {code, name, country, lat, lon, aliases[]}"""
    out = {}
    with open(ROOT / "data" / "ports.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            aliases = [a.strip().lower() for a in (row.get("aliases") or "").split("|") if a.strip()]
            code = (row.get("locode") or "").strip().upper()
            out[code or row["name"].strip().upper()] = {
                "code": code, "name": row["name"].strip(),
                "country": row["country"].strip().upper(),
                "lat": float(row["lat"]), "lon": float(row["lon"]),
                "aliases": [row["name"].strip().lower(), *aliases],
            }
    return out


def find_place(token: str) -> dict | None:
    """Resolve a port LOCODE, port name/alias, or chokepoint name to a place dict."""
    t = token.strip()
    if not t:
        return None
    p = ports()
    if t.upper().replace(" ", "") in p:
        return p[t.upper().replace(" ", "")]
    tl = t.lower()
    for port in p.values():
        if tl in port["aliases"] or tl.split(",")[0].strip() in port["aliases"]:
            return port
    for name, (lat, lon, rx) in CHOKEPOINTS.items():
        if tl == name.lower() or re.search(rx, tl):
            return {"code": "", "name": name, "country": "", "lat": lat, "lon": lon, "aliases": [name.lower()]}
    return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _densify(pts: list[tuple[float, float]], step_deg: float = 2.0):
    for (a, b) in zip(pts, pts[1:]):
        n = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) / step_deg))
        for i in range(n):
            yield (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)
    if pts:
        yield pts[-1]


def route_points(route: dict) -> list[tuple[float, float]]:
    return [p for leg in route.get("legs", []) for p in leg["pts"]]


def chokepoints_on_route(route: dict, radius_km: float = 350) -> list[str]:
    pts = list(_densify(route_points(route)))
    hits = []
    for name, (lat, lon, _) in CHOKEPOINTS.items():
        if any(haversine_km((lat, lon), p) <= radius_km for p in pts):
            hits.append(name)
    return hits


def places_for_routes(routes: dict) -> dict[str, tuple[float, float, str]]:
    """Every named place relevant to any candidate route: name -> (lat, lon, regex)."""
    out: dict[str, tuple[float, float, str]] = {}
    for r in routes.values():
        for cp in chokepoints_on_route(r):
            lat, lon, rx = CHOKEPOINTS[cp]
            out[cp] = (lat, lon, rx)
        for tok in r.get("via", []):
            pl = find_place(tok)
            if pl and pl["name"] not in out:
                rx = "|".join(re.escape(a) for a in pl["aliases"] if len(a) > 3)
                if rx:
                    out[pl["name"]] = (pl["lat"], pl["lon"], rx)
    return out


def match_location(text: str, places: dict[str, tuple[float, float, str]]):
    """Return (name, lat, lon) of the first route-relevant place mentioned in text, else None."""
    t = text.lower()
    for name, (lat, lon, rx) in places.items():
        if re.search(rf"(?<![a-z])({rx})(?![a-z])", t):
            return name, lat, lon
    return None


def legs_from_via(via: list[str], modes: list[str] | None = None) -> list[dict]:
    """Build map legs from an ordered list of ports/chokepoints; consecutive equal modes merge."""
    pts = []
    for tok in via:
        pl = find_place(tok)
        if pl:
            pts.append((pl["lat"], pl["lon"]))
    if len(pts) < 2:
        return []
    from .sealanes import sea_path

    modes = modes or ["sea"] * (len(pts) - 1)
    legs: list[dict] = []
    for i in range(len(pts) - 1):
        m = modes[i] if i < len(modes) else modes[-1]
        seg = sea_path(pts[i], pts[i + 1]) if m == "sea" else [pts[i], pts[i + 1]]
        if legs and legs[-1]["mode"] == m:
            legs[-1]["pts"].extend(seg[1:])
        else:
            legs.append({"mode": m, "pts": seg})
    return legs


def map_center(routes: dict) -> dict:
    pts = [p for r in routes.values() for p in route_points(r)]
    if not pts:
        return {"lat": 20, "lon": 20, "scale": 1.0}
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(lats) - min(lats), (max(lons) - min(lons)) / 1.6, 10)
    return {"lat": (max(lats) + min(lats)) / 2, "lon": (max(lons) + min(lons)) / 2,
            "scale": round(max(1.0, min(4.0, 120 / span)), 2)}
