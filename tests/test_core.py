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


# ---------------------------------------------------------------- siti ufficiali (Forumnet)
def _forumnet(name, venue):
    from custom_components.forum_eventi.sources import forumnet
    payload = forumnet.load((FIXTURES / name).read_text(encoding="utf-8"))
    return forumnet, payload, forumnet.parse_payload(payload, venue)


def test_forumnet_forum_real_payload():
    forumnet, payload, events = _forumnet("forumnet_forum_p1.json", VENUE_FORUM)
    assert len(events) == 11
    first = events[0]
    assert (first.title, first.start.date().isoformat(), first.category) == ("Don Toliver", "2026-10-27", CAT_CONCERT)
    assert first.url == "https://www.unipolforum.it/it/musica/eve/1466-don-toliver/"
    basket = next(e for e in events if "Trentino" in e.title)
    assert basket.category == CAT_SPORT and basket.start.date() == date(2026, 11, 8)
    assert forumnet.offsets(payload) == [1, 11, 21, 31, 41, 51, 61, 71]
    assert forumnet.page_url(VENUE_FORUM, 11).endswith("&pagine=11&cateve=Tutti&mese=Tutti")


def test_forumnet_repower_real_payload():
    _, payload, events = _forumnet("forumnet_repower_p1.json", VENUE_REPOWER)
    xf = [e for e in events if e.title.startswith("X FACTOR")]
    assert [e.start.day for e in xf] == [29, 5, 12, 19, 26]          # un giovedì per riga
    assert all(e.category == CAT_THEATRE for e in events)
    merged = merge_events(events)
    jan4 = [e.title for e in merged if e.start.date() == date(2027, 1, 4)]
    assert sorted(jan4) == ["ALLADIN ON ICE", "PRINCIPESSA ANASTASIA"]  # due spettacoli diversi, non uniti


def test_forumnet_overlapping_pages_are_deduplicated():
    _, _, events = _forumnet("forumnet_forum_p1.json", VENUE_FORUM)
    assert len(merge_events(events + events)) == len(events)


def test_official_and_euroleague_same_game_merge():
    official = ev("Eurolega: Armani Olimpia Milano vs Valencia Basket", (2026, 11, 5), 0, cat=CAT_SPORT, src="ufficiale")
    el = ev("Olimpia Milano – Valencia (EuroLeague)", (2026, 11, 5), 20, 30, cat=CAT_SPORT, src="euroleague")
    merged = merge_events([el, official])
    assert len(merged) == 1
    m = merged[0]
    assert m.title.startswith("Eurolega: Armani") and m.times == ["20:30"] and set(m.sources) == {"ufficiale", "euroleague"}


def test_official_rockol_songkick_merge_and_times_not_summed():
    merged = merge_events([
        ev("Artie5ive", (2026, 11, 10), 0, src="ufficiale"),
        ev("Artie 5ive", (2026, 11, 10), 0, src="rockol"),
        ev("Artie 5ive", (2026, 11, 10), 21, 0, src="songkick.com"),
        ev("Artie 5ive", (2026, 11, 10), 20, 45, src="ticketone"),
    ])
    assert len(merged) == 1
    m = merged[0]
    assert m.title == "Artie5ive" and m.times == ["21:00"]       # orario della fonte più affidabile, niente "repliche" finte


def test_forum_bill_with_several_artists_is_one_event():
    # Rockol: una pagina per artista della stessa serata; Songkick: un evento con più performer
    merged = merge_events([
        ev("Megadeth", (2027, 4, 6), 0, src="rockol"),
        ev("Testament", (2027, 4, 6), 0, src="rockol"),
        ev("Black Label Society", (2027, 4, 6), 0, src="rockol"),
        ev("Megadeth", (2027, 4, 6), 20, 0, src="songkick.com"),
    ])
    assert [(m.title, m.times) for m in merged] == [("Megadeth", ["20:00"])]
    a = assess_day(date(2027, 4, 6), merged)
    assert a.score == 55                                             # non 100: un solo concerto


def test_forum_official_rows_and_sport_stay_separate():
    merged = merge_events([
        ev("Spettacolo A", (2027, 1, 30), 0, src="ufficiale"),
        ev("Spettacolo B", (2027, 1, 30), 0, src="ufficiale"),
        ev("Basket Serie A: Olimpia Milano vs Varese", (2027, 1, 30), 0, cat=CAT_SPORT, src="ufficiale"),
        ev("Concerto C", (2027, 1, 30), 0, src="rockol"),
        ev("Teatro D", (2027, 1, 30), 0, venue=VENUE_REPOWER, cat=CAT_THEATRE, src="rockol"),
        ev("Teatro E", (2027, 1, 30), 0, venue=VENUE_REPOWER, cat=CAT_THEATRE, src="rockol"),
    ])
    assert len(merged) == 5           # C finisce in A; il Repower non è toccato dalla regola
    assert "rockol" in next(m for m in merged if m.title == "Spettacolo A").sources


# ---------------------------------------------------------------- lista big con livello minimo
def test_big_with_level_floor_on_repower():
    xf = [ev("X FACTOR 2026 - LIVE", (2026, 10, 29), 0, venue=VENUE_REPOWER, cat=CAT_THEATRE, src="ufficiale")]
    plain = assess_day(date(2026, 10, 29), xf)
    assert plain.level == "basso"
    boosted = assess_day(date(2026, 10, 29), xf, big_artists=["X Factor=alto"])
    assert boosted.score == 55 and boosted.level == "alto"
    assert any("almeno «alto»" in r for r in boosted.reasons)


def test_big_level_does_not_lower_and_plain_big_still_adds():
    pausini = [ev("Laura Pausini", (2026, 10, d), sold=True) for d in (5, 6, 7)]
    a = assess_day(date(2026, 10, 6), pausini, big_artists=["Laura Pausini=medio"])
    assert a.score == 90                                   # il livello minimo non abbassa mai
    b = assess_day(date(2026, 10, 13), [ev("Olimpia – Real", (2026, 10, 13), 20, 30, cat=CAT_SPORT)],
                   big_artists=["Olimpia", "X Factor=boh"])
    assert b.score == 55                                   # senza livello: +15 come prima; livello ignoto ignorato


def test_parse_big():
    from custom_components.forum_eventi.scoring import parse_big
    assert parse_big(["X Factor = Estremo", "Laura Pausini", " ", "Foo=xyz"]) == [
        ("x factor", "estremo"), ("laura pausini", None), ("foo", None)]
