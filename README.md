# Eventi Forum & Repower (Home Assistant)

Custom integration che una volta a settimana raccoglie gli eventi dell'**Unipol Forum** e del **Teatro Repower** di Assago da più fonti, li unisce, e calcola ogni giorno un **indice di casino** (0-100) con i motivi in chiaro.

## Fonti

| Fonte | Default | Cosa copre | Come |
|---|---|---|---|
| Rockol – pagina concerti Unipol Forum | attiva | concerti al Forum (senza orario) | HTML paginato `?pag=N`; data e venue lette dall'URL di ogni evento; 5 s tra le pagine come chiede il loro robots.txt |
| API EuroLeague | attiva | partite casalinghe dell'Olimpia al Forum | JSON ufficiale `api-live.euroleague.net` |
| Songkick – calendario Unipol Forum | attiva (pagina extra) | concerti, quasi sempre con orario | eventi schema.org JSON-LD della pagina (verificato: ~40 eventi) |
| Pagine extra (opzioni) | — | aggregatori/biglietterie a tua scelta | JSON-LD, filtrati per location Forum/Repower |
| TicketOne – venue Forum e Repower | **spenta** | tutto | la loro protezione anti-bot lascia appese le richieste non da browser; tenuta solo come opzione |

Gli stessi eventi da fonti diverse vengono uniti (stessa venue, stesso giorno, titolo normalizzato, anche "Pooh @ Unipol Forum" = "Pooh"); le voci "Package/VIP pack" vengono scartate. Quando Rockol non dà l'orario e un'altra fonte sì, vince l'orario noto.

**Non coperti**
- `unipolforum.it` e `teatrorepower.com`: il loro `robots.txt` vieta l'accesso automatico.
- Teatro Repower: senza TicketOne non c'è ancora una fonte stabile; si può aggiungere una pagina JSON-LD dalle opzioni.
- Serie A di basket (LBA): nessuna API pubblica verificata.

## Indice di casino

| Regola | Punti |
|---|---|
| Concerto al Forum / sport al Forum / altro al Forum | 45 / 30 / 35 |
| Spettacolo al Repower | 12 |
| Sold out | +15 Forum, +5 Repower |
| Stesso artista più sere di fila al Forum | +10 per sera in più (max +20) |
| Artista nella tua lista "big" | +15 |
| Più repliche nello stesso giorno | +5 per replica |
| Forum e Repower lo stesso giorno | +10 |
| Feriale con inizio entro le 21:00 (o orario ignoto al Forum) | +10 |
| Venerdì o sabato | +5 |

Livelli: **nessuno** 0 · **basso** 1-29 · **medio** 30-54 · **alto** 55-74 · **estremo** 75+.
Esempio: Pausini, martedì, sera centrale di tre, sold out → 45 + 20 + 15 + 10 = **90, estremo**. Olimpia di martedì alle 20:30 → 40, medio. Musical al Repower in settimana → 22, basso.
Le regole sono in `custom_components/forum_eventi/scoring.py`.

## Entità

| Entità | Stato | Attributi utili |
|---|---|---|
| `sensor.forum_casino_oggi` | nessuno…estremo | `punteggio`, `motivi`, `riepilogo`, `eventi` |
| `sensor.forum_casino_domani` | idem | idem |
| `sensor.forum_punteggio_oggi` | 0-100 | |
| `sensor.forum_prossimo_evento` | titolo | `inizio`, `tra_giorni`, `livello_giornata` |
| `sensor.forum_prossimi_7_giorni` | giorni con eventi | `giorni` (lista per card/stampante) |
| `binary_sensor.forum_evento_oggi` | on/off | |
| `calendar.forum_eventi` | | eventi col livello nel titolo |
| `button.forum_aggiorna_eventi` | | forza la raccolta |
| `sensor.forum_ultimo_aggiornamento` (diagnostica) | timestamp | `eventi_per_fonte`, `errori`, `fonti_vuote` |

Servizio: `forum_eventi.aggiorna`.

La raccolta avviene una volta a settimana (default lunedì alle 04:17, modificabile dalle opzioni) e i dati restano su disco: un riavvio di HA non riscarica nulla. A mezzanotte i sensori ricalcolano "oggi" senza rete.

## Installazione

### Con HACS (consigliato: gli aggiornamenti arrivano da soli)
1. HACS › menu ⋮ › **Repository personalizzati** › URL `https://github.com/PixelGoat8/ha-forum-eventi`, categoria **Integrazione**.
2. Cerca **Eventi Forum & Repower** in HACS, scarica, riavvia Home Assistant.
3. **Impostazioni › Dispositivi e servizi › Aggiungi integrazione › Eventi Forum & Repower**.

Quando esce una nuova release, HACS la segnala tra gli aggiornamenti di Home Assistant.

### A mano
Copia `custom_components/forum_eventi` in `/config/custom_components/`, riavvia, poi aggiungi l'integrazione come sopra.

### Dopo l'installazione
- Dalle **opzioni**: lista artisti big, pagine extra, giorno/ora dell'aggiornamento.
- Automazione: `ha_config/automazione_forum.yaml` (cambia `notify.mobile_app_iphone`).
- Card: `ha_config/card_panoramica.yaml` nella vista Panoramica.

## Pubblicare una nuova versione
1. Aggiorna `version` in `custom_components/forum_eventi/manifest.json` (es. `0.2.1`).
2. Commit e push su `main`.
3. Crea la release: da riga di comando `git tag v0.2.1 && git push --tags`, oppure da GitHub › **Releases › Draft a new release** con tag `v0.2.1` (lo crea lei).
4. L'action **Release** controlla che tag e manifest coincidano (e crea la release se hai usato solo il tag); HACS la propone come aggiornamento.

## Diagnosi fuori da HA

```bash
pip install aiohttp beautifulsoup4
python3 tools/forum_probe.py --giorni 30 --big "Laura Pausini"
python3 tools/forum_probe.py --raw        # salva l'HTML grezzo delle fonti e conta cosa trova
```

Se `sensor.forum_ultimo_aggiornamento` mostra una fonte in `fonti_vuote`, il sito ha cambiato struttura: lancia `--raw` e controlla l'HTML salvato.

## Test

```bash
pytest tests          # parser, dedup, punteggio (senza HA) — gira anche in CI a ogni push
python3 tests/smoke_ha.py   # setup completo in un'istanza HA reale, rete simulata
```
