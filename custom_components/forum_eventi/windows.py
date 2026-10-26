"""Fasce di afflusso e deflusso intorno agli eventi: nessuna dipendenza da Home Assistant.

Afflusso: da `inflow_before` minuti prima dell'inizio fino all'inizio.
Deflusso: da `outflow_from` a `outflow_to` minuti dopo l'inizio.
Senza orario si usa quello tipico della venue e la fascia è marcata `orario_stimato`.
Più spettacoli nello stesso giorno (repliche) danno una coppia di fasce ciascuno.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .models import VENUE_FORUM, VENUE_LABELS, VENUE_REPOWER, Event

INFLOW = "afflusso"
OUTFLOW = "deflusso"

# Orario tipico quando le fonti non lo danno: al Forum le serate iniziano quasi sempre 20:30-21:00
TYPICAL_START = {VENUE_FORUM: (21, 0), VENUE_REPOWER: (20, 30)}

DEFAULT_INFLOW_BEFORE = 120
DEFAULT_OUTFLOW_FROM = 150
DEFAULT_OUTFLOW_TO = 180


@dataclass
class Window:
    kind: str                 # INFLOW | OUTFLOW
    start: datetime
    end: datetime
    event: Event
    show: datetime            # inizio dello spettacolo a cui si riferisce
    estimated: bool

    def contains(self, now: datetime) -> bool:
        return self.start <= now < self.end

    def as_dict(self) -> dict:
        return {
            "tipo": self.kind,
            "inizio": self.start.isoformat(),
            "fine": self.end.isoformat(),
            "evento": self.event.title,
            "venue": VENUE_LABELS[self.event.venue],
            "orario": self.show.strftime("%H:%M"),
            "orario_stimato": self.estimated,
        }


def show_starts(ev: Event) -> list[tuple[datetime, bool]]:
    """Inizi degli spettacoli dell'evento, con True se l'orario è stimato."""
    if ev.times:
        out = []
        for t in ev.times:
            hour, minute = (int(x) for x in t.split(":"))
            out.append((ev.start.replace(hour=hour, minute=minute), False))
        return out
    hour, minute = TYPICAL_START.get(ev.venue, (21, 0))
    return [(ev.start.replace(hour=hour, minute=minute, second=0, microsecond=0), True)]


def build_windows(
    events: list[Event],
    first_day: date,
    last_day: date,
    inflow_before: int = DEFAULT_INFLOW_BEFORE,
    outflow_from: int = DEFAULT_OUTFLOW_FROM,
    outflow_to: int = DEFAULT_OUTFLOW_TO,
) -> list[Window]:
    """Fasce degli eventi dei giorni da first_day a last_day compresi, in ordine di inizio."""
    out: list[Window] = []
    for ev in events:
        if not first_day <= ev.start.date() <= last_day:
            continue
        for show, estimated in show_starts(ev):
            out.append(Window(INFLOW, show - timedelta(minutes=inflow_before), show, ev, show, estimated))
            out.append(Window(OUTFLOW, show + timedelta(minutes=outflow_from), show + timedelta(minutes=outflow_to),
                              ev, show, estimated))
    return sorted(out, key=lambda w: (w.start, w.kind))


def active(windows: list[Window], now: datetime, kind: str) -> list[Window]:
    return [w for w in windows if w.kind == kind and w.contains(now)]


def upcoming(windows: list[Window], now: datetime, kind: str) -> Window | None:
    return next((w for w in windows if w.kind == kind and w.start > now), None)


def next_change(windows: list[Window], now: datetime) -> datetime | None:
    """Il prossimo istante in cui una fascia si apre o si chiude."""
    return min((t for w in windows for t in (w.start, w.end) if t > now), default=None)
