import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from conftest import FIXTURES
from custom_components.forum_eventi.models import (
    CAT_CONCERT, CAT_SPORT, CAT_THEATRE, VENUE_FORUM, VENUE_REPOWER, Event, merge_events, normalize_title,
)
from custom_components.forum_eventi.scoring import assess_day
from custom_components.forum_eventi.sources import euroleague, jsonld, ticketone

TZ = ZoneInfo("Europe/Rome")


def ev(title, d, hh=21, mm=0, venue=VENUE_FORUM, cat=CAT_CONCERT, sold=False, src="t"):
    return Event(venue=venue, title=title, start=datetime(*d, hh, mm, tzinfo=TZ), sources=[src], category=cat, sold_out=sold)


# ---------------------------------------------------------------- TicketOne
def test_ticketone_dom_parsing():
    html = (FIXTURES / "ticketone_forum_p1.html").read_text()
    events = ticketone.parse_listing(html, VENUE_FORUM)
    titles = [(e.title, e.start.strftime("%d/%m %H:%M"), e.sold_out) for e in events]
    assert titles == [
        ("Laura Pausini", "04/10 21:00", False),
        ("Laura Pausini", "06/10 21:00", True),
        ("Laura Pausini", "07/10 21:00", False),
        ("Kid Yugi", "08/10 21:00", True),
    ]  # il "Package" è scartato
    assert events[0].url.startswith("https://www.ticketone.it/event/")
    assert ticketone.max_page(html) == 4


def test_ticketone_page_urls():
    assert ticketone.page_url(VENUE_REPOWER, 1).endswith("teatro-repower-16222/")
    assert ticketone.page_url(VENUE_FORUM, 3).endswith("unipol-forum-15102/?pnum=3")


# ---------------------------------------------------------------- EuroLeague
def test_euroleague_only_future_home_games_at_forum():
    payload = json.loads((FIXTURES / "euroleague_mil.json").read_text())
    events = euroleague.parse_games(payload)
    assert len(events) == 1
    e = events[0]
    assert e.start == datetime(2026, 10, 13, 20, 30, tzinfo=TZ)
    assert "Real Madrid" in e.title and e.category == CAT_SPORT


def test_euroleague_season_code():
    assert euroleague.season_code(date(2026, 10, 8)) == "E2026"
    assert euroleague.season_code(date(2027, 3, 1)) == "E2026"


# ---------------------------------------------------------------- JSON-LD generico
def test_jsonld_filters_by_venue():
    html = (FIXTURES / "aggregator_jsonld.html").read_text()
    events = jsonld.parse_page(html, "https://example.org/eventi")
    assert {(e.venue, e.title) for e in events} == {
        (VENUE_FORUM, "Laura Pausini – Io canto World Tour"),
        (VENUE_REPOWER, "Grease"),
    }
    pausini = next(e for e in events if e.venue == VENUE_FORUM)
    assert pausini.sold_out and pausini.sources == ["example.org"]


# ---------------------------------------------------------------- dedup
def test_normalize_and_merge_across_sources():
    assert normalize_title("Laura Pausini - Io canto World Tour 2026") == "laura pausini"
    assert normalize_title("Laura Pausini – Io canto World Tour") == "laura pausini"
    merged = merge_events([
        ev("Laura Pausini", (2026, 10, 7), src="ticketone"),
        ev("Laura Pausini – Io canto World Tour", (2026, 10, 7), sold=True, src="example.org"),
    ])
    assert len(merged) == 1
    assert merged[0].sold_out and merged[0].sources == ["ticketone", "example.org"]


def test_merge_keeps_multiple_shows_same_day():
    merged = merge_events([
        ev("Winx Club", (2027, 1, 3), 15, 30, venue=VENUE_REPOWER, cat=CAT_THEATRE),
        ev("Winx Club", (2027, 1, 3), 19, 0, venue=VENUE_REPOWER, cat=CAT_THEATRE),
    ])
    assert len(merged) == 1 and merged[0].times == ["15:30", "19:00"]
    assert merged[0].start.hour == 15


# ---------------------------------------------------------------- punteggio
PAUSINI = [ev("Laura Pausini", (2026, 10, d), sold=(d == 6)) for d in (5, 6, 7)]


def test_three_nights_sold_out_weekday_is_extreme():
    a = assess_day(date(2026, 10, 6), PAUSINI)   # martedì, centrale, sold out
    # 45 base + 20 (3 sere) + 15 sold out + 10 feriale 21:00
    assert a.score == 90 and a.level == "estremo"


def test_repower_weekday_is_low():
    a = assess_day(date(2026, 10, 7), [ev("Grease", (2026, 10, 7), 20, 30, venue=VENUE_REPOWER, cat=CAT_THEATRE)])
    assert a.score == 22 and a.level == "basso"


def test_basket_weekday_is_medium():
    a = assess_day(date(2026, 10, 13), [ev("Olimpia – Real", (2026, 10, 13), 20, 30, cat=CAT_SPORT)])
    assert a.score == 40 and a.level == "medio"


def test_forum_plus_repower_and_big_list():
    events = [ev("Vasco Rossi", (2026, 10, 10)), ev("Grease", (2026, 10, 10), 20, 30, venue=VENUE_REPOWER, cat=CAT_THEATRE)]
    a = assess_day(date(2026, 10, 10), events, big_artists=["Vasco Rossi"])   # sabato
    # 45 + 15 big + 12 Repower + 10 insieme + 5 sabato
    assert a.score == 87 and a.level == "estremo"
    assert any("lista big" in r for r in a.reasons)


def test_empty_day():
    a = assess_day(date(2026, 10, 9), PAUSINI)
    assert a.score == 0 and a.level == "nessuno" and a.summary == "Nessun evento"


# ---------------------------------------------------------------- Rockol
def test_rockol_parsing_from_urls():
    from custom_components.forum_eventi.sources import rockol
    html = (FIXTURES / "rockol_forum_p1.html").read_text()
    events = sorted(rockol.parse_listing(html), key=lambda e: e.start)
    got = [(e.venue, e.title, e.start.date().isoformat()) for e in events]
    assert got == [
        (VENUE_FORUM, "Laura Pausini", "2026-10-07"),
        (VENUE_FORUM, "Pooh", "2026-10-19"),
        (VENUE_FORUM, "Zero Assoluto", "2026-10-20"),
        (VENUE_FORUM, "Alfa", "2026-10-24"),          # testo "Biglietti" -> titolo dallo slug
        (VENUE_FORUM, "Artie 5ive", "2026-11-10"),    # solo data e link generico -> slug
        (VENUE_REPOWER, "Grease", "2026-12-04"),
    ]  # l'evento all'Alcatraz è scartato
    assert all(e.times == [] for e in events)          # Rockol non dà l'orario
    assert rockol.max_page(html) == 4
    assert rockol.page_url(VENUE_FORUM, 2).endswith("?pag=2")


def test_unknown_time_weekday_forum_gets_rush_bonus():
    from custom_components.forum_eventi.sources import rockol
    events = rockol.parse_listing((FIXTURES / "rockol_forum_p1.html").read_text())
    a = assess_day(date(2026, 10, 20), events)        # martedì, Zero Assoluto, orario ignoto
    assert a.score == 55 and a.level == "alto"
    assert any("orario non noto" in r for r in a.reasons)


def test_songkick_style_title_merges_with_rockol():
    merged = merge_events([
        ev("Pooh", (2026, 10, 19), 0, src="rockol"),
        ev("Pooh @ Unipol Forum", (2026, 10, 19), 21, src="songkick"),
    ])
    assert len(merged) == 1 and merged[0].times == ["21:00"] and merged[0].sources == ["rockol", "songkick"]
