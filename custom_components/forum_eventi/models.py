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


# Quale fonte "vince" su titolo, categoria e orari quando più fonti descrivono lo stesso evento
SOURCE_PRIORITY = {"ufficiale": 0, "songkick.com": 1, "euroleague": 2, "rockol": 3, "ticketone": 4}


def _priority(ev: Event) -> int:
    return min((SOURCE_PRIORITY.get(s, 5) for s in ev.sources), default=9)


def _squash(title: str) -> str:
    """'Artie 5ive' e 'Artie5ive' -> 'artie5ive'."""
    return normalize_title(title).replace(" ", "")


def _same_event(a: Event, b: Event) -> bool:
    """a e b sono già nella stessa venue e nello stesso giorno."""
    sa, sb = _squash(a.title), _squash(b.title)
    # Una sola serata per volta al Forum: Rockol ha una pagina per artista (spalla, DJ di una
    # serata a più nomi), quindi "Megadeth", "Testament" e "Black Label Society" sono lo stesso
    # concerto. Il sito ufficiale ha una riga per serata: due sue righe restano distinte.
    if (a.venue == VENUE_FORUM and CAT_SPORT not in (a.category, b.category)
            and not ("ufficiale" in a.sources and "ufficiale" in b.sources)):
        return True
    if set(a.sources) & set(b.sources):
        return sa == sb                      # stessa fonte: solo i doppioni esatti (pagine sovrapposte)
    if sa and sb and (sa in sb or sb in sa) and min(len(sa), len(sb)) >= 3:
        return True
    # Una sola partita per volta al Forum: titoli diversi tra fonti ("Eurolega: Armani Olimpia
    # Milano vs ..." e "Olimpia Milano – ... (EuroLeague)") sono la stessa partita.
    return a.category == CAT_SPORT and b.category == CAT_SPORT


def _absorb(into: Event, ev: Event) -> None:
    for src in ev.sources:
        if src not in into.sources:
            into.sources.append(src)
    into.sold_out = into.sold_out or ev.sold_out
    if _priority(ev) < _priority(into) or into.url is None:
        into.url = ev.url or into.url
    if _priority(ev) < _priority(into):
        into.title = ev.title
        if ev.category != CAT_OTHER:
            into.category = ev.category
    elif into.category == CAT_OTHER:
        into.category = ev.category
    # Orari: non si sommano tra fonti diverse (20:30 su una e 20:45 sull'altra non sono due
    # repliche). Si prendono quelli della fonte più affidabile che ne ha.
    if ev.times and not into.times:
        into.times = list(ev.times)
        into.start = ev.start
    elif ev.times and into.times and set(ev.sources) == set(into.sources):
        into.times = sorted(set(into.times) | set(ev.times))
        into.start = min(into.start, ev.start)


def merge_events(events: list[Event]) -> list[Event]:
    """Unisce gli stessi eventi arrivati da fonti diverse (o ripetuti nella stessa fonte)."""
    # Le fonti più affidabili per prime: il loro titolo fa da riferimento
    ordered = sorted(events, key=lambda e: (_priority(e), e.start))
    groups: dict[tuple[str, str], list[Event]] = {}
    for ev in ordered:
        bucket = groups.setdefault((ev.venue, ev.start.date().isoformat()), [])
        target = next((m for m in bucket if _same_event(m, ev)), None)
        if target is None:
            bucket.append(Event(**{**ev.__dict__, "sources": list(ev.sources), "times": list(ev.times)}))
        else:
            _absorb(target, ev)
    merged = [e for bucket in groups.values() for e in bucket]
    return sorted(merged, key=lambda e: (e.start, e.venue, e.title))
