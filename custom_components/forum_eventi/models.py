"""Modello dati condiviso: nessuna dipendenza da Home Assistant (testabile da solo)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime

VENUE_FORUM = "forum"
VENUE_REPOWER = "repower"

VENUE_LABELS = {VENUE_FORUM: "Unipol Forum", VENUE_REPOWER: "Teatro Repower"}

CAT_CONCERT = "concerto"
CAT_SPORT = "sport"
CAT_THEATRE = "teatro"
CAT_OTHER = "altro"


@dataclass
class Event:
    venue: str                      # VENUE_FORUM | VENUE_REPOWER
    title: str
    start: datetime                 # timezone-aware, Europe/Rome
    sources: list[str] = field(default_factory=list)
    url: str | None = None
    category: str = CAT_OTHER
    sold_out: bool = False
    times: list[str] = field(default_factory=list)   # orari distinti nella stessa giornata

    def __post_init__(self) -> None:
        if not self.times and self.start.hour != 0:
            self.times = [self.start.strftime("%H:%M")]

    @property
    def key(self) -> str:
        """Chiave di deduplica: stessa venue, stesso giorno, stesso titolo normalizzato."""
        return f"{self.venue}|{self.start.date().isoformat()}|{normalize_title(self.title)}"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        data = dict(data)
        data["start"] = datetime.fromisoformat(data["start"])
        return cls(**data)


_NOISE = re.compile(
    r"\b(tour|world|live|in concerto|concerto|20\d\d|unipol forum|teatro repower|"
    r"il musical|musical|assago|milano)\b"
)


def normalize_title(title: str) -> str:
    """Riduce il titolo a una forma confrontabile tra fonti diverse."""
    text = re.split(r"\s[-–—:|@]\s", title)[0]       # "Laura Pausini - Io canto tour" -> "Laura Pausini"
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = _NOISE.sub(" ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


PACKAGE_MARKERS = ("package", "vip pack", "pacchetto", "hospitality", "parcheggio", "parking")


def is_package(title: str, context: str = "") -> bool:
    """Le voci 'Package/VIP/parcheggio' non sono eventi in più: vanno scartate."""
    blob = f"{title} {context}".lower()
    return any(marker in blob for marker in PACKAGE_MARKERS)


def merge_events(events: list[Event]) -> list[Event]:
    """Unisce gli stessi eventi arrivati da fonti diverse, tenendo l'informazione più ricca."""
    merged: dict[str, Event] = {}
    for ev in events:
        current = merged.get(ev.key)
        if current is None:
            merged[ev.key] = Event(
                **{**ev.__dict__, "sources": list(ev.sources), "times": list(ev.times)}
            )
            continue
        for t in ev.times:
            if t not in current.times:
                current.times.append(t)
        current.times.sort()
        for src in ev.sources:
            if src not in current.sources:
                current.sources.append(src)
        current.sold_out = current.sold_out or ev.sold_out
        current.url = current.url or ev.url
        if current.category == CAT_OTHER:
            current.category = ev.category
        # Orario: prevale quello con l'ora valorizzata (00:00 = ora ignota)
        if ev.start.hour != 0 and (current.start.hour == 0 or ev.start < current.start):
            current.start = ev.start
    return sorted(merged.values(), key=lambda e: (e.start, e.venue, e.title))
