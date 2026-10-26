"""Siti ufficiali di Unipol Forum e Teatro Repower (stesso CMS di Forumnet).

Il blocco "Calendario" delle pagine è riempito da un endpoint JSON:
  /index.php?action=It_GruppoForum&m=calendario&p=<id pagina>&pagine=<offset>&cateve=Tutti&mese=Tutti
che risponde {"msg": "<html con una riga per serata>", "pagine": "<html paginazione>"}.
`pagine` è l'offset 1-based a blocchi di 10 (1, 11, 21, ...). Ogni riga ha data gg/mm/aaaa,
titolo, link e categoria; le repliche sono già righe separate. Nessun orario.
robots.txt dei due siti: vietato solo /public/.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from ..models import CAT_CONCERT, CAT_OTHER, CAT_SPORT, CAT_THEATRE, VENUE_FORUM, VENUE_REPOWER, Event, is_package

TZ = ZoneInfo("Europe/Rome")
SOURCE = "ufficiale"
PAGE_SIZE = 10

SITES = {
    VENUE_FORUM: ("https://www.unipolforum.it", 69),
    VENUE_REPOWER: ("https://www.teatrorepower.com", 38),
}

FORUM_CATEGORIES = {"musica": CAT_CONCERT, "sport": CAT_SPORT}
DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def page_url(venue: str, offset: int = 1) -> str:
    base, page_id = SITES[venue]
    return (f"{base}/index.php?action=It_GruppoForum&m=calendario&p={page_id}"
            f"&pagine={offset}&cateve=Tutti&mese=Tutti")


def offsets(payload: dict) -> list[int]:
    """Offset di tutte le pagine elencate nella paginazione (1, 11, 21, ...)."""
    pages = [int(n) for n in re.findall(r'id="pagina(\d+)"', payload.get("pagine") or "")]
    return [(n - 1) * PAGE_SIZE + 1 for n in sorted(set(pages))] or [1]


def load(text: str) -> dict:
    return json.loads(text)


def _category(venue: str, label: str) -> str:
    if venue == VENUE_REPOWER:
        return CAT_THEATRE
    return FORUM_CATEGORIES.get(label.strip().lower(), CAT_OTHER)


def parse_payload(payload: dict, venue: str) -> list[Event]:
    base = SITES[venue][0]
    soup = BeautifulSoup(payload.get("msg") or "", "html.parser")
    out: list[Event] = []
    for row in soup.select("div.evento"):
        date_el, link = row.select_one(".datae"), row.select_one(".titoletto a")
        if not date_el or not link:
            continue
        m = DATE_RE.search(date_el.get_text())
        title = link.get_text(" ", strip=True)
        if not m or not title or is_package(title):
            continue
        day, month, year = (int(x) for x in m.groups())
        cat_el = row.select_one("span.cat")
        href = re.sub(r"/gestore/.*$", "/", link.get("href", ""))
        out.append(Event(
            venue=venue,
            title=title,
            start=datetime(year, month, day, tzinfo=TZ),
            sources=[SOURCE],
            url=href if href.startswith("http") else f"{base}{href}",
            category=_category(venue, cat_el.get_text() if cat_el else ""),
        ))
    return out
