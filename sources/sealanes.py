"""
A small global sea-lane graph so port-to-port legs from carrier schedules are
drawn (and risk-matched) along plausible shipping corridors instead of straight
lines across land. Coarse by design: good for maps and chokepoint detection,
not for navigation.
"""

from __future__ import annotations

import heapq
import math
from functools import lru_cache

NODES = {
    "NorthSea": (54.0, 4.0), "Dover": (51.0, 1.5), "Ushant": (48.5, -5.5), "Finisterre": (43.5, -10.0),
    "StVincent": (37.0, -10.0), "Gibraltar": (36.0, -5.6), "WMed": (37.5, 3.0), "SicilyCh": (37.2, 11.5),
    "EMed": (34.0, 25.0), "PortSaid": (31.6, 32.3), "Suez": (30.0, 32.55), "RedSeaN": (27.5, 34.0),
    "RedSeaM": (20.0, 38.5), "BabM": (12.6, 43.3), "GulfAden": (12.5, 47.0), "ArabianSea": (14.0, 62.0),
    "GulfOman": (24.5, 58.5), "Hormuz": (26.5, 56.4), "PersianGulf": (26.8, 52.5), "SriLanka": (5.5, 80.5),
    "MalaccaN": (5.8, 95.0), "Malacca": (3.0, 100.8), "Singapore": (1.2, 104.0), "SChinaSea": (12.0, 112.0),
    "SChinaSeaN": (19.0, 114.5), "TaiwanSt": (24.0, 119.5), "EChina": (29.0, 123.5), "Korea": (34.0, 128.0),
    "Japan": (33.0, 135.0), "Sunda": (-6.5, 104.5), "IndianS": (-10.0, 80.0), "Mauritius": (-22.0, 57.0),
    "SAfrica": (-31.0, 38.0), "Agulhas": (-35.5, 20.0), "WAfricaS": (-20.0, 5.0), "GuineaGulf": (-3.0, -5.0),
    "WAfricaN": (10.0, -20.0), "Canaries": (28.0, -19.0), "MidAtl": (35.0, -45.0), "USEast": (35.0, -72.0),
    "FloridaSt": (24.2, -81.5), "GulfMexico": (26.5, -90.0), "Caribbean": (18.3, -64.3),
    "CaribW": (12.0, -77.0), "PanamaAtl": (9.5, -79.9), "PanamaPac": (8.6, -79.4), "PacCA": (10.0, -90.0),
    "MexPac": (20.0, -108.0), "CalCoast": (32.0, -118.5), "BrazilNE": (-5.0, -33.0), "Brazil": (-24.5, -44.5),
    "Aegean": (38.5, 25.0), "Dardanelles": (40.2, 26.4), "Bosporus": (41.1, 29.05), "BlackSea": (42.5, 35.0),
}

EDGES = [
    ("NorthSea", "Dover"), ("Dover", "Ushant"), ("Ushant", "Finisterre"), ("Finisterre", "StVincent"),
    ("StVincent", "Gibraltar"), ("Gibraltar", "WMed"), ("WMed", "SicilyCh"), ("SicilyCh", "EMed"),
    ("EMed", "PortSaid"), ("PortSaid", "Suez"), ("Suez", "RedSeaN"), ("RedSeaN", "RedSeaM"),
    ("RedSeaM", "BabM"), ("BabM", "GulfAden"), ("GulfAden", "ArabianSea"), ("ArabianSea", "SriLanka"),
    ("ArabianSea", "GulfOman"), ("GulfOman", "Hormuz"), ("Hormuz", "PersianGulf"), ("SriLanka", "MalaccaN"),
    ("MalaccaN", "Malacca"), ("Malacca", "Singapore"), ("Singapore", "SChinaSea"), ("SChinaSea", "SChinaSeaN"),
    ("SChinaSeaN", "TaiwanSt"), ("TaiwanSt", "EChina"), ("EChina", "Korea"), ("Korea", "Japan"),
    ("EChina", "Japan"), ("Singapore", "Sunda"), ("Sunda", "IndianS"), ("SriLanka", "IndianS"),
    ("IndianS", "Mauritius"), ("Mauritius", "SAfrica"), ("SAfrica", "Agulhas"), ("Agulhas", "WAfricaS"),
    ("WAfricaS", "GuineaGulf"), ("GuineaGulf", "WAfricaN"), ("WAfricaN", "Canaries"), ("Canaries", "StVincent"),
    ("Canaries", "MidAtl"), ("Ushant", "MidAtl"), ("MidAtl", "USEast"), ("MidAtl", "Caribbean"),
    ("USEast", "FloridaSt"), ("FloridaSt", "GulfMexico"), ("Caribbean", "CaribW"), ("CaribW", "PanamaAtl"),
    ("PanamaAtl", "PanamaPac"), ("PanamaPac", "PacCA"), ("PacCA", "MexPac"), ("MexPac", "CalCoast"),
    ("WAfricaN", "BrazilNE"), ("BrazilNE", "Caribbean"), ("BrazilNE", "Brazil"), ("EMed", "Aegean"),
    ("Aegean", "Dardanelles"), ("Dardanelles", "Bosporus"), ("Bosporus", "BlackSea"),
]


def _km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


@lru_cache(maxsize=1)
def _graph() -> dict[str, list[tuple[str, float]]]:
    g: dict[str, list[tuple[str, float]]] = {n: [] for n in NODES}
    for a, b in EDGES:
        d = _km(NODES[a], NODES[b])
        g[a].append((b, d))
        g[b].append((a, d))
    return g


def _nearest(p, k: int = 2) -> list[str]:
    return sorted(NODES, key=lambda n: _km(p, NODES[n]))[:k]


def _dijkstra(src: str) -> tuple[dict, dict]:
    dist, prev = {src: 0.0}, {}
    pq = [(0.0, src)]
    g = _graph()
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue
        for v, w in g[u]:
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def sea_path(a: tuple[float, float], b: tuple[float, float]) -> list[tuple[float, float]]:
    """Waypoints from a to b along the sea-lane graph (a and b included)."""
    direct = _km(a, b)
    best, best_path = direct if direct < 800 else math.inf, [a, b]
    for sa in _nearest(a):
        dist, prev = _dijkstra(sa)
        for sb in _nearest(b):
            if sb not in dist:
                continue
            total = _km(a, NODES[sa]) + dist[sb] + _km(NODES[sb], b)
            if total < best:
                path, n = [sb], sb
                while n != sa:
                    n = prev[n]
                    path.append(n)
                best, best_path = total, [a, *[NODES[x] for x in reversed(path)], b]
    return best_path
