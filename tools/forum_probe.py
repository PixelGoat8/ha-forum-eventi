#!/usr/bin/env python3
"""Prova le fonti fuori da Home Assistant e mostra eventi e punteggi.

    pip install aiohttp beautifulsoup4
    python3 tools/forum_probe.py                 # tutte le fonti, prossimi 60 giorni
    python3 tools/forum_probe.py --giorni 14 --big "Laura Pausini, Vasco Rossi"
    python3 tools/forum_probe.py --url https://esempio.it/eventi-assago
    python3 tools/forum_probe.py --raw           # salva l'HTML grezzo delle fonti e dice cosa ci trova
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import types
from datetime import date, timedelta
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "forum_eventi"
for name, path in (("custom_components", PKG.parent), ("custom_components.forum_eventi", PKG)):
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]           # evita __init__.py, che importa homeassistant
    sys.modules.setdefault(name, mod)

import aiohttp  # noqa: E402

from custom_components.forum_eventi.fetch import USER_AGENT, fetch_all, fetch_event_pages  # noqa: E402
from custom_components.forum_eventi.models import VENUE_FORUM, VENUE_REPOWER  # noqa: E402
from custom_components.forum_eventi.scoring import assess_day  # noqa: E402
from custom_components.forum_eventi.const import DEFAULTS, CONF_EXTRA_URLS  # noqa: E402
from custom_components.forum_eventi.sources import forumnet, jsonld, rockol  # noqa: E402
from custom_components.forum_eventi.windows import build_windows  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--giorni", type=int, default=60)
    ap.add_argument("--big", default="")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--ticketone", action="store_true", help="prova anche TicketOne (di solito bloccato)")
    ap.add_argument("--no-ufficiali", action="store_true", help="salta i siti ufficiali di Forum e Repower")
    ap.add_argument("--no-rockol", action="store_true")
    ap.add_argument("--no-default-urls", action="store_true", help="non usare Songkick come pagina extra")
    ap.add_argument("--no-euroleague", action="store_true")
    ap.add_argument("--no-pagine", action="store_true", help="non leggere le pagine evento ufficiali (orari)")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()
    today = date.today()
    # Avanzamento visibile: una riga per ogni pagina scaricata
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    from custom_components.forum_eventi.fetch import TIMEOUT
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        default_urls = [] if args.no_default_urls else DEFAULTS[CONF_EXTRA_URLS].split()
        if args.raw:
            targets = [
                ("ufficiale_forum", forumnet.page_url(VENUE_FORUM, 1)),
                ("ufficiale_repower", forumnet.page_url(VENUE_REPOWER, 1)),
                ("rockol_forum", rockol.page_url(VENUE_FORUM, 1)),
            ] + [
                (f"extra{i}", u) for i, u in enumerate(default_urls + args.url, 1)
            ]
            for name, url in targets:
                try:
                    async with session.get(url, headers={"User-Agent": USER_AGENT}) as r:
                        html = await r.text()
                except Exception as err:  # noqa: BLE001
                    print(f"{name}: ERRORE {type(err).__name__}: {err}")
                    continue
                out = Path(f"raw_{name}.html")
                out.write_text(html, encoding="utf-8")
                print(f"{name}: HTTP {r.status}, {len(html)//1024} KB -> {out}")
                print(f"   blocchi JSON-LD: {html.count('application/ld+json')}, "
                      f"eventi JSON-LD a Forum/Repower: {len(jsonld.parse_page(html, url))}, "
                      f"link evento Rockol: {len(rockol.parse_listing(html))}")
            return
        report = await fetch_all(
            session, today,
            use_ticketone=args.ticketone,
            use_official=not args.no_ufficiali,
            use_rockol=not args.no_rockol,
            use_euroleague=not args.no_euroleague,
            extra_urls=default_urls + args.url,
        )
        if not args.no_pagine and not args.no_ufficiali:
            # come in HA, ma senza cache su disco: legge tutte le pagine evento (~100, 2 s l'una)
            cache: dict = {}
            await fetch_event_pages(session, report.events, cache, today)
            print("Orari dalle pagine evento:", forumnet.apply_page_times(report.events, cache), "eventi")

    print("Eventi per fonte:", report.per_source)
    if report.errors:
        print("Errori:", report.errors)
    big = [b.strip() for b in args.big.split(",") if b.strip()]
    print()
    for i in range(args.giorni):
        a = assess_day(today + timedelta(days=i), report.events, big)
        if not a.events:
            continue
        print(f"{a.day:%a %d/%m}  {a.level.upper():8} {a.score:3}  {a.summary}")
        for r in a.reasons:
            print(f"{'':22}· {r}")
        for w in build_windows(report.events, a.day, a.day):
            est = " (orario stimato)" if w.estimated else ""
            print(f"{'':22}  {w.kind} {w.start:%H:%M}-{w.end:%H:%M} · {w.event.title}{est}")


if __name__ == "__main__":
    asyncio.run(main())
