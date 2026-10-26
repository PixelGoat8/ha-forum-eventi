"""Rockol: pagina concerti della venue, HTML lato server, paginata con ?pag=N.

Il parser non dipende dal layout: ogni evento ha un link del tipo
  /concerto-alfa-unipol-forum-assago-mi-24-ottobre-2026-c-0pelao6w9rx
che contiene già venue, giorno, mese e anno. Rockol non riporta l'orario.
robots.txt: tutti i bot ammessi, Crawl-Delay 5.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import CAT_CONCERT, VENUE_FORUM, VENUE_REPOWER, Event, is_package

TZ = ZoneInfo("Europe/Rome")
SOURCE = "rockol"
BASE = "https://www.rockol.it"
CRAWL_DELAY = 5.0

VENUE_URLS = {
    VENUE_FORUM: f"{BASE}/concerti-unipol-forum-assago-milano-v-b9xr0lzrqy5",
}

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
VENUE_SLUGS = (
    ("teatro-repower", VENUE_REPOWER),
    ("unipol-forum", VENUE_FORUM),
    ("mediolanum-forum", VENUE_FORUM),
    ("forum-di-assago", VENUE_FORUM),
)
EVENT_RE = re.compile(
    r"/concerto-(?P<slug>[a-z0-9-]+?)-(?P<day>\d{1,2})-(?P<month>" + "|".join(MONTHS) + r")-(?P<year>20\d\d)-c-(?P<id>[a-z0-9]+)"
)


def page_url(venue: str, page: int) -> str:
    base = VENUE_URLS[venue]
    return base if page <= 1 else f"{base}?pag={page}"


def max_page(html: str) -> int:
    return max((int(n) for n in re.findall(r"[?&]pag=(\d+)", html)), default=1)


def _venue_and_artist(slug: str) -> tuple[str | None, str]:
    for marker, venue in VENUE_SLUGS:
        idx = slug.find(marker)
        if idx > 0:
            return venue, slug[: idx].strip("-")
    return None, slug


def _clean_text(text: str) -> str:
    """'Pooh Assago (Milano) Unipol Forum' -> 'Pooh'; '19.10: Pooh' -> 'Pooh'."""
    text = re.sub(r"^\s*\d{1,2}\.\d{1,2}\s*:\s*", "", text)
    text = re.split(r"\s+Assago\b|\s+Unipol Forum\b|\s+Teatro Repower\b", text)[0]
    return " ".join(text.split())


TITLE_ATTR_RE = re.compile(r"'(?P<name>.+?)'\s+presso\b")
DATE_ONLY_RE = re.compile(r"^\d{1,2}[./]\d{1,2}\.?$")


def _slug_title(slug: str) -> str:
    """'artie-5ive' -> 'Artie 5ive' (str.title() darebbe 'Artie 5Ive')."""
    return " ".join(w[:1].upper() + w[1:] for w in slug.split("-") if w)


def _title_for(a, artist_slug: str) -> str:
    """Ordine di affidabilità: attributo title ("... - 'Zero Assoluto' presso Unipol Forum"),
    testo del link se è un nome (non una data o un'etichetta), poi lo slug dell'URL."""
    m = TITLE_ATTR_RE.search(a.get("title", ""))
    if m:
        return m.group("name").strip()
    text = _clean_text(a.get_text(" ", strip=True))
    if 1 < len(text) <= 80 and not DATE_ONLY_RE.match(text) \
            and not text.lower().startswith(("biglietti", "info", "scopri", "dettagli", "tutti i concerti")):
        return text
    return _slug_title(artist_slug)


def parse_listing(html: str) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Event] = {}
    slug_titles: dict[str, bool] = {}       # id -> il titolo attuale viene solo dallo slug?
    for a in soup.find_all("a", href=EVENT_RE):
        m = EVENT_RE.search(a["href"])
        venue, artist_slug = _venue_and_artist(m.group("slug"))
        if venue is None:
            continue
        title = _title_for(a, artist_slug)
        from_slug = title == _slug_title(artist_slug)
        if is_package(title):
            continue
        ev_id = m.group("id")
        if ev_id in found and not (slug_titles[ev_id] and not from_slug):
            continue          # già visto con un titolo buono: il primo vince
        href = a["href"]
        slug_titles[ev_id] = from_slug
        found[ev_id] = Event(
            venue=venue,
            title=title,
            start=datetime(int(m.group("year")), MONTHS[m.group("month")], int(m.group("day")), tzinfo=TZ),
            sources=[SOURCE],
            url=href if href.startswith("http") else f"{BASE}{href}",
            category=CAT_CONCERT,
        )
    return list(found.values())
