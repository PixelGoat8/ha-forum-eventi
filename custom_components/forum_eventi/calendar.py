"""calendar.forum_eventi: tutti gli eventi nel calendario di HA, col livello nel titolo."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ForumConfigEntry
from .entity import ForumEntity
from .models import VENUE_LABELS, Event

DEFAULT_DURATION = timedelta(hours=3)


async def async_setup_entry(hass: HomeAssistant, entry: ForumConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([ForumCalendar(entry.runtime_data)])


class ForumCalendar(ForumEntity, CalendarEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "eventi")

    def _to_cal(self, ev: Event) -> CalendarEvent:
        level = self.coordinator.assess(ev.start.date()).level
        if ev.start.hour == 0:   # orario sconosciuto -> evento di tutto il giorno
            start, end = ev.start.date(), ev.start.date() + timedelta(days=1)
        else:
            start, end = ev.start, ev.start + DEFAULT_DURATION
        desc = [f"Orari: {', '.join(ev.times) or 'n.d.'}", f"Fonti: {', '.join(ev.sources)}"]
        if ev.sold_out:
            desc.insert(0, "SOLD OUT")
        if ev.url:
            desc.append(ev.url)
        return CalendarEvent(
            start=start, end=end,
            summary=f"[{level}] {ev.title}",
            location=VENUE_LABELS[ev.venue],
            description="\n".join(desc),
        )

    @property
    def event(self) -> CalendarEvent | None:
        today = self.coordinator.today()
        events = self.coordinator.data.events if self.coordinator.data else []
        nxt = next((e for e in events if e.start.date() >= today), None)
        return self._to_cal(nxt) if nxt else None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime,
                               end_date: datetime) -> list[CalendarEvent]:
        events = self.coordinator.data.events if self.coordinator.data else []
        return [
            self._to_cal(e) for e in events
            if start_date - DEFAULT_DURATION <= e.start <= end_date
        ]
