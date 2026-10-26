"""Sensori binari: evento oggi, afflusso in corso, deflusso in corso."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from . import ForumConfigEntry
from .entity import ForumEntity
from .windows import INFLOW, OUTFLOW, active, next_change, upcoming


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    async_add_entities([
        TodayBinarySensor(c),
        WindowBinarySensor(c, "afflusso_in_corso", INFLOW, "mdi:car-arrow-right"),
        WindowBinarySensor(c, "deflusso_in_corso", OUTFLOW, "mdi:car-arrow-left"),
    ])


class TodayBinarySensor(ForumEntity, BinarySensorEntity):
    _attr_icon = "mdi:stadium"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "evento_oggi")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.assess(self.coordinator.today()).events)


class WindowBinarySensor(ForumEntity, BinarySensorEntity):
    """Acceso durante una fascia di afflusso (o deflusso) di un evento.
    Si aggiorna da solo sui confini delle fasce, senza polling."""

    def __init__(self, coordinator, key: str, kind: str, icon: str) -> None:
        super().__init__(coordinator, key)
        self._kind = kind
        self._attr_icon = icon
        self._unsub_timer: CALLBACK_TYPE | None = None

    def _windows(self):
        # ieri compreso: il deflusso di un evento serale può finire dopo mezzanotte
        today = self.coordinator.today()
        return self.coordinator.windows(today - timedelta(days=1), today + timedelta(days=1))

    @property
    def is_on(self) -> bool:
        return bool(active(self._windows(), dt_util.now(), self._kind))

    @property
    def extra_state_attributes(self) -> dict:
        now = dt_util.now()
        windows = self._windows()
        nxt = upcoming(windows, now, self._kind)
        today = self.coordinator.today()
        return {
            "attive": [w.as_dict() for w in active(windows, now, self._kind)],
            "prossima": nxt.as_dict() if nxt else None,
            "oggi": [w.as_dict() for w in windows if w.kind == self._kind and w.show.date() == today],
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule()

    async def async_will_remove_from_hass(self) -> None:
        self._cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule()                 # orari nuovi (pagine evento) o giorno nuovo
        super()._handle_coordinator_update()

    def _cancel(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _schedule(self) -> None:
        self._cancel()
        when = next_change(self._windows(), dt_util.now())
        if when:
            self._unsub_timer = async_track_point_in_time(self.hass, self._boundary, when)

    @callback
    def _boundary(self, _now: datetime) -> None:
        self._unsub_timer = None
        self.async_write_ha_state()
        self._schedule()
