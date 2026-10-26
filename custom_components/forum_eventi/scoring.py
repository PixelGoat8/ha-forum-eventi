"""'Indice di casino' 0-100 per una giornata, con i motivi in chiaro.

Regole (tutte modificabili qui):
- base per venue/categoria: Forum concerto 45, Forum sport 30, Forum altro 35, Repower 12
- sold out: +15 (Forum) / +5 (Repower)
- più date di fila dello stesso artista al Forum: +10 per serata in più (max +20)
  -> "Pausini tre sere di fila" = base 45 + 20 + eventuale sold out
- evento nella tua lista 'big': +15; con un livello ("X Factor=alto") la giornata non scende
  sotto quel livello (minimo: medio 30, alto 55, estremo 75). Una voce corrisponde se tutte le sue
  parole compaiono nel titolo completo; se ne corrispondono più di una vince il livello più alto
  ("X Factor=alto" + "X Factor Finale=estremo")
- più spettacoli nella stessa giornata: +5 per replica
- Forum e Repower insieme: +10
- feriale con inizio serale (dalle 17:00) entro le 21:00 (afflusso in pieno rientro dal lavoro): +10
- venerdì/sabato sera: +5
"""
from __future__ import annotations

import re
import unicodedata
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


LEVEL_FLOOR = {"basso": 1, "medio": 30, "alto": 55, "estremo": 75}


def _words(text: str) -> frozenset[str]:
    """Parole del titolo COMPLETO (senza tagliare al primo trattino come normalize_title):
    'X FACTOR 2026 - FINALE' -> {'x', 'factor', '2026', 'finale'}."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return frozenset(re.sub(r"[^a-z0-9]+", " ", text).split())


def parse_big(entries: list[str] | None) -> list[tuple[frozenset[str], str | None]]:
    """'Laura Pausini' -> ({'laura', 'pausini'}, None); 'X Factor Finale=estremo' -> ({'x', 'factor', 'finale'}, 'estremo').
    Un livello non riconosciuto viene ignorato (resta il +15)."""
    out: list[tuple[frozenset[str], str | None]] = []
    for raw in entries or []:
        name, _, level = raw.partition("=")
        words = _words(name)
        level = level.strip().lower() or None
        if words:
            out.append((words, level if level in LEVEL_FLOOR else None))
    return out


def _big_matches(title: str, big: list[tuple[frozenset[str], str | None]]) -> list[str | None]:
    """Livelli di tutte le voci della lista le cui parole compaiono tutte nel titolo."""
    words = _words(title)
    return [lv for b, lv in big if b <= words]


def assess_day(day: date, all_events: list[Event], big_artists: list[str] | None = None) -> DayAssessment:
    todays = [e for e in all_events if e.start.date() == day]
    result = DayAssessment(day=day, events=todays)
    if not todays:
        return result

    big = parse_big(big_artists)
    score = 0
    floor = 0
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

        matches = _big_matches(ev.title, big)
        levels = [lv for lv in matches if lv]
        if levels:
            # più voci corrispondono ("X Factor=alto" e "X Factor Finale=estremo"): vince la più severa
            top = max(levels, key=LEVEL_FLOOR.__getitem__)
            if LEVEL_FLOOR[top] > floor:
                floor, floor_reason = LEVEL_FLOOR[top], f"{label}: dalla lista big, almeno «{top}»"
        elif matches:
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

    # Rientro dal lavoro: conta il primo spettacolo serale (dalle 17), non una matinée delle 12:00
    starts = [e.start.replace(hour=int(t[:2]), minute=int(t[3:])) for e in todays for t in e.times]
    has_times = bool(starts)
    first_start = min((s for s in starts if s.hour >= 17), default=None)
    if day.weekday() < 5:
        if first_start and (first_start.hour, first_start.minute) <= (21, 0):
            score += 10
            reasons.append(f"feriale, inizio alle {first_start:%H:%M} in orario di rientro (+10)")
        elif not has_times and VENUE_FORUM in {e.venue for e in todays}:
            # Rockol non dà l'orario: al Forum le serate iniziano quasi sempre 20:30-21:00
            score += 10
            reasons.append("feriale, orario non noto (al Forum di solito 20:30-21:00) (+10)")
    if day.weekday() in (4, 5):
        score += 5
        reasons.append("venerdì/sabato sera (+5)")

    if floor > score:
        reasons.append(f"{floor_reason} (portato a {floor})")
        score = floor
    result.score = max(0, min(100, score))
    result.level = level_for(result.score)
    result.reasons = reasons
    return result
