"""Pulsante per forzare la raccolta fuori dal giro settimanale."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ForumConfigEntry
from .entity import ForumEntity


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([RefreshButton(entry.runtime_data)])


class RefreshButton(ForumEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "aggiorna_eventi")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
