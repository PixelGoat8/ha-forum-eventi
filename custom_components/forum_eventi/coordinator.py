"""Coordinator: scarica una volta a settimana, conserva su disco, ricalcola ogni giorno."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BIG_ARTISTS, CONF_EXTRA_URLS, CONF_REFRESH_HOUR, CONF_REFRESH_WEEKDAY,
    CONF_USE_EUROLEAGUE, CONF_USE_OFFICIAL, CONF_USE_ROCKOL, CONF_USE_TICKETONE, DEFAULTS, DOMAIN, STALE_AFTER_DAYS,
    STORAGE_VERSION,
)
from .fetch import fetch_all
from .models import Event
from .scoring import DayAssessment, assess_day

_LOGGER = logging.getLogger(__name__)


class ForumData:
    """Istantanea dei dati: eventi + metadati dell'ultima raccolta."""

    def __init__(self, events: list[Event], fetched_at: datetime | None,
                 per_source: dict[str, int], errors: dict[str, str]) -> None:
        self.events = events
        self.fetched_at = fetched_at
        self.per_source = per_source
        self.errors = errors


class ForumCoordinator(DataUpdateCoordinator[ForumData]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._unsubs: list = []

    # ------------------------------------------------------------- opzioni
    def opt(self, key: str):
        return self.config_entry.options.get(key, DEFAULTS[key])

    @property
    def big_artists(self) -> list[str]:
        return [a.strip() for a in str(self.opt(CONF_BIG_ARTISTS)).split(",") if a.strip()]

    @property
    def extra_urls(self) -> list[str]:
        return [u.strip() for u in str(self.opt(CONF_EXTRA_URLS)).splitlines() if u.strip().startswith("http")]

    # ---------------------------------------------------------- ciclo di vita
    async def async_setup(self) -> None:
        """Carica la cache; scarica solo se manca o è vecchia. Poi pianifica."""
        cached = await self._store.async_load()
        if cached:
            fetched_at = dt_util.parse_datetime(cached.get("fetched_at") or "")
            self.async_set_updated_data(ForumData(
                [Event.from_dict(e) for e in cached.get("events", [])],
                fetched_at, cached.get("per_source", {}), cached.get("errors", {}),
            ))
            if fetched_at and dt_util.utcnow() - fetched_at < timedelta(days=STALE_AFTER_DAYS):
                self._schedule()
                return
            await self.async_refresh()          # cache vecchia: se fallisce restano i dati in cache
        else:
            await self.async_config_entry_first_refresh()   # prima volta: se fallisce, HA ritenta
        self._schedule()

    def _schedule(self) -> None:
        self._unsubs.append(async_track_time_change(
            self.hass, self._weekly_tick, hour=int(self.opt(CONF_REFRESH_HOUR)), minute=17, second=0,
        ))
        # A mezzanotte lo "oggi" cambia: ricalcolo senza riscaricare
        self._unsubs.append(async_track_time_change(self.hass, self._daily_tick, hour=0, minute=0, second=10))

    @callback
    def _weekly_tick(self, now: datetime) -> None:
        if now.weekday() == int(self.opt(CONF_REFRESH_WEEKDAY)):
            self.hass.async_create_task(self.async_refresh())

    @callback
    def _daily_tick(self, _now: datetime) -> None:
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await super().async_shutdown()

    # ------------------------------------------------------------- raccolta
    async def _async_update_data(self) -> ForumData:
        today = dt_util.now().date()
        report = await fetch_all(
            async_get_clientsession(self.hass), today,
            use_ticketone=bool(self.opt(CONF_USE_TICKETONE)),
            use_official=bool(self.opt(CONF_USE_OFFICIAL)),
            use_rockol=bool(self.opt(CONF_USE_ROCKOL)),
            use_euroleague=bool(self.opt(CONF_USE_EUROLEAGUE)),
            extra_urls=self.extra_urls,
        )
        if not report.per_source:
            # tutte le fonti in errore: tengo i dati vecchi se ci sono
            if self.data:
                self.data.errors = report.errors
                return self.data
            raise UpdateFailed(f"Nessuna fonte raggiungibile: {report.errors}")

        data = ForumData(report.events, dt_util.utcnow(), report.per_source, report.errors)
        await self._store.async_save({
            "fetched_at": data.fetched_at.isoformat(),
            "events": [e.to_dict() for e in data.events],
            "per_source": data.per_source,
            "errors": data.errors,
        })
        _LOGGER.info("Eventi aggiornati: %s (errori: %s)", report.per_source, report.errors or "nessuno")
        return data

    # ------------------------------------------------------------- calcoli
    def assess(self, day: date) -> DayAssessment:
        events = self.data.events if self.data else []
        return assess_day(day, events, self.big_artists)

    def today(self) -> date:
        return dt_util.now().date()

    def upcoming(self, days: int) -> list[DayAssessment]:
        start = self.today()
        return [a for a in (self.assess(start + timedelta(days=i)) for i in range(days)) if a.events]
