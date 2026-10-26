"""Costanti dell'integrazione."""
DOMAIN = "forum_eventi"
NAME = "Eventi Forum & Repower"

CONF_USE_TICKETONE = "use_ticketone"
CONF_USE_OFFICIAL = "use_official"
CONF_USE_ROCKOL = "use_rockol"
CONF_USE_EUROLEAGUE = "use_euroleague"
CONF_EXTRA_URLS = "extra_urls"
CONF_BIG_ARTISTS = "big_artists"
CONF_REFRESH_WEEKDAY = "refresh_weekday"   # 0 = lunedì
CONF_REFRESH_HOUR = "refresh_hour"

DEFAULTS = {
    # TicketOne ha una protezione anti-bot che lascia appese le richieste: spento di default
    CONF_USE_TICKETONE: False,
    CONF_USE_OFFICIAL: True,
    CONF_USE_ROCKOL: True,
    CONF_USE_EUROLEAGUE: True,
    CONF_EXTRA_URLS: "https://www.songkick.com/venues/4565288-unipol-forum/calendar",
    CONF_BIG_ARTISTS: "",
    CONF_REFRESH_WEEKDAY: 0,
    CONF_REFRESH_HOUR: 4,
}

STORAGE_VERSION = 1
STALE_AFTER_DAYS = 8          # se all'avvio i dati sono più vecchi, riscarica subito
SERVICE_REFRESH = "aggiorna"
