"""
Common schema and plumbing for every data source.

Every intel adapter converts its native format into `Bulletin`s: the same shape
the Critic already reads and cites (id, time, source, severity, text). Adding a
new source means writing one adapter; the agents don't change.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM")
CATEGORIES = ("Security", "Sanctions", "Export Control", "Canal/Port", "Labor",
              "Insurance", "Carrier", "Weather", "Cargo", "Counterparty")

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"


@dataclass
class Bulletin:
    source: str                      # human name of the feed/list
    category: str                    # one of CATEGORIES
    severity: str                    # one of SEVERITIES
    text: str                        # one or two sentences the Critic can cite
    time: str = ""                   # ISO timestamp or publication date
    url: str = ""                    # link back to the original record
    location: str = ""               # matched place (port / chokepoint), if any
    lat: float | None = None
    lon: float | None = None
    id: str = ""                     # assigned by the builder (e.g. SEC-03)
    extra: dict = field(default_factory=dict)

    def to_intel(self) -> dict:
        """Shape consumed by agents.py / the UI (superset of the demo intel dicts)."""
        d = asdict(self)
        d.pop("extra")
        return d


@dataclass
class Context:
    """What a source may look at when deciding what is relevant."""
    manifest: dict
    routes: dict                      # route_id -> route dict (see carriers.py)


class IntelSource(Protocol):
    name: str

    def fetch(self, ctx: Context) -> list[Bulletin]: ...


class RouteSource(Protocol):
    name: str

    def routes(self, manifest: dict) -> dict: ...


# ------------------------------------------------------------------ I/O helpers

def read_text(location: str, headers: dict | None = None, ttl_s: int = 900,
              timeout: int = 20) -> str:
    """Read a local path (relative to repo root) or an http(s) URL, with a small disk cache."""
    if location.startswith(("http://", "https://")):
        key = hashlib.sha256((location + json.dumps(headers or {}, sort_keys=True)).encode()).hexdigest()[:24]
        cached = CACHE_DIR / key
        if cached.exists() and time.time() - cached.stat().st_mtime < ttl_s:
            return cached.read_text(encoding="utf-8", errors="replace")
        req = urllib.request.Request(location, headers={"User-Agent": "RouteGuard/1.0", **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
        CACHE_DIR.mkdir(exist_ok=True)
        cached.write_text(raw, encoding="utf-8")
        return raw
    p = Path(location)
    if not p.is_absolute():
        p = ROOT / p
    return p.read_text(encoding="utf-8-sig", errors="replace")


# Per-run keys (e.g. pasted into the app sidebar). A context variable, not os.environ, so a
# key one user pastes never leaks into another user's session on a shared server.
RUN_SECRETS: contextvars.ContextVar[dict] = contextvars.ContextVar("RUN_SECRETS", default={})


def secret(env_name: str | None) -> str | None:
    """Look up an API key by env-var name: a per-run key first, then the environment
    (Streamlit secrets are exported to env by app.py)."""
    if not env_name:
        return None
    return RUN_SECRETS.get().get(env_name) or os.environ.get(env_name)


def dig(obj: Any, path: str, default=None):
    """Tiny dotted-path getter for JSON feeds: dig(item, 'properties.title')."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return default
    return cur


# ------------------------------------------------------------------ severity heuristics

_CRIT = ("attack", "missile", "drone", "hijack", "seized", "seizure", "explosion", "struck",
         "closed", "closure", "suspended", "designat", "sanction", "embargo", "fatal", "killed")
_HIGH = ("strike", "stoppage", "restriction", "draft", "delay", "congestion", "queue", "advisory",
         "warning", "threat", "diversion", "divert", "boarding", "suspicious approach", "storm")


def guess_severity(text: str, default: str = "MEDIUM") -> str:
    t = text.lower()
    if any(k in t for k in _CRIT):
        return "CRITICAL"
    if any(k in t for k in _HIGH):
        return "HIGH"
    return default
