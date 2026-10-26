"""Raccolta da tutte le fonti. Usa solo aiohttp: gira sia in HA sia nello strumento di prova."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

import aiohttp

from .models import VENUE_FORUM, VENUE_REPOWER, Event, merge_events
from .sources import euroleague, forumnet, jsonld, rockol, ticketone

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "HomeAssistant-forum_eventi/0.1 (uso personale, 1 richiesta/settimana)"
PAGE_DELAY = 2.0          # secondi tra una pagina e l'altra: siamo ospiti
MAX_PAGES = 10
# Applicato a OGNI richiesta: senza, aiohttp aspetta fino a 5 minuti un sito che non risponde
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)


@dataclass
class FetchReport:
    events: list[Event] = field(default_factory=list)
    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


async def _get_text(session: aiohttp.ClientSession, url: str) -> str:
    t0 = time.monotonic()
    try:
        async with session.get(
            url, timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it"},
        ) as resp:
            resp.raise_for_status()
            text = await resp.text()
    except asyncio.TimeoutError as err:
        raise TimeoutError(f"nessuna risposta entro {TIMEOUT.total}s da {url}") from err
    _LOGGER.info("GET %s -> %s, %d KB in %.1fs", url, resp.status, len(text) // 1024, time.monotonic() - t0)
    return text


# Dopo quante raccolte di fila con errore o 0 eventi una fonte va segnalata come rotta
BROKEN_AFTER = 2

SOURCE_LABELS = {
    "ufficiale_forum": "sito ufficiale dell'Unipol Forum",
    "ufficiale_repower": "sito ufficiale del Teatro Repower",
    "rockol_forum": "Rockol",
    "euroleague": "EuroLeague",
    "ticketone_forum": "TicketOne (Unipol Forum)",
    "ticketone_repower": "TicketOne (Teatro Repower)",
}


def source_label(name: str) -> str:
    """Nome leggibile di una fonte; per le pagine extra il dominio."""
    return SOURCE_LABELS.get(name) or (urlparse(name).hostname or name).removeprefix("www.")


def source_failures(previous: dict[str, int], report: FetchReport) -> dict[str, int]:
    """Raccolte consecutive fallite per ogni fonte usata in questa raccolta (errore oppure 0 eventi).
    Le fonti non più usate (spente dalle opzioni) spariscono."""
    out: dict[str, int] = {}
    for name in [*report.per_source, *report.errors]:
        failed = name in report.errors or report.per_source.get(name, 0) == 0
        out[name] = previous.get(name, 0) + 1 if failed else 0
    return out


def failure_detail(name: str, report: FetchReport) -> str:
    return report.errors.get(name) or "nessun evento trovato: probabilmente il sito ha cambiato struttura"


async def fetch_ticketone(session: aiohttp.ClientSession, venue: str) -> list[Event]:
    first = await _get_text(session, ticketone.page_url(venue, 1))
    events = ticketone.parse_listing(first, venue)
    pages = min(ticketone.max_page(first), MAX_PAGES)
    _LOGGER.info("TicketOne %s: pagina 1 -> %d eventi, %d pagine totali", venue, len(events), pages)
    for page in range(2, pages + 1):
        await asyncio.sleep(PAGE_DELAY)
        events += ticketone.parse_listing(await _get_text(session, ticketone.page_url(venue, page)), venue)
    return events


async def fetch_forumnet(session: aiohttp.ClientSession, venue: str) -> list[Event]:
    """Calendario ufficiale (JSON) di Unipol Forum o Teatro Repower, tutte le pagine."""
    first = forumnet.load(await _get_text(session, forumnet.page_url(venue, 1)))
    events = forumnet.parse_payload(first, venue)
    offs = forumnet.offsets(first)
    _LOGGER.info("Sito ufficiale %s: %d pagine", venue, len(offs))
    for off in offs[1:]:
        await asyncio.sleep(PAGE_DELAY)
        events += forumnet.parse_payload(forumnet.load(await _get_text(session, forumnet.page_url(venue, off))), venue)
    return events


async def fetch_event_pages(session: aiohttp.ClientSession, events: list[Event], cache: dict[str, dict],
                            today: date, tried: set[str] | None = None) -> int:
    """Legge le pagine evento ufficiali non ancora in cache (orari in testo libero), le più vicine per prime.
    Una pagina letta non si riscarica più: la cache (url -> {"letto", "programma"}) va conservata dal chiamante.
    `tried` raccoglie le pagine già tentate, per non ripeterle nello stesso giro. Restituisce quante pagine sono state lette."""
    tried = set() if tried is None else tried
    urls: list[str] = []
    for ev in sorted(events, key=lambda e: e.start):
        if (ev.start.date() >= today and forumnet.is_event_page(ev.url) and ev.url not in cache
                and ev.url not in tried and ev.url not in urls and "euroleague" not in ev.sources):
            urls.append(ev.url)
    read = errors = 0
    for i, url in enumerate(urls):
        if i:
            await asyncio.sleep(PAGE_DELAY)
        tried.add(url)
        try:
            schedule = forumnet.parse_event_page(await _get_text(session, url))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Pagina evento %s non disponibile: %s", url, err)
            errors += 1
            if errors >= 3:
                _LOGGER.warning("Troppi errori sulle pagine evento: riprovo alla prossima raccolta")
                break
            continue
        errors = 0
        read += 1
        if schedule is not None:            # "Evento passato": non in cache, si riprova la volta dopo
            cache[url] = {"letto": today.isoformat(), "programma": schedule}
    _LOGGER.info("Pagine evento: %d lette, %d da leggere, %d in cache", read, len(urls) - read, len(cache))
    return read


def prune_page_cache(cache: dict[str, dict], events: list[Event]) -> dict[str, dict]:
    """Tiene in cache solo le pagine degli eventi ancora in calendario."""
    keep = {e.url for e in events}
    return {url: v for url, v in cache.items() if url in keep}


async def fetch_rockol(session: aiohttp.ClientSession, venue: str) -> list[Event]:
    first = await _get_text(session, rockol.page_url(venue, 1))
    events = rockol.parse_listing(first)
    pages = min(rockol.max_page(first), MAX_PAGES)
    _LOGGER.info("Rockol %s: pagina 1 -> %d eventi, %d pagine totali", venue, len(events), pages)
    for page in range(2, pages + 1):
        await asyncio.sleep(rockol.CRAWL_DELAY)   # Crawl-Delay del loro robots.txt
        events += rockol.parse_listing(await _get_text(session, rockol.page_url(venue, page)))
    return events


async def fetch_euroleague(session: aiohttp.ClientSession, today: date) -> list[Event]:
    return euroleague.parse_games(json.loads(await _get_text(session, euroleague.games_url(today))))


async def fetch_all(
    session: aiohttp.ClientSession,
    today: date,
    *,
    use_ticketone: bool = False,
    use_official: bool = True,
    use_rockol: bool = True,
    use_euroleague: bool = True,
    extra_urls: list[str] | None = None,
) -> FetchReport:
    report = FetchReport()
    jobs: dict[str, asyncio.Future] = {}
    if use_ticketone:
        jobs["ticketone_forum"] = fetch_ticketone(session, VENUE_FORUM)
        jobs["ticketone_repower"] = fetch_ticketone(session, VENUE_REPOWER)
    if use_official:
        for venue in forumnet.SITES:
            jobs[f"ufficiale_{venue}"] = fetch_forumnet(session, venue)
    if use_rockol:
        for venue in rockol.VENUE_URLS:
            jobs[f"rockol_{venue}"] = fetch_rockol(session, venue)
    if use_euroleague:
        jobs["euroleague"] = fetch_euroleague(session, today)
    for url in extra_urls or []:
        async def _one(u=url):
            events = jsonld.parse_page(await _get_text(session, u), u)
            _LOGGER.info("JSON-LD %s -> %d eventi a Forum/Repower", u, len(events))
            return events
        jobs[url] = _one()

    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    collected: list[Event] = []
    for name, res in zip(jobs, results):
        if isinstance(res, Exception):
            _LOGGER.warning("Fonte %s non disponibile: %s", name, res)
            report.errors[name] = f"{type(res).__name__}: {res}"
            continue
        report.per_source[name] = len(res)
        collected += res

    report.events = [e for e in merge_events(collected) if e.start.date() >= today]
    return report
