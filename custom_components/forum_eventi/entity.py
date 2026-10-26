"""Base comune delle entità: un unico dispositivo di servizio."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ForumCoordinator


class ForumEntity(CoordinatorEntity[ForumCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ForumCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name="Forum",   # entity_id: sensor.forum_casino_oggi, ecc.
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Rockol · EuroLeague · Songkick/JSON-LD",
        )
