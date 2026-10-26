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
    CONF_BIG_ARTISTS, CONF_EXTRA_URLS, CONF_INFLOW_BEFORE, CONF_OUTFLOW_FROM, CONF_OUTFLOW_TO, CONF_REFRESH_HOUR,
    CONF_REFRESH_WEEKDAY, CONF_USE_EUROLEAGUE, CONF_USE_EVENT_PAGES, CONF_USE_OFFICIAL, CONF_USE_ROCKOL,
    CONF_USE_TICKETONE, DEFAULTS, DOMAIN, STALE_AFTER_DAYS, STORAGE_VERSION,
)
from .fetch import fetch_all, fetch_event_pages, prune_page_cache
from .models import Event
from .scoring import DayAssessment, assess_day
from .sources.forumnet import apply_page_times
from .windows import Window, build_windows

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
        self._page_cache: dict[str, dict] = {}     # url pagina evento -> {"letto", "programma"}
        self._pages_task = None

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
            self._page_cache = cached.get("pagine_evento", {})
            self.async_set_updated_data(ForumData(
                [Event.from_dict(e) for e in cached.get("events", [])],
                fetched_at, cached.get("per_source", {}), cached.get("errors", {}),
            ))
            if fetched_at and dt_util.utcnow() - fetched_at < timedelta(days=STALE_AFTER_DAYS):
                self._schedule()
                self._start_event_pages()          # riprende una lettura interrotta da un riavvio
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

        self._page_cache = prune_page_cache(self._page_cache, report.events)
        apply_page_times(report.events, self._page_cache)
        data = ForumData(report.events, dt_util.utcnow(), report.per_source, report.errors)
        await self._async_save(data)
        _LOGGER.info("Eventi aggiornati: %s (errori: %s)", report.per_source, report.errors or "nessuno")
        # Le pagine evento nuove (orari) si leggono dopo, in background: i sensori non aspettano
        self.hass.loop.call_soon(self._start_event_pages)
        return data

    async def _async_save(self, data: ForumData) -> None:
        await self._store.async_save({
            "fetched_at": data.fetched_at.isoformat() if data.fetched_at else None,
            "events": [e.to_dict() for e in data.events],
            "per_source": data.per_source,
            "errors": data.errors,
            "pagine_evento": self._page_cache,
        })

    # ------------------------------------------------------- pagine evento (orari)
    @callback
    def _start_event_pages(self) -> None:
        if not self.opt(CONF_USE_EVENT_PAGES) or not self.opt(CONF_USE_OFFICIAL) or not self.data:
            return
        if self._pages_task and not self._pages_task.done():
            return
        self._pages_task = self.config_entry.async_create_background_task(
            self.hass, self._async_read_event_pages(), f"{DOMAIN}_pagine_evento")

    async def _async_read_event_pages(self) -> None:
        # Ripete finché ci sono pagine nuove: una raccolta arrivata nel frattempo può aggiungerne
        tried: set[str] = set()
        while self.data:
            read = await fetch_event_pages(async_get_clientsession(self.hass), self.data.events,
                                           self._page_cache, self.today(), tried)
            if not read:
                return
            apply_page_times(self.data.events, self._page_cache)
            self.data.events.sort(key=lambda e: (e.start, e.venue, e.title))
            await self._async_save(self.data)
            self.async_update_listeners()

    # ------------------------------------------------------------- calcoli
    def assess(self, day: date) -> DayAssessment:
        events = self.data.events if self.data else []
        return assess_day(day, events, self.big_artists)

    def today(self) -> date:
        return dt_util.now().date()

    def windows(self, first_day: date, last_day: date) -> list[Window]:
        events = self.data.events if self.data else []
        return build_windows(
            events, first_day, last_day,
            inflow_before=int(self.opt(CONF_INFLOW_BEFORE)),
            outflow_from=int(self.opt(CONF_OUTFLOW_FROM)),
            outflow_to=int(self.opt(CONF_OUTFLOW_TO)),
        )

    def upcoming(self, days: int) -> list[DayAssessment]:
        start = self.today()
        return [a for a in (self.assess(start + timedelta(days=i)) for i in range(days)) if a.events]
