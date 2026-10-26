"""Orari dalle pagine evento ufficiali e fasce di afflusso/deflusso."""
import asyncio
from datetime import date, datetime

import pytest
from conftest import FIXTURES
from custom_components.forum_eventi import fetch
from custom_components.forum_eventi.models import CAT_CONCERT, CAT_SPORT, CAT_THEATRE, VENUE_FORUM, VENUE_REPOWER, Event
from custom_components.forum_eventi.sources import forumnet
from custom_components.forum_eventi.windows import INFLOW, OUTFLOW, active, build_windows, next_change, upcoming
from test_core import TZ, ev

REPOWER = "https://www.teatrorepower.com"
FORUM = "https://www.unipolforum.it"


def page(name):
    return forumnet.parse_event_page((FIXTURES / f"forumnet_eve_{name}.html").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- parser delle pagine evento
def test_grease_times_by_weekday():
    s = page("grease")      # "giovedì, venerdì ore 20.30 sabato ore 15.30 e ore 20.30 domenica ore 15.30"
    assert forumnet.times_for(s, date(2027, 2, 18)) == ["20:30"]            # giovedì
    assert forumnet.times_for(s, date(2027, 2, 19)) == ["20:30"]            # venerdì
    assert forumnet.times_for(s, date(2027, 2, 20)) == ["15:30", "20:30"]   # sabato
    assert forumnet.times_for(s, date(2027, 2, 21)) == ["15:30"]            # domenica
    assert forumnet.times_for(s, date(2027, 2, 23)) == []                   # martedì: non in programma


def test_times_by_exact_date():
    alladin = page("alladin")     # "lunedì 4 gennaio 2027 ore 20:30 martedì 5 gennaio 2027 ore 12:00"
    assert forumnet.times_for(alladin, date(2027, 1, 4)) == ["20:30"]
    assert forumnet.times_for(alladin, date(2027, 1, 5)) == ["12:00"]
    magic = page("supermagic")
    assert [forumnet.times_for(magic, date(2027, 2, d)) for d in (12, 13, 14)] == [
        ["21:00"], ["16:00", "21:00"], ["15:00", "18:30"]]


def test_single_time_and_weekend_only():
    assert forumnet.times_for(page("schiaccianoci"), date(2027, 1, 6)) == ["19:00"]   # "inizio spettacolo ore 19.00"
    piccole = page("piccole_donne")                                                   # "sabato ore 20.30 domenica ore 15.30"
    assert forumnet.times_for(piccole, date(2027, 1, 30)) == ["20:30"]
    assert forumnet.times_for(piccole, date(2027, 1, 31)) == ["15:30"]


def test_forum_pages():
    assert forumnet.times_for(page("volley"), date(2026, 11, 22)) == ["18:00"]   # "Domenica 22 novembre alle ore 18"
    assert page("toliver") == []          # concerti al Forum: solo la data
    assert page("xfactor") == []          # "alle 21:15 su Sky Uno" è l'orario TV, senza "ore": ignorato


def test_doors_time_ignored_and_past_event():
    html = '<div id="content"><div class="sommario">apertura porte ore 19.00 inizio concerto ore 21.00</div></div>'
    assert forumnet.parse_event_page(html) == [{"giorni": [], "date": [], "orari": ["21:00"]}]
    past = '<div class="UltimoEvento"><div class="body">Evento passato</div></div>'
    assert forumnet.parse_event_page(past) is None


def test_is_event_page():
    assert forumnet.is_event_page(f"{REPOWER}/it/musical/eve/596-grease/")
    assert not forumnet.is_event_page("https://www.songkick.com/concerts/1-x")
    assert not forumnet.is_event_page(None)


# ---------------------------------------------------------------- applicazione degli orari
def test_apply_page_times_priority():
    grease = Event(VENUE_REPOWER, "GREASE", datetime(2027, 2, 20, tzinfo=TZ), ["ufficiale"],
                   url=f"{REPOWER}/it/musical/eve/596-grease/", category=CAT_THEATRE)
    concert = Event(VENUE_FORUM, "Volley", datetime(2026, 11, 22, 17, 0, tzinfo=TZ), ["ufficiale", "songkick.com"],
                    url=f"{FORUM}/it/sport/eve/1522-volley/", category=CAT_SPORT)
    game = Event(VENUE_FORUM, "Eurolega", datetime(2026, 11, 22, 20, 30, tzinfo=TZ), ["ufficiale", "euroleague"],
                 url=f"{FORUM}/it/sport/eve/1474-eurolega/", category=CAT_SPORT)
    cache = {
        grease.url: {"letto": "2026-10-26", "programma": page("grease")},
        concert.url: {"letto": "2026-10-26", "programma": page("volley")},
        game.url: {"letto": "2026-10-26", "programma": [{"giorni": [], "date": [], "orari": ["19:00"]}]},
    }
    assert forumnet.apply_page_times([grease, concert, game], cache) == 2
    assert grease.times == ["15:30", "20:30"] and grease.start.hour == 15 and grease.start.minute == 30
    assert concert.times == ["18:00"]                        # la pagina ufficiale vince su Songkick
    assert game.times == ["20:30"]                           # EuroLeague vince sulla pagina


class FakeResponse:
    def __init__(self, text):
        self._text, self.status = text, 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self._text is None:
            raise RuntimeError("HTTP 500")

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, **_kw):
        self.calls.append(url)
        return FakeResponse(self.pages.get(url))


def test_fetch_event_pages_cache(monkeypatch):
    monkeypatch.setattr(fetch, "PAGE_DELAY", 0)
    grease_url, past_url, broken_url = (f"{REPOWER}/it/musical/eve/596-grease/",
                                        f"{REPOWER}/it/altri-eventi/eve/600-x/", f"{REPOWER}/it/prosa/eve/1-rotta/")
    events = [
        Event(VENUE_REPOWER, "GREASE", datetime(2027, 2, d, tzinfo=TZ), ["ufficiale"], url=grease_url) for d in (18, 19)
    ] + [
        Event(VENUE_REPOWER, "X", datetime(2026, 11, 5, tzinfo=TZ), ["ufficiale"], url=past_url),
        Event(VENUE_REPOWER, "Rotta", datetime(2026, 11, 6, tzinfo=TZ), ["ufficiale"], url=broken_url),
        Event(VENUE_FORUM, "Vecchio", datetime(2026, 10, 1, tzinfo=TZ), ["ufficiale"], url=f"{FORUM}/it/musica/eve/9-v/"),
        Event(VENUE_FORUM, "Songkick", datetime(2026, 11, 1, 21, tzinfo=TZ), ["songkick.com"], url="https://songkick.com/x"),
    ]
    session = FakeSession({
        grease_url: (FIXTURES / "forumnet_eve_grease.html").read_text(encoding="utf-8"),
        past_url: '<div class="UltimoEvento">Evento passato</div>',
    })
    cache, tried = {}, set()
    read = asyncio.run(fetch.fetch_event_pages(session, events, cache, date(2026, 10, 26), tried))
    assert read == 2                                      # GREASE + pagina "passato"; la rotta è un errore
    assert session.calls == [past_url, broken_url, grease_url]     # una volta per pagina, le più vicine prima
    assert list(cache) == [grease_url]                    # "Evento passato" non va in cache
    # stesso giro: niente da rileggere; giro nuovo (tried vuoto): solo le pagine fuori cache
    assert asyncio.run(fetch.fetch_event_pages(session, events, cache, date(2026, 10, 26), tried)) == 0
    asyncio.run(fetch.fetch_event_pages(session, events, cache, date(2026, 10, 26)))
    assert session.calls[3:] == [past_url, broken_url]
    assert list(fetch.prune_page_cache(cache, events[2:])) == []


# ---------------------------------------------------------------- fasce di afflusso e deflusso
def at(d, hh, mm=0):
    return datetime(*d, hh, mm, tzinfo=TZ)


def test_windows_default_and_after_midnight():
    concert = ev("Placebo", (2026, 11, 6), 21, 0)
    w = build_windows([concert], date(2026, 11, 6), date(2026, 11, 6))
    assert [(x.kind, x.start, x.end, x.estimated) for x in w] == [
        (INFLOW, at((2026, 11, 6), 19), at((2026, 11, 6), 21), False),
        (OUTFLOW, at((2026, 11, 6), 23, 30), at((2026, 11, 7), 0), False),
    ]
    assert [x.kind for x in active(w, at((2026, 11, 6), 20), INFLOW)] == [INFLOW]
    assert active(w, at((2026, 11, 6), 21), INFLOW) == []                   # fine esclusa
    assert active(w, at((2026, 11, 6), 23, 45), OUTFLOW)[0].as_dict()["fine"] == "2026-11-07T00:00:00+01:00"
    assert next_change(w, at((2026, 11, 6), 12)) == at((2026, 11, 6), 19)
    assert next_change(w, at((2026, 11, 6), 21)) == at((2026, 11, 6), 23, 30)
    assert next_change(w, at((2026, 11, 7), 0)) is None


def test_windows_estimated_time_and_options():
    unknown = Event(VENUE_FORUM, "Tokio Hotel", datetime(2026, 11, 11, tzinfo=TZ), ["rockol"], category=CAT_CONCERT)
    w = build_windows([unknown], date(2026, 11, 11), date(2026, 11, 11), inflow_before=90, outflow_from=120, outflow_to=200)
    d = [x.as_dict() for x in w]
    assert d[0] == {"tipo": "afflusso", "inizio": "2026-11-11T19:30:00+01:00", "fine": "2026-11-11T21:00:00+01:00",
                    "evento": "Tokio Hotel", "venue": "Unipol Forum", "orario": "21:00", "orario_stimato": True}
    assert (d[1]["inizio"], d[1]["fine"]) == ("2026-11-11T23:00:00+01:00", "2026-11-12T00:20:00+01:00")
    repower = Event(VENUE_REPOWER, "X", datetime(2026, 11, 12, tzinfo=TZ), ["ufficiale"], category=CAT_THEATRE)
    assert build_windows([repower], date(2026, 11, 12), date(2026, 11, 12))[0].show.hour == 20   # 20:30 tipico


def test_windows_for_each_show_and_upcoming():
    grease = ev("Grease", (2027, 2, 20), 15, 30, venue=VENUE_REPOWER, cat=CAT_THEATRE)
    grease.times = ["15:30", "20:30"]
    w = build_windows([grease], date(2027, 2, 20), date(2027, 2, 20))
    assert [(x.kind, x.show.strftime("%H:%M")) for x in w] == [
        (INFLOW, "15:30"), (OUTFLOW, "15:30"), (INFLOW, "20:30"), (OUTFLOW, "20:30")]
    assert upcoming(w, at((2027, 2, 20), 16), INFLOW).show.hour == 20
    # fuori dall'intervallo di giorni: niente fasce
    assert build_windows([grease], date(2027, 2, 21), date(2027, 2, 22)) == []


@pytest.mark.parametrize("hhmm", ["20:30", "21:00"])
def test_window_bounds_follow_start(hhmm):
    h, m = map(int, hhmm.split(":"))
    w = build_windows([ev("A", (2026, 11, 3), h, m)], date(2026, 11, 3), date(2026, 11, 3))
    assert (w[0].end - w[0].start).total_seconds() == 2 * 3600 and w[0].end.strftime("%H:%M") == hhmm


def test_weekday_matinee_gets_no_rush_bonus():
    from custom_components.forum_eventi.scoring import assess_day
    matinee = ev("Alladin on ice", (2027, 1, 5), 12, 0, venue=VENUE_REPOWER, cat=CAT_THEATRE)   # martedì 12:00
    assert assess_day(date(2027, 1, 5), [matinee]).score == 12
    both = ev("Grease", (2027, 1, 5), 12, 0, venue=VENUE_REPOWER, cat=CAT_THEATRE)
    both.times = ["12:00", "20:30"]                     # conta lo spettacolo serale
    a = assess_day(date(2027, 1, 5), [both])
    assert any("inizio alle 20:30" in r for r in a.reasons) and a.score == 12 + 5 + 10


# ---------------------------------------------------------------- fonti rotte (riparazioni)
def test_source_failures_counting():
    from custom_components.forum_eventi.fetch import FetchReport, failure_detail, source_failures, source_label
    r1 = FetchReport(per_source={"ufficiale_forum": 82, "rockol_forum": 0}, errors={"euroleague": "TimeoutError: x"})
    f1 = source_failures({}, r1)
    assert f1 == {"ufficiale_forum": 0, "rockol_forum": 1, "euroleague": 1}
    r2 = FetchReport(per_source={"ufficiale_forum": 80, "rockol_forum": 0, "euroleague": 15})
    f2 = source_failures(f1, r2)
    assert f2 == {"ufficiale_forum": 0, "rockol_forum": 2, "euroleague": 0}     # EuroLeague tornata: azzerata
    assert source_failures(f2, FetchReport(per_source={"ufficiale_forum": 80})) == {"ufficiale_forum": 0}  # Rockol spenta
    assert failure_detail("euroleague", r1) == "TimeoutError: x"
    assert "0" not in failure_detail("rockol_forum", r1) and "struttura" in failure_detail("rockol_forum", r1)
    assert source_label("rockol_forum") == "Rockol"
    assert source_label("https://www.songkick.com/venues/4565288-unipol-forum/calendar") == "songkick.com"
