"""Config flow (istanza unica, nessun dato richiesto) e options flow."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BIG_ARTISTS, CONF_EXTRA_URLS, CONF_INFLOW_BEFORE, CONF_OUTFLOW_FROM, CONF_OUTFLOW_TO, CONF_REFRESH_HOUR,
    CONF_REFRESH_WEEKDAY, CONF_USE_EUROLEAGUE, CONF_USE_EVENT_PAGES, CONF_USE_OFFICIAL, CONF_USE_ROCKOL,
    CONF_USE_TICKETONE, DEFAULTS, DOMAIN, NAME,
)

WEEKDAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MINUTES = (CONF_INFLOW_BEFORE, CONF_OUTFLOW_FROM, CONF_OUTFLOW_TO)


def _minutes(maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=0, max=maximum, step=5, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX))


class ForumConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={}, options=dict(DEFAULTS))
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ForumOptionsFlow()


class ForumOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_REFRESH_WEEKDAY] = int(user_input[CONF_REFRESH_WEEKDAY])
            user_input[CONF_REFRESH_HOUR] = int(user_input[CONF_REFRESH_HOUR])
            for key in MINUTES:
                if key in user_input:
                    user_input[key] = int(user_input[key])
            outflow_to = user_input.get(CONF_OUTFLOW_TO, DEFAULTS[CONF_OUTFLOW_TO])
            if outflow_to <= user_input.get(CONF_OUTFLOW_FROM, DEFAULTS[CONF_OUTFLOW_FROM]):
                errors[CONF_OUTFLOW_TO] = "outflow_order"
            else:
                return self.async_create_entry(data=user_input)

        o = {**DEFAULTS, **self.config_entry.options, **(user_input or {})}
        schema = vol.Schema({
            vol.Required(CONF_USE_OFFICIAL, default=o[CONF_USE_OFFICIAL]): bool,
            vol.Required(CONF_USE_EVENT_PAGES, default=o[CONF_USE_EVENT_PAGES]): bool,
            vol.Required(CONF_USE_ROCKOL, default=o[CONF_USE_ROCKOL]): bool,
            vol.Required(CONF_USE_EUROLEAGUE, default=o[CONF_USE_EUROLEAGUE]): bool,
            vol.Required(CONF_USE_TICKETONE, default=o[CONF_USE_TICKETONE]): bool,
            vol.Optional(CONF_BIG_ARTISTS, default=o[CONF_BIG_ARTISTS]): selector.TextSelector(),
            vol.Optional(CONF_EXTRA_URLS, default=o[CONF_EXTRA_URLS]): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(CONF_REFRESH_WEEKDAY, default=str(o[CONF_REFRESH_WEEKDAY])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=str(i), label=d) for i, d in enumerate(WEEKDAYS)],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_REFRESH_HOUR, default=o[CONF_REFRESH_HOUR]): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=23, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_INFLOW_BEFORE, default=o[CONF_INFLOW_BEFORE]): _minutes(360),
            vol.Required(CONF_OUTFLOW_FROM, default=o[CONF_OUTFLOW_FROM]): _minutes(480),
            vol.Required(CONF_OUTFLOW_TO, default=o[CONF_OUTFLOW_TO]): _minutes(600),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
