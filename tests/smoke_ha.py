"""Smoke test dentro un vero Home Assistant (senza rete): config flow, entità, stati, opzioni.

Uso: python3 tests/smoke_ha.py   (richiede il pacchetto homeassistant installato)
"""
import asyncio
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Rome")


async def main() -> int:
    from homeassistant import config_entries, loader
    from homeassistant.core import HomeAssistant
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    cfg = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT / "custom_components", cfg / "custom_components")
    hass = HomeAssistant(str(cfg))
    await hass.config.async_set_time_zone("Europe/Rome")
    hass.config.language = "it"
    hass.config.skip_pip = True
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    from homeassistant.auth import auth_manager_from_config
    from homeassistant.helpers import (
        area_registry, category_registry, device_registry, entity_registry,
        floor_registry, issue_registry, label_registry, translation,
    )
    for reg in (label_registry, floor_registry, area_registry, category_registry,
                device_registry, entity_registry, issue_registry):
        await reg.async_load(hass)
    hass.auth = await auth_manager_from_config(hass, [], [])
    await translation.async_load(hass) if hasattr(translation, "async_load") else None
    await async_setup_component(hass, "homeassistant", {})
    await hass.async_start()

    from custom_components.forum_eventi.fetch import FetchReport
    from custom_components.forum_eventi.models import CAT_SPORT, VENUE_FORUM, VENUE_REPOWER, Event

    today = dt_util.now().date()
    def at(days, h, m=0):
        d = today + timedelta(days=days)
        return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)

    fake = FetchReport(
        events=[
            Event(VENUE_FORUM, "Laura Pausini", at(0, 21), ["ticketone"], sold_out=True, category="concerto"),
            Event(VENUE_FORUM, "Laura Pausini", at(1, 21), ["ticketone"], category="concerto"),
            Event(VENUE_REPOWER, "Grease", at(0, 20, 30), ["ticketone"], category="teatro"),
            Event(VENUE_FORUM, "Olimpia Milano – Real Madrid (EuroLeague)", at(5, 20, 30), ["euroleague"], category=CAT_SPORT),
        ],
        per_source={"ticketone_forum": 2, "ticketone_repower": 1, "euroleague": 1},
    )

    async def fake_fetch(*a, **k):
        return fake

    errors = 0
    with patch("custom_components.forum_eventi.coordinator.fetch_all", fake_fetch), \
         patch("custom_components.forum_eventi.coordinator.async_get_clientsession", lambda h: None):
        r = await hass.config_entries.flow.async_init("forum_eventi", context={"source": config_entries.SOURCE_USER})
        assert r["type"] == "form", r
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        assert r["type"] == "create_entry", r
        await hass.async_block_till_done()

        states = {s.entity_id: s for s in hass.states.async_all() if "forum" in s.entity_id}
        for eid, s in sorted(states.items()):
            print(f"{eid:42} {s.state}")
        expected = ["sensor.forum_casino_oggi", "sensor.forum_punteggio_oggi", "sensor.forum_casino_domani",
                    "sensor.forum_prossimo_evento", "sensor.forum_prossimi_7_giorni",
                    "sensor.forum_ultimo_aggiornamento", "binary_sensor.forum_evento_oggi",
                    "calendar.forum_eventi", "button.forum_aggiorna_eventi"]
        for eid in expected:
            if eid not in states:
                print("MANCANTE:", eid); errors += 1
        oggi = hass.states.get("sensor.forum_casino_oggi")
        print("motivi:", oggi.attributes.get("motivi"))
        if oggi.state not in ("alto", "estremo"):
            print("livello inatteso", oggi.state); errors += 1

        # opzioni: lista big + ricarica
        entry = hass.config_entries.async_entries("forum_eventi")[0]
        r = await hass.config_entries.options.async_init(entry.entry_id)
        r = await hass.config_entries.options.async_configure(r["flow_id"], {
            "use_ticketone": True, "use_euroleague": True, "big_artists": "Laura Pausini",
            "extra_urls": "", "refresh_weekday": "0", "refresh_hour": 4})
        assert r["type"] == "create_entry", r
        await hass.async_block_till_done()
        print("dopo opzioni, punteggio oggi:", hass.states.get("sensor.forum_punteggio_oggi").state)

        # calendario
        cal = await hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": "calendar.forum_eventi", "duration": {"days": 7}},
            blocking=True, return_response=True)
        print("calendario:", [(e["start"], e["summary"]) for e in cal["calendar.forum_eventi"]["events"]])

        await hass.services.async_call("button", "press", {"entity_id": "button.forum_aggiorna_eventi"}, blocking=True)
        await hass.services.async_call("forum_eventi", "aggiorna", {}, blocking=True)

        # Render dei template di automazione e card con i dati veri
        import yaml
        from homeassistant.helpers.template import Template
        auto = yaml.safe_load((ROOT / "ha_config/automazione_forum.yaml").read_text())
        vars_ = {}
        for k, v in auto["actions"][0]["variables"].items():
            vars_[k] = Template(v, hass).async_render(vars_, parse_result=False) if isinstance(v, str) else v
            if k == "a":
                vars_[k] = hass.states.get("sensor.forum_casino_oggi").attributes
        notif = auto["actions"][1]["data"]
        print("--- PUSH ---")
        print(Template(notif["title"], hass).async_render(vars_, parse_result=False))
        print(Template(notif["message"], hass).async_render(vars_, parse_result=False))
        print(Template(notif["data"]["push"]["interruption-level"], hass).async_render(vars_, parse_result=False))
        for card in yaml.safe_load((ROOT / "ha_config/card_panoramica.yaml").read_text()):
            print("--- CARD ---")
            print(Template(card["content"], hass).async_render(parse_result=False))

    await hass.async_stop(force=True)
    print("ERRORI:", errors)
    return errors


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
