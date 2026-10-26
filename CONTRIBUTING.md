# Contribuire

## Struttura

```
custom_components/forum_eventi/
├── sources/          parser delle singole fonti (rockol, euroleague, jsonld, ticketone)
├── fetch.py          raccolta da tutte le fonti, timeout e pause tra le pagine
├── models.py         modello Event, normalizzazione dei titoli, unione dei doppioni
├── scoring.py        regole dell'indice di casino
├── coordinator.py    aggiornamento settimanale, cache su disco, ricalcolo a mezzanotte
└── sensor.py, binary_sensor.py, calendar.py, button.py
tests/                test dei parser, dell'unione e del punteggio
tools/forum_probe.py  prova delle fonti fuori da Home Assistant
ha_config/            esempi di automazione e card
```

`sources/`, `fetch.py`, `models.py` e `scoring.py` non dipendono da Home Assistant: si possono provare e testare da soli.

## Test

```bash
pip install pytest aiohttp beautifulsoup4
pytest tests
```

`tests/smoke_ha.py` installa l'integrazione in un'istanza Home Assistant reale con la rete simulata (richiede il pacchetto `homeassistant`):

```bash
python3 tests/smoke_ha.py
```

A ogni push l'action **Validate** esegue i test e i controlli di hassfest e HACS.

## Provare le fonti dal vivo

```bash
pip install aiohttp beautifulsoup4 tzdata
python3 -X utf8 tools/forum_probe.py --giorni 30 --big "Laura Pausini"
python3 -X utf8 tools/forum_probe.py --raw
```

Il primo comando mostra eventi e punteggi dei prossimi giorni. `--raw` salva l'HTML grezzo di ogni fonte (`raw_*.html`) e conta cosa trova: è il punto di partenza quando un sito cambia struttura. Su Windows usa `py` al posto di `python3`.

## Aggiungere una fonte

1. Scrivi un parser in `sources/` che restituisca una lista di `Event`.
2. Collegalo in `fetch.py` e, se serve, aggiungi un'opzione in `const.py` e `config_flow.py`.
3. Salva una pagina reale ridotta in `tests/fixtures/` e aggiungi un test.
4. Rispetta il `robots.txt` del sito e le eventuali pause richieste.

## Pubblicare una release (manutentore)

1. Aggiorna `version` in `custom_components/forum_eventi/manifest.json`, es. `0.2.1`.
2. Commit e push su `main`.
3. Crea la release con tag `v0.2.1`, da GitHub (**Releases › Draft a new release**) oppure con `git tag v0.2.1 && git push --tags`.

L'action **Release** controlla che il tag coincida con la versione del manifest e crea la release se manca. HACS la propone come aggiornamento agli utenti.
