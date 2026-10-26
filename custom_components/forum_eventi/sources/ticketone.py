"""TicketOne: pagine 'venue' (HTML lato server, paginate con ?pnum=N).

Strategia di parsing, dalla più affidabile alla più fragile:
1. blocchi JSON-LD schema.org Event, se presenti;
2. euristica sul DOM: ogni link /event/<slug>-<id>/ viene risalito fino al
   contenitore che porta data ("07 ott 2026") e ora ("21:00").
Nessuna dipendenza da Home Assistant.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from ..models import (
    CAT_CONCERT, CAT_OTHER, CAT_SPORT, CAT_THEATRE, VENUE_FORUM, VENUE_REPOWER,
    Event, is_package,
)

TZ = ZoneInfo("Europe/Rome")
SOURCE = "ticketone"
BASE = "https://www.ticketone.it"

VENUE_URLS = {
    VENUE_FORUM: f"{BASE}/city/assago-215/venue/unipol-forum-15102/",
    VENUE_REPOWER: f"{BASE}/city/assago-215/venue/teatro-repower-16222/",
}

MONTHS = {
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
}
EVENT_HREF = re.compile(r"/event/[^\"'\s]*?-(\d{6,})/?")
DATE_RE = re.compile(r"\b(\d{1,2})\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)[a-z]*\.?\s+(20\d\d)\b", re.I)
TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
SOLD_OUT_RE = re.compile(r"sold\s*out|esaurit", re.I)


def page_url(venue: str, page: int) -> str:
    base = VENUE_URLS[venue]
    return base if page <= 1 else f"{base}?pnum={page}"


def max_page(html: str) -> int:
    """Numero di pagine ('1 di 4' o link ?pnum=N)."""
    pages = [int(n) for n in re.findall(r"[?&]pnum=(\d+)", html)]
    m = re.search(r"\b\d+\s+di\s+(\d+)\b", html)
    if m:
        pages.append(int(m.group(1)))
    return max(pages, default=1)


def parse_listing(html: str, venue: str) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    events = _from_json_ld(soup, venue)
    if not events:
        events = _from_dom(soup, venue)
    return events


# --------------------------------------------------------------------- JSON-LD
def _from_json_ld(soup: BeautifulSoup, venue: str) -> list[Event]:
    out: list[Event] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_ld(data):
            ev = event_from_ld(item, venue, SOURCE)
            if ev:
                out.append(ev)
    return out


def _walk_ld(data):
    if isinstance(data, list):
        for x in data:
            yield from _walk_ld(x)
    elif isinstance(data, dict):
        types = data.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and t.endswith("Event") for t in types):
            yield data
        for key in ("@graph", "itemListElement", "item", "subEvent"):
            if key in data:
                yield from _walk_ld(data[key])


def event_from_ld(item: dict, venue: str, source: str) -> Event | None:
    """Converte un oggetto schema.org Event. Usato anche dalla fonte generica."""
    name = (item.get("name") or "").strip()
    start = item.get("startDate")
    if not name or not start or is_package(name):
        return None
    try:
        dt = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except ValueError:
        return None
    dt = dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)
    availability = str((item.get("offers") or {}).get("availability", "")) if isinstance(item.get("offers"), dict) else ""
    types = item.get("@type")
    return Event(
        venue=venue,
        title=name,
        start=dt,
        sources=[source],
        url=item.get("url"),
        category=_category_from_type(types, name),
        sold_out="SoldOut" in availability,
    )


def _category_from_type(types, name: str) -> str:
    blob = f"{types} {name}".lower()
    if "music" in blob or "concert" in blob:
        return CAT_CONCERT
    if "sport" in blob or " vs " in blob or "basket" in blob:
        return CAT_SPORT
    if "theater" in blob or "theatre" in blob or "musical" in blob or "dance" in blob:
        return CAT_THEATRE
    return CAT_OTHER


# ------------------------------------------------------------------------ DOM
def _from_dom(soup: BeautifulSoup, venue: str) -> list[Event]:
    seen: set[str] = set()
    out: list[Event] = []
    for a in soup.find_all("a", href=EVENT_HREF):
        event_id = EVENT_HREF.search(a["href"]).group(1)
        if event_id in seen:
            continue
        box = _event_container(a, event_id)
        if box is None:
            continue
        seen.add(event_id)
        text = box.get_text(" ", strip=True)
        title = _title(box, a)
        if not title or is_package(title, text):
            continue
        d = DATE_RE.search(text)
        if not d:
            continue
        day, mon, year = int(d.group(1)), MONTHS[d.group(2)[:3].lower()], int(d.group(3))
        t = TIME_RE.search(text[d.end():]) or TIME_RE.search(text)
        hour, minute = (int(t.group(1)), int(t.group(2))) if t else (0, 0)
        href = a["href"]
        out.append(Event(
            venue=venue,
            title=title,
            start=datetime(year, mon, day, hour, minute, tzinfo=TZ),
            sources=[SOURCE],
            url=href if href.startswith("http") else f"{BASE}{href}",
            # Al Forum su TicketOne sono quasi tutti concerti; al Repower spettacoli
            category=CAT_THEATRE if venue == VENUE_REPOWER else CAT_CONCERT,
            sold_out=bool(SOLD_OUT_RE.search(text)),
        ))
    return out


def _event_container(a: Tag, event_id: str) -> Tag | None:
    """Risale il DOM finché trova un nodo con data, che contenga UN solo evento."""
    node: Tag | None = a
    for _ in range(8):
        node = node.parent if node is not None else None
        if node is None or node.name in ("body", "html"):
            return None
        ids = {m.group(1) for m in EVENT_HREF.finditer(str(node))}
        if len(ids) > 1:
            return None
        if DATE_RE.search(node.get_text(" ", strip=True)):
            return node
    return None


def _title(box: Tag, a: Tag) -> str:
    for tag in ("h2", "h3", "h4"):
        h = box.find(tag)
        if h and h.get_text(strip=True):
            return h.get_text(" ", strip=True)
    return (a.get("title") or a.get_text(" ", strip=True) or "").strip()
