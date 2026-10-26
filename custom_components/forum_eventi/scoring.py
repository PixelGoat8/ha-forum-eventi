"""'Indice di casino' 0-100 per una giornata, con i motivi in chiaro.

Regole (tutte modificabili qui):
- base per venue/categoria: Forum concerto 45, Forum sport 30, Forum altro 35, Repower 12
- sold out: +15 (Forum) / +5 (Repower)
- più date di fila dello stesso artista al Forum: +10 per serata in più (max +20)
  -> "Pausini tre sere di fila" = base 45 + 20 + eventuale sold out
- artista nella tua lista 'big': +15
- più spettacoli nella stessa giornata: +5 per replica
- Forum e Repower insieme: +10
- feriale con inizio entro le 21:00 (afflusso in pieno rientro dal lavoro): +10
- venerdì/sabato sera: +5
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import CAT_CONCERT, CAT_SPORT, VENUE_FORUM, VENUE_LABELS, VENUE_REPOWER, Event, normalize_title

LEVELS = [(75, "estremo"), (55, "alto"), (30, "medio"), (1, "basso"), (0, "nessuno")]
LEVEL_ICONS = {
    "nessuno": "mdi:check-circle-outline",
    "basso": "mdi:car",
    "medio": "mdi:car-multiple",
    "alto": "mdi:alert",
    "estremo": "mdi:alert-octagon",
}


@dataclass
class DayAssessment:
    day: date
    score: int = 0
    level: str = "nessuno"
    events: list[Event] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.events:
            return "Nessun evento"
        parts = []
        for ev in self.events:
            times = "/".join(ev.times) if ev.times else "orario n.d."
            tag = " SOLD OUT" if ev.sold_out else ""
            parts.append(f"{ev.title} ({VENUE_LABELS[ev.venue]}, {times}){tag}")
        return "; ".join(parts)

    def as_attributes(self) -> dict:
        return {
            "giorno": self.day.isoformat(),
            "punteggio": self.score,
            "livello": self.level,
            "motivi": self.reasons,
            "riepilogo": self.summary,
            "eventi": [
                {
                    "titolo": e.title,
                    "venue": VENUE_LABELS[e.venue],
                    "orari": e.times,
                    "inizio": e.start.isoformat(),
                    "sold_out": e.sold_out,
                    "categoria": e.category,
                    "fonti": e.sources,
                    "url": e.url,
                }
                for e in self.events
            ],
        }


def level_for(score: int) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "nessuno"


def _run_length(ev: Event, all_events: list[Event]) -> int:
    """Quante serate consecutive (incluso questa) fa lo stesso titolo al Forum."""
    title = normalize_title(ev.title)
    days = {e.start.date() for e in all_events if e.venue == ev.venue and normalize_title(e.title) == title}
    d0 = ev.start.date()
    start = d0
    while start - timedelta(days=1) in days:
        start -= timedelta(days=1)
    end = d0
    while end + timedelta(days=1) in days:
        end += timedelta(days=1)
    return (end - start).days + 1


def assess_day(day: date, all_events: list[Event], big_artists: list[str] | None = None) -> DayAssessment:
    todays = [e for e in all_events if e.start.date() == day]
    result = DayAssessment(day=day, events=todays)
    if not todays:
        return result

    big = [normalize_title(b) for b in (big_artists or []) if b.strip()]
    score = 0
    reasons: list[str] = []

    for ev in todays:
        label = ev.title
        if ev.venue == VENUE_FORUM:
            base = 45 if ev.category == CAT_CONCERT else 30 if ev.category == CAT_SPORT else 35
        else:
            base = 12
        score += base
        reasons.append(f"{label} al {VENUE_LABELS[ev.venue]} (+{base})")

        if ev.sold_out:
            bonus = 15 if ev.venue == VENUE_FORUM else 5
            score += bonus
            reasons.append(f"{label} sold out (+{bonus})")

        if ev.venue == VENUE_FORUM and ev.category != CAT_SPORT:   # le partite non fanno "residency"
            run = _run_length(ev, all_events)
            if run > 1:
                bonus = min(10 * (run - 1), 20)
                score += bonus
                reasons.append(f"{label}: {run} date di fila (+{bonus})")

        norm = normalize_title(ev.title)
        if any(b and (b in norm or norm in b) for b in big):
            score += 15
            reasons.append(f"{label} è nella lista big (+15)")

        if len(ev.times) > 1:
            bonus = 5 * (len(ev.times) - 1)
            score += bonus
            reasons.append(f"{label}: {len(ev.times)} spettacoli in giornata (+{bonus})")

    venues = {e.venue for e in todays}
    if {VENUE_FORUM, VENUE_REPOWER} <= venues:
        score += 10
        reasons.append("Forum e Repower insieme (+10)")

    first_start = min((e.start for e in todays if e.start.hour), default=None)
    if day.weekday() < 5:
        if first_start and (first_start.hour, first_start.minute) <= (21, 0):
            score += 10
            reasons.append(f"feriale, inizio alle {first_start:%H:%M} in orario di rientro (+10)")
        elif first_start is None and VENUE_FORUM in {e.venue for e in todays}:
            # Rockol non dà l'orario: al Forum le serate iniziano quasi sempre 20:30-21:00
            score += 10
            reasons.append("feriale, orario non noto (al Forum di solito 20:30-21:00) (+10)")
    if day.weekday() in (4, 5):
        score += 5
        reasons.append("venerdì/sabato sera (+5)")

    result.score = max(0, min(100, score))
    result.level = level_for(result.score)
    result.reasons = reasons
    return result
