"""Fonte generica: qualsiasi pagina che pubblichi eventi schema.org in JSON-LD.

Pensata per aggregatori e siti di biglietteria aggiunti dalle opzioni.
Tiene solo gli eventi la cui location cita il Forum o il Teatro Repower.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..models import VENUE_FORUM, VENUE_REPOWER, Event
from .ticketone import _walk_ld, event_from_ld

FORUM_HINTS = ("unipol forum", "forum di assago", "mediolanum forum", "forum assago", "forum di milano")
REPOWER_HINTS = ("teatro repower", "repower")


def venue_from_location(location) -> str | None:
    blob = json.dumps(location, ensure_ascii=False).lower() if location else ""
    if any(h in blob for h in REPOWER_HINTS):
        return VENUE_REPOWER
    if any(h in blob for h in FORUM_HINTS):
        return VENUE_FORUM
    return None


def parse_page(html: str, url: str) -> list[Event]:
    source = (urlparse(url).hostname or "web").removeprefix("www.")
    soup = BeautifulSoup(html, "html.parser")
    out: list[Event] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_ld(data):
            venue = venue_from_location(item.get("location"))
            if venue is None:
                continue
            ev = event_from_ld(item, venue, source)
            if ev:
                # Songkick: "Raf @ Unipol Forum" -> "Raf"
                ev.title = re.split(r"\s+@\s+", ev.title)[0].strip() or ev.title
                out.append(ev)
    return out
