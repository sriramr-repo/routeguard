"""
News-style feeds: maritime security advisories and canal / port authority notices.

Two adapters cover almost every publisher:
  * RSSFeedSource   - RSS 2.0 or Atom (most security centres, port authorities, carriers)
  * JSONFeedSource  - any JSON API, via a small field mapping

Only items that mention a place on one of the candidate routes (a port or a
chokepoint the route passes near) are kept, so the Critic isn't flooded.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .base import Bulletin, Context, dig, guess_severity, read_text, secret
from .geo import match_location, places_for_routes

_TAG = re.compile(r"<[^>]+>")


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def _parse_time(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fn in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = fn(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


class _FeedBase:
    def __init__(self, name: str, category: str, url: str, max_age_days: int = 30,
                 default_severity: str = "MEDIUM", require_route_match: bool = True,
                 headers: dict | None = None, api_key_env: str | None = None,
                 api_key_header: str = "Authorization", keywords: list[str] | None = None,
                 max_items: int = 8, **_):
        self.name, self.category, self.url = name, category, url
        self.max_age = timedelta(days=max_age_days)
        self.default_severity = default_severity
        self.require_route_match = require_route_match
        self.headers = dict(headers or {})
        key = secret(api_key_env)
        if key:
            self.headers[api_key_header] = key
        self.keywords = [k.lower() for k in (keywords or [])]
        self.max_items = max_items

    def _items(self) -> list[dict]:
        raise NotImplementedError

    def fetch(self, ctx: Context) -> list[Bulletin]:
        places = places_for_routes(ctx.routes)
        now = datetime.now(timezone.utc)
        out = []
        for it in self._items():
            title, body = _clean(it.get("title")), _clean(it.get("summary"))
            text = f"{title}. {body}" if body and body.lower() != title.lower() else title
            when = _parse_time(it.get("time", ""))
            if when and now - when > self.max_age:
                continue
            loc = match_location(text, places)
            kw_hit = any(k in text.lower() for k in self.keywords)
            if self.require_route_match and not loc and not kw_hit:
                continue
            out.append(Bulletin(
                source=self.name, category=self.category,
                severity=guess_severity(text, self.default_severity),
                text=text[:420], time=when.date().isoformat() if when else it.get("time", ""),
                url=it.get("link", ""), location=loc[0] if loc else "",
                lat=loc[1] if loc else None, lon=loc[2] if loc else None))
        return out[: self.max_items]


class RSSFeedSource(_FeedBase):
    """RSS 2.0 / Atom. Point `url` at the feed (or a saved XML file)."""

    def _items(self) -> list[dict]:
        root = ET.fromstring(read_text(self.url, self.headers))
        items = []
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag not in ("item", "entry"):
                continue
            get = lambda *names: next((c.text or c.get("href") or "" for c in el
                                       if c.tag.split("}")[-1] in names and (c.text or c.get("href"))), "")
            items.append({"title": get("title"), "summary": get("description", "summary", "content"),
                          "time": get("pubDate", "published", "updated", "date"), "link": get("link", "guid")})
        return items


class JSONFeedSource(_FeedBase):
    """Any JSON API. `items_path` points at the list; `fields` maps title/summary/time/link."""

    def __init__(self, items_path: str = "", fields: dict | None = None, **kw):
        super().__init__(**kw)
        self.items_path = items_path
        self.fields = {"title": "title", "summary": "summary", "time": "time", "link": "link", **(fields or {})}

    def _items(self) -> list[dict]:
        data = json.loads(read_text(self.url, self.headers))
        rows = dig(data, self.items_path, []) if self.items_path else data
        return [{k: str(dig(r, path, "") or "") for k, path in self.fields.items()} for r in rows or []]
