"""Raccolta da tutte le fonti. Usa solo aiohttp: gira sia in HA sia nello strumento di prova."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date

import aiohttp

from .models import VENUE_FORUM, VENUE_REPOWER, Event, merge_events
from .sources import euroleague, jsonld, rockol, ticketone

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


async def fetch_ticketone(session: aiohttp.ClientSession, venue: str) -> list[Event]:
    first = await _get_text(session, ticketone.page_url(venue, 1))
    events = ticketone.parse_listing(first, venue)
    pages = min(ticketone.max_page(first), MAX_PAGES)
    _LOGGER.info("TicketOne %s: pagina 1 -> %d eventi, %d pagine totali", venue, len(events), pages)
    for page in range(2, pages + 1):
        await asyncio.sleep(PAGE_DELAY)
        events += ticketone.parse_listing(await _get_text(session, ticketone.page_url(venue, page)), venue)
    return events


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
    use_rockol: bool = True,
    use_euroleague: bool = True,
    extra_urls: list[str] | None = None,
) -> FetchReport:
    report = FetchReport()
    jobs: dict[str, asyncio.Future] = {}
    if use_ticketone:
        jobs["ticketone_forum"] = fetch_ticketone(session, VENUE_FORUM)
        jobs["ticketone_repower"] = fetch_ticketone(session, VENUE_REPOWER)
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
