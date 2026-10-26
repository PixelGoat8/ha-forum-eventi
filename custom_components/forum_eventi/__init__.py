"""Eventi al Forum di Assago e al Teatro Repower, con indice di casino giornaliero."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, SERVICE_REFRESH
from .coordinator import ForumCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.BUTTON]

type ForumConfigEntry = ConfigEntry[ForumCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry) -> bool:
    coordinator = ForumCoordinator(hass, entry)
    await coordinator.async_setup()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        async def _refresh(_call: ServiceCall) -> None:
            for e in hass.config_entries.async_loaded_entries(DOMAIN):
                await e.runtime_data.async_refresh()

        hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh)
    return True


async def _options_updated(hass: HomeAssistant, entry: ForumConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ForumConfigEntry) -> None:
    """Integrazione rimossa: via anche le segnalazioni delle fonti rotte."""
    for domain, issue_id in list(ir.async_get(hass).issues):
        if domain == DOMAIN:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


async def async_unload_entry(hass: HomeAssistant, entry: ForumConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_shutdown()
    return ok
