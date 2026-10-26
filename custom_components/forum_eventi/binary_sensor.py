"""binary_sensor.forum_evento_oggi: acceso se oggi c'è almeno un evento."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ForumConfigEntry
from .entity import ForumEntity


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([TodayBinarySensor(entry.runtime_data)])


class TodayBinarySensor(ForumEntity, BinarySensorEntity):
    _attr_icon = "mdi:stadium"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "evento_oggi")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.assess(self.coordinator.today()).events)
