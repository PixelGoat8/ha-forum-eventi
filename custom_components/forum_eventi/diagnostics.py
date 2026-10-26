"""Diagnostica della config entry (Impostazioni › Dispositivi e servizi › ⋮ › Scarica diagnostica)."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from . import ForumConfigEntry
from .fetch import BROKEN_AFTER

MAX_EVENTS = 30


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ForumConfigEntry) -> dict[str, Any]:
    # Nessun dato personale: le opzioni sono fonti, lista big, orari e minuti delle fasce
    c = entry.runtime_data
    d = c.data
    today = c.today()
    upcoming = [e for e in (d.events if d else []) if e.start.date() >= today]
    return {
        "opzioni": dict(entry.options),
        "ultima_raccolta": d.fetched_at.isoformat() if d and d.fetched_at else None,
        "eventi_totali": len(d.events) if d else 0,
        "eventi_per_fonte": d.per_source if d else {},
        "errori": d.errors if d else {},
        "fallimenti_consecutivi": c.failures,
        "soglia_segnalazione": BROKEN_AFTER,
        "pagine_evento_in_cache": c.pages_in_cache,
        "eventi_senza_orario": sum(1 for e in upcoming if not e.times),
        "prossimi_eventi": [e.to_dict() for e in upcoming[:MAX_EVENTS]],
        "giorni": [
            {"giorno": a.day.isoformat(), "livello": a.level, "punteggio": a.score, "motivi": a.reasons}
            for a in (c.assess(today + timedelta(days=i)) for i in range(7)) if a.events
        ],
    }
