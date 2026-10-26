"""Sensori: livello e punteggio di oggi/domani, prossimo evento, settimana, diagnostica."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ForumConfigEntry
from .entity import ForumEntity
from .models import VENUE_LABELS
from .scoring import LEVEL_ICONS, LEVELS

LEVEL_OPTIONS = [name for _, name in reversed(LEVELS)]


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([
        LevelSensor(c, "casino_oggi", 0),
        ScoreSensor(c, "punteggio_oggi", 0),
        LevelSensor(c, "casino_domani", 1),
        NextEventSensor(c),
        WeekSensor(c),
        LastUpdateSensor(c),
    ])


class LevelSensor(ForumEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = LEVEL_OPTIONS

    def __init__(self, coordinator, key: str, offset: int) -> None:
        super().__init__(coordinator, key)
        self._offset = offset

    def _a(self):
        return self.coordinator.assess(self.coordinator.today() + timedelta(days=self._offset))

    @property
    def native_value(self) -> str:
        return self._a().level

    @property
    def icon(self) -> str:
        return LEVEL_ICONS[self._a().level]

    @property
    def extra_state_attributes(self) -> dict:
        return self._a().as_attributes()


class ScoreSensor(ForumEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, key: str, offset: int) -> None:
        super().__init__(coordinator, key)
        self._offset = offset

    @property
    def native_value(self) -> int:
        return self.coordinator.assess(self.coordinator.today() + timedelta(days=self._offset)).score


class NextEventSensor(ForumEntity, SensorEntity):
    _attr_icon = "mdi:ticket-confirmation"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prossimo_evento")

    def _next(self):
        today = self.coordinator.today()
        events = self.coordinator.data.events if self.coordinator.data else []
        return next((e for e in events if e.start.date() >= today), None)

    @property
    def native_value(self) -> str | None:
        ev = self._next()
        return ev.title[:255] if ev else None

    @property
    def extra_state_attributes(self) -> dict:
        ev = self._next()
        if not ev:
            return {}
        a = self.coordinator.assess(ev.start.date())
        return {
            "venue": VENUE_LABELS[ev.venue],
            "inizio": ev.start.isoformat(),
            "tra_giorni": (ev.start.date() - self.coordinator.today()).days,
            "sold_out": ev.sold_out,
            "livello_giornata": a.level,
            "punteggio_giornata": a.score,
            "url": ev.url,
        }


class WeekSensor(ForumEntity, SensorEntity):
    """Stato = giorni con eventi nei prossimi 7; attributi pronti per card e stampante."""
    _attr_icon = "mdi:calendar-week"
    _attr_native_unit_of_measurement = "giorni"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "prossimi_7_giorni")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.upcoming(7))

    @property
    def extra_state_attributes(self) -> dict:
        days = self.coordinator.upcoming(7)
        return {
            "giorni": [
                {"giorno": a.day.isoformat(), "livello": a.level, "punteggio": a.score, "riepilogo": a.summary}
                for a in days
            ],
            "peggiore": max(days, key=lambda a: a.score).day.isoformat() if days else None,
        }


class LastUpdateSensor(ForumEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-download"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ultimo_aggiornamento")

    @property
    def native_value(self):
        return self.coordinator.data.fetched_at if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        if not d:
            return {}
        return {
            "eventi_totali": len(d.events),
            "eventi_per_fonte": d.per_source,
            "errori": d.errors,
            # una fonte che restituisce 0 eventi di solito vuol dire parser rotto
            "fonti_vuote": [k for k, v in d.per_source.items() if v == 0],
        }
