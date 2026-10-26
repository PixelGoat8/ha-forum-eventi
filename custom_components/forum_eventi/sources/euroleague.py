"""Partite casalinghe dell'Olimpia al Forum dall'API pubblica EuroLeague.

Endpoint: https://api-live.euroleague.net/v2/competitions/E/seasons/E<anno>/games?teamCode=MIL
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..models import CAT_SPORT, VENUE_FORUM, Event

TZ = ZoneInfo("Europe/Rome")
SOURCE = "euroleague"
TEAM = "MIL"
FORUM_VENUE_CODE = "ASX8"


def season_code(today: date) -> str:
    """La stagione EuroLeague parte a luglio: ottobre 2026 -> E2026, marzo 2027 -> E2026."""
    return f"E{today.year if today.month >= 7 else today.year - 1}"


def games_url(today: date) -> str:
    return (
        "https://api-live.euroleague.net/v2/competitions/E/seasons/"
        f"{season_code(today)}/games?teamCode={TEAM}"
    )


def parse_games(payload: dict) -> list[Event]:
    out: list[Event] = []
    for g in payload.get("data", []):
        if g.get("played"):
            continue
        venue = g.get("venue") or {}
        home = ((g.get("local") or {}).get("club") or {}).get("code")
        at_forum = venue.get("code") == FORUM_VENUE_CODE or "FORUM" in str(venue.get("name", "")).upper()
        if home != TEAM or not at_forum:
            continue
        # utcDate è sempre presente e non ambiguo
        try:
            start = datetime.fromisoformat(g["utcDate"].replace("Z", "+00:00")).astimezone(TZ)
        except (KeyError, ValueError):
            continue
        road = ((g.get("road") or {}).get("club") or {}).get("abbreviatedName") or "?"
        out.append(Event(
            venue=VENUE_FORUM,
            title=f"Olimpia Milano – {road} (EuroLeague)",
            start=start,
            sources=[SOURCE],
            url=None,
            category=CAT_SPORT,
        ))
    return out
