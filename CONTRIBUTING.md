# Contribuire

## Struttura

```
custom_components/forum_eventi/
├── sources/          parser delle singole fonti (forumnet = siti ufficiali, rockol, euroleague, jsonld, ticketone)
├── fetch.py          raccolta da tutte le fonti, timeout e pause tra le pagine
├── models.py         modello Event, normalizzazione dei titoli, unione dei doppioni
├── scoring.py        regole dell'indice di casino
├── windows.py        fasce di afflusso e deflusso
├── coordinator.py    aggiornamento settimanale, cache su disco, ricalcolo a mezzanotte
└── sensor.py, binary_sensor.py, calendar.py, button.py
tests/                test dei parser, dell'unione e del punteggio
tools/forum_probe.py  prova delle fonti fuori da Home Assistant
ha_config/            esempi di automazione e card
```

`sources/`, `fetch.py`, `models.py`, `scoring.py` e `windows.py` non dipendono da Home Assistant: si possono provare e testare da soli.

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

Il primo comando mostra eventi, punteggi e fasce dei prossimi giorni; legge anche tutte le pagine evento ufficiali (3-4 minuti, `--no-pagine` per saltarle). `--raw` salva l'HTML grezzo di ogni fonte (`raw_*.html`) e conta cosa trova: è il punto di partenza quando un sito cambia struttura. Su Windows usa `py` al posto di `python3`.

## Note sulle fonti

- **Siti ufficiali** (`sources/forumnet.py`): il blocco Calendario delle pagine è caricato da `/index.php?action=It_GruppoForum&m=calendario&p=<id>&pagine=<offset>&cateve=Tutti&mese=Tutti`, che risponde in JSON (`msg` con l'HTML delle righe, `pagine` con la paginazione). `pagine` è un offset a blocchi di 10: 1, 11, 21…
- **Pagine evento ufficiali** (`forumnet.parse_event_page`): gli orari sono in testo libero nei blocchi `.sommario` e `.testo` ("giovedì, venerdì ore 20.30 sabato ore 15.30 e ore 20.30", "lunedì 4 gennaio 2027 ore 20:30", "inizio spettacolo ore 19.00"). Il parser raggruppa giorni o date con gli orari che li seguono; vale solo "ore HH.MM", e "apertura porte" viene ignorato. Ogni pagina si legge una volta: la cache (url → programma) sta nello Store dell'integrazione. Le pagine del Forum di solito non hanno orari.
- **Unione dei doppioni** (`models.merge_events`): stessa venue e stesso giorno; titoli uguali o contenuti l'uno nell'altro, oppure due eventi sportivi da fonti diverse. Titolo e orari vengono dalla fonte con priorità più alta (`SOURCE_PRIORITY`).

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
