"""
Source registry: reads config/sources.toml, runs every enabled source, and assembles
a scenario dict in exactly the shape the agents and UI already use.

    scenario, report = build_scenario(manifest, "config/sources.toml")

A failing source never breaks the run: it is reported and skipped.
"""

from __future__ import annotations

import time

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from pathlib import Path

from .base import ROOT, RUN_SECRETS, Bulletin, Context
from .carriers import DCSAScheduleSource, RouteCSVSource
from .export_controls import ExportControlRulesSource, TradeGovCSLSource
from .feeds import JSONFeedSource, RSSFeedSource
from .geo import map_center
from .sanctions import CountryEmbargoSource, SanctionsListSource
from .similarweb import SimilarwebSource

INTEL_TYPES = {
    "rss": RSSFeedSource,
    "json": JSONFeedSource,
    "sanctions_list": SanctionsListSource,
    "country_embargo": CountryEmbargoSource,
    "export_rules": ExportControlRulesSource,
    "trade_gov_csl": TradeGovCSLSource,
    "similarweb": SimilarwebSource,
}
ROUTE_TYPES = {"route_csv": RouteCSVSource, "dcsa": DCSAScheduleSource}
PREFIX = {"Security": "SEC", "Sanctions": "SAN", "Export Control": "EXP", "Canal/Port": "PORT",
          "Labor": "LAB", "Insurance": "INS", "Carrier": "CAR", "Weather": "WX", "Cargo": "CGO",
          "Counterparty": "KYC"}
SEV_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}


def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    with open(p, "rb") as f:
        return tomllib.load(f)


def _make(types: dict, spec: dict):
    spec = dict(spec)
    kind = spec.pop("type")
    spec.pop("enabled", None)
    if kind not in types:
        raise ValueError(f"unknown source type '{kind}'")
    return types[kind](**spec)


def build_scenario(manifest: dict, config_path: str | Path = "config/sources.toml",
                   secrets: dict | None = None) -> tuple[dict, list[dict]]:
    """`secrets` ({env var name: key}) override the environment for this run only."""
    token = RUN_SECRETS.set({k: v for k, v in (secrets or {}).items() if v})
    try:
        return _build(manifest, config_path)
    finally:
        RUN_SECRETS.reset(token)


def _build(manifest: dict, config_path: str | Path) -> tuple[dict, list[dict]]:
    cfg = load_config(config_path)
    report: list[dict] = []

    # 1. candidate routes from carrier schedules / rate sheets
    routes: dict = {}
    for spec in cfg.get("routes", []):
        if not spec.get("enabled", True):
            report.append({"source": spec.get("name", spec["type"]), "kind": "routes", "status": "disabled", "items": 0})
            continue
        t0 = time.time()
        try:
            got = _make(ROUTE_TYPES, spec).routes(manifest)
            routes.update(got)
            report.append({"source": spec["name"], "kind": "routes", "status": "ok", "items": len(got),
                           "ms": int((time.time() - t0) * 1000)})
        except Exception as exc:
            report.append({"source": spec.get("name", spec["type"]), "kind": "routes", "status": f"error: {exc}", "items": 0})
    if not routes:
        raise ValueError("no candidate routes found for this origin/destination; add them to a route source")

    # 2. intel from every configured feed / list, filtered to this shipment's routes
    ctx = Context(manifest=manifest, routes=routes)
    bulletins: list[Bulletin] = []
    for spec in cfg.get("intel", []):
        name = spec.get("name", spec["type"])
        if not spec.get("enabled", True):
            report.append({"source": name, "kind": spec["type"], "status": "disabled", "items": 0})
            continue
        t0 = time.time()
        try:
            got = _make(INTEL_TYPES, spec).fetch(ctx)
            bulletins.extend(got)
            report.append({"source": name, "kind": spec["type"], "status": "ok", "items": len(got),
                           "ms": int((time.time() - t0) * 1000)})
        except Exception as exc:
            report.append({"source": name, "kind": spec["type"], "status": f"error: {exc}", "items": 0})

    # 3. dedupe, rank, cap, assign citable ids
    seen, uniq = set(), []
    for b in sorted(bulletins, key=lambda b: SEV_RANK.get(b.severity, 3)):
        k = (b.category, b.text[:120].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(b)
    uniq = uniq[: int(cfg.get("settings", {}).get("max_bulletins", 25))]
    counters: dict[str, int] = {}
    for b in uniq:
        p = PREFIX.get(b.category, "INT")
        counters[p] = counters.get(p, 0) + 1
        b.id = f"{p}-{counters[p]:02d}"

    # 4. map hotspots from bulletins that resolved to a place
    hotspots, placed = [], set()
    for b in uniq:
        if b.lat is not None and b.location not in placed:
            placed.add(b.location)
            hotspots.append({"name": b.location, "lat": b.lat, "lon": b.lon,
                             "label": f"{b.location}: {b.category} ({b.id})"})

    m = manifest
    scenario = {
        "title": f"{m.get('shipment_id')}: {m.get('origin')} → {m.get('destination')}",
        "tagline": str(m.get("cargo", "")),
        "manifest": {"deadline_days": m.get("deadline_days", "n/a"), "declared_value_usd": m.get("declared_value_usd", 0),
                     "containers": m.get("containers", "n/a"), **m},
        "routes": routes,
        "intel": [b.to_intel() for b in uniq],
        "hotspots": hotspots,
        "map_center": map_center(routes),
        "script": None,          # no replay script: connected-source runs are always live
        "live_data": True,
    }
    return scenario, report
