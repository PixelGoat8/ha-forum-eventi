"""Siti ufficiali di Unipol Forum e Teatro Repower (stesso CMS di Forumnet).

Il blocco "Calendario" delle pagine è riempito da un endpoint JSON:
  /index.php?action=It_GruppoForum&m=calendario&p=<id pagina>&pagine=<offset>&cateve=Tutti&mese=Tutti
che risponde {"msg": "<html con una riga per serata>", "pagine": "<html paginazione>"}.
`pagine` è l'offset 1-based a blocchi di 10 (1, 11, 21, ...). Ogni riga ha data gg/mm/aaaa,
titolo, link e categoria; le repliche sono già righe separate. Nessun orario.
robots.txt dei due siti: vietato solo /public/.

Gli orari stanno solo nelle pagine evento (/it/<cat>/eve/<id>-<slug>/), in testo libero:
  "giovedì, venerdì ore 20.30 sabato ore 15.30 e ore 20.30 domenica ore 15.30"   (Repower)
  "lunedì 4 gennaio 2027 ore 20:30 martedì 5 gennaio 2027 ore 12:00"             (Repower)
  "inizio spettacolo ore 19.00"                                                   (Repower)
  "Domenica 22 novembre alle ore 18"                                              (Forum, raro)
Le pagine del Forum di solito non hanno orari (concerti, Serie A, EuroLeague: solo la data).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
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


# ---------------------------------------------------------------- pagine evento: orari
WEEKDAYS = {"lunedi": 0, "martedi": 1, "mercoledi": 2, "giovedi": 3, "venerdi": 4, "sabato": 5, "domenica": 6}
MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
TOKEN_RE = re.compile(
    r"\b(?P<wd>" + "|".join(WEEKDAYS) + r")\b(?:\s+(?P<d>\d{1,2})\s+(?P<m>" + "|".join(MONTHS) + r")\b)?"
    r"|\bore\s+(?P<h>\d{1,2})(?:[.:](?P<min>\d{2}))?\b"
)
# "apertura porte ore 19.00" non è l'inizio dello spettacolo
DOORS_RE = re.compile(r"(apertur|porte|cancelli)[^.]{0,20}$")
EVENT_ID_RE = re.compile(r"/eve/(\d+)-")


def is_event_page(url: str | None) -> bool:
    return bool(url) and any(url.startswith(base) for base, _ in SITES.values()) and bool(EVENT_ID_RE.search(url))


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(text.split())


def parse_event_page(html: str) -> list[dict] | None:
    """Programma della pagina evento: gruppi {"giorni": [0-6], "date": ["MM-GG"], "orari": ["HH:MM"]}.
    Un gruppo senza giorni né date vale per tutte le serate ("inizio spettacolo ore 19.00").
    None se la pagina dice "Evento passato" (il programma potrebbe mancare: non va messa in cache)."""
    soup = BeautifulSoup(html, "html.parser")
    past = soup.select_one(".UltimoEvento")
    if past and "passato" in past.get_text().lower():
        return None
    # La scheda ha l'HTML rotto (un </div> dentro la tabella): si leggono direttamente sommario e testo
    parts = soup.select("#content .sommario, #content .testo") or soup.select(".sommario, .testo")
    text = _plain(" ".join(p.get_text(" ") for p in parts))
    groups: list[dict] = []
    cur: dict | None = None
    after_time = False
    for m in TOKEN_RE.finditer(text):
        if m["wd"]:
            if cur is None or after_time:          # dopo un orario comincia un gruppo nuovo
                cur = {"giorni": [], "date": [], "orari": []}
                groups.append(cur)
            if m["d"]:
                cur["date"].append(f"{MONTHS[m['m']]:02d}-{int(m['d']):02d}")
            else:
                cur["giorni"].append(WEEKDAYS[m["wd"]])
            after_time = False
            continue
        hour, minute = int(m["h"]), int(m["min"] or 0)
        if not 8 <= hour <= 23 or minute > 59 or DOORS_RE.search(text[max(0, m.start() - 30):m.start()]):
            continue
        if cur is None:
            cur = {"giorni": [], "date": [], "orari": []}
            groups.append(cur)
        hhmm = f"{hour:02d}:{minute:02d}"
        if hhmm not in cur["orari"]:
            cur["orari"].append(hhmm)
        after_time = True
    return [g for g in groups if g["orari"]]


def times_for(schedule: list[dict], day: date) -> list[str]:
    """Orari di una serata: prima la data esatta, poi il giorno della settimana, poi l'orario unico."""
    key = f"{day.month:02d}-{day.day:02d}"
    for match in (
        lambda g: key in g["date"],
        lambda g: not g["date"] and day.weekday() in g["giorni"],
    ):
        found = sorted({t for g in schedule if match(g) for t in g["orari"]})
        if found:
            return found
    if any(g["date"] or g["giorni"] for g in schedule):
        return []          # programma per giorni o date, ma non per questo
    return sorted({t for g in schedule for t in g["orari"]})


def apply_page_times(events: list[Event], cache: dict[str, dict]) -> int:
    """Orari dalle pagine evento già lette (cache: url -> {"letto", "programma"}).
    Priorità: EuroLeague > pagina ufficiale > Songkick, quindi le partite EuroLeague restano come sono.
    Restituisce quanti eventi hanno ricevuto un orario."""
    applied = 0
    for ev in events:
        entry = cache.get(ev.url or "")
        if not entry or "euroleague" in ev.sources:
            continue
        times = times_for(entry["programma"], ev.start.date())
        if not times:
            continue
        hour, minute = (int(x) for x in times[0].split(":"))
        ev.times = times
        ev.start = ev.start.replace(hour=hour, minute=minute)
        applied += 1
    return applied
