# Eventi Forum & Repower

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/PixelGoat8/ha-forum-eventi/actions/workflows/validate.yml/badge.svg)](https://github.com/PixelGoat8/ha-forum-eventi/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/PixelGoat8/ha-forum-eventi)](https://github.com/PixelGoat8/ha-forum-eventi/releases)

Integrazione per [Home Assistant](https://www.home-assistant.io/) che ti avvisa quando c'è un evento all'**Unipol Forum** (ex Forum di Assago) o al **Teatro Repower**, e stima quanto traffico e confusione porterà in zona.

Utile se abiti o lavori vicino a Milanofiori: una sera con un concerto sold out o con lo stesso artista tre sere di fila significa tangenziale bloccata, parcheggi pieni e M2 affollata. L'integrazione raccoglie il calendario una volta a settimana da più fonti e ogni giorno calcola un **indice di casino** da 0 a 100, con i motivi spiegati.

> *English summary: Home Assistant custom integration that tracks events at Unipol Forum and Teatro Repower (Assago, Milan) and computes a daily 0–100 "crowd/traffic" score. The UI and docs are in Italian.*

## Cosa fa

- Raccoglie gli eventi una volta a settimana da più fonti e unisce i doppioni.
- Ogni giorno assegna un livello: **nessuno**, **basso**, **medio**, **alto**, **estremo**.
- Calcola le fasce di **afflusso** e **deflusso** intorno a ogni spettacolo e le espone come sensori binari che si accendono e spengono da soli.
- Espone sensori, un calendario e un sensore binario "evento oggi" da usare in automazioni e dashboard.
- Non usa account, chiavi API o servizi cloud propri.

## Requisiti

- Home Assistant 2025.6 o successivo
- [HACS](https://hacs.xyz/) per l'installazione consigliata

## Installazione

### Con HACS (consigliata)

1. In HACS apri il menu **⋮ › Repository personalizzati**.
2. Aggiungi `https://github.com/PixelGoat8/ha-forum-eventi` con categoria **Integrazione**.
3. Cerca **Eventi Forum & Repower**, scaricala e riavvia Home Assistant.
4. Vai in **Impostazioni › Dispositivi e servizi › Aggiungi integrazione** e scegli **Eventi Forum & Repower**.

Gli aggiornamenti successivi compaiono in Home Assistant come quelli delle altre integrazioni HACS.

### Manuale

1. Scarica l'ultima [release](https://github.com/PixelGoat8/ha-forum-eventi/releases).
2. Copia la cartella `custom_components/forum_eventi` in `/config/custom_components/`.
3. Riavvia Home Assistant e aggiungi l'integrazione come al punto 4 sopra.

Alla prima configurazione l'integrazione scarica subito il calendario: ci vuole circa mezzo minuto, perché tra una pagina e l'altra rispetta le pause richieste dai siti. Poi, in background, legge una volta sola la pagina di ogni evento dei siti ufficiali per ricavarne gli orari: la prima volta sono circa 100 pagine e servono 3-4 minuti, nelle settimane successive solo gli eventi nuovi.

## Configurazione

Tutte le impostazioni sono in **Impostazioni › Dispositivi e servizi › Eventi Forum & Repower › Configura**.

| Opzione | Default | Descrizione |
|---|---|---|
| Siti ufficiali | attiva | Calendario completo di Unipol Forum e Teatro Repower: concerti, sport, spettacoli |
| Orari dalle pagine evento | attiva | Legge una volta la pagina di ogni evento ufficiale per ricavare gli orari (vedi [Fonti dei dati](#fonti-dei-dati)) |
| Rockol | attiva | Concerti all'Unipol Forum, come riserva |
| EuroLeague | attiva | Partite casalinghe dell'Olimpia Milano al Forum |
| TicketOne | spenta | Vedi [Limiti](#limiti) |
| Eventi "big" | vuoto | Nomi separati da virgola. Un nome da solo aggiunge +15 al punteggio; `nome=livello` impone un livello minimo alla giornata (`basso`, `medio`, `alto`, `estremo`). Una voce vale se tutte le sue parole compaiono nel titolo; se ne valgono più di una vince la più severa. Es.: `Laura Pausini, X Factor=alto, X Factor Finale=estremo` |
| Pagine extra | calendario Songkick del Forum | Una URL per riga. Sono valide le pagine che pubblicano eventi in formato [schema.org](https://schema.org/Event) (JSON-LD); vengono tenuti solo gli eventi al Forum o al Repower |
| Giorno e ora dell'aggiornamento | lunedì, 04:00 | Quando scaricare il calendario della settimana |
| Afflusso: minuti prima dell'inizio | 120 | La fascia di afflusso va da questi minuti prima dell'inizio fino all'inizio |
| Deflusso: da / fino a quanti minuti dopo l'inizio | 150 / 180 | La fascia di deflusso; la fine deve venire dopo l'inizio |

## Entità

| Entità | Stato | Attributi principali |
|---|---|---|
| `sensor.forum_casino_oggi` | `nessuno`, `basso`, `medio`, `alto`, `estremo` | `punteggio`, `motivi`, `riepilogo`, `eventi` |
| `sensor.forum_casino_domani` | come sopra | come sopra |
| `sensor.forum_punteggio_oggi` | 0–100 | |
| `sensor.forum_prossimo_evento` | titolo del prossimo evento | `venue`, `inizio`, `tra_giorni`, `livello_giornata` |
| `sensor.forum_prossimi_7_giorni` | giorni con eventi nella settimana | `giorni`: elenco con livello e riepilogo di ogni giorno |
| `binary_sensor.forum_evento_oggi` | `on` se oggi c'è almeno un evento | |
| `binary_sensor.forum_afflusso_in_corso` | `on` durante una fascia di afflusso | `attive`, `prossima`, `oggi` |
| `binary_sensor.forum_deflusso_in_corso` | `on` durante una fascia di deflusso | `attive`, `prossima`, `oggi` |
| `calendar.forum_eventi` | | tutti gli eventi, con il livello del giorno nel titolo |
| `button.forum_aggiorna_eventi` | | scarica subito il calendario |
| `sensor.forum_ultimo_aggiornamento` | data dell'ultima raccolta | `eventi_per_fonte`, `errori`, `fonti_vuote` |

Servizio: **`forum_eventi.aggiorna`**, equivalente al pulsante.

`sensor.forum_casino_oggi` e `sensor.forum_casino_domani` hanno anche l'attributo `finestre`, con tutte le fasce della giornata.

### Fasce di afflusso e deflusso

Per ogni spettacolo l'integrazione calcola due fasce: l'**afflusso**, da 2 ore prima dell'inizio fino all'inizio, e il **deflusso**, da 2 ore e mezza a 3 ore dopo l'inizio. Puoi cambiare questi valori nelle opzioni. Con più repliche nello stesso giorno ogni replica ha le sue fasce. Il deflusso di un evento serale può finire dopo mezzanotte: il sensore resta acceso fino alla fine della fascia.

Ogni fascia negli attributi ha questa forma:

```yaml
tipo: afflusso
inizio: "2026-11-06T18:30:00+01:00"
fine: "2026-11-06T20:30:00+01:00"
evento: Placebo
venue: Unipol Forum
orario: "20:30"
orario_stimato: false
```

Se nessuna fonte conosce l'orario, l'integrazione usa quello tipico (21:00 al Forum, 20:30 al Repower) e lo segnala con `orario_stimato: true`.

I sensori si accendono e si spengono esattamente all'inizio e alla fine delle fasce, senza interrogazioni periodiche.

I dati vengono salvati su disco: un riavvio di Home Assistant non riscarica nulla, e a mezzanotte i sensori passano al giorno nuovo senza fare richieste.

## Come si calcola l'indice di casino

Ogni evento del giorno contribuisce con una base, a cui si sommano dei bonus. Il totale è limitato a 100.

| Regola | Punti |
|---|---|
| Concerto al Forum | 45 |
| Evento sportivo al Forum | 30 |
| Altro evento al Forum | 35 |
| Spettacolo al Teatro Repower | 12 |
| Sold out | +15 al Forum, +5 al Repower |
| Stesso artista più sere di fila al Forum | +10 per ogni sera in più, fino a +20 |
| Evento nella lista "big" | +15, oppure il livello minimo indicato (`nome=alto` porta la giornata almeno a 55) |
| Più repliche nello stesso giorno | +5 per ogni replica in più |
| Forum e Repower nello stesso giorno | +10 |
| Giorno feriale con inizio serale, dalle 17:00 alle 21:00 (o orario non noto al Forum) | +10 |
| Venerdì o sabato | +5 |

| Livello | Punteggio |
|---|---|
| nessuno | 0 |
| basso | 1–29 |
| medio | 30–54 |
| alto | 55–74 |
| estremo | 75–100 |

**Esempi**
- Concerto sold out di martedì, seconda di tre serate: 45 + 20 + 15 + 10 = **90, estremo**
- Partita dell'Olimpia di martedì alle 20:30: 30 + 10 = **40, medio**
- Musical al Repower in settimana: 12 + 10 = **22, basso**

L'attributo `motivi` di `sensor.forum_casino_oggi` elenca le regole applicate, così puoi capire da dove viene ogni punteggio.

## Esempi d'uso

Nella cartella [`ha_config`](ha_config) trovi due esempi pronti da adattare.

- **[Notifica mattutina](ha_config/automazione_forum.yaml)**: alle 7:30, se oggi c'è un evento, manda una notifica con gli eventi, gli orari e il livello di domani. Sostituisci `notify.notify` con il tuo servizio. Funziona su iOS (i livelli alto ed estremo superano le modalità Full Immersion) e su Android (priorità alta e canale dedicato).
- **[Card per la dashboard](ha_config/card_panoramica.yaml)**: un avviso colorato secondo il livello, visibile solo nei giorni con eventi, più una card facoltativa con la settimana.

### Automazioni

Gli esempi usano `notify.notify`: sostituiscilo con il tuo servizio di notifica (vedi [sotto](#notifiche-su-più-dispositivi) per mandarle a più dispositivi). Si incollano in **Impostazioni › Automazioni › Crea automazione › Modifica in YAML**.

#### Mattina: casino oggi

```yaml
alias: "Forum: casino oggi"
triggers:
  - trigger: time
    at: "07:30:00"
conditions:
  - condition: state
    entity_id: sensor.forum_casino_oggi
    state: ["alto", "estremo"]
actions:
  - action: notify.notify
    data:
      title: "Forum: oggi casino {{ states('sensor.forum_casino_oggi') }}"
      message: "{{ state_attr('sensor.forum_casino_oggi', 'riepilogo') }}"
```

#### Sera prima: domani c'è un evento

Alle 20:00, se domani il livello è almeno medio, con l'ora in cui comincia l'afflusso.

```yaml
alias: "Forum: avviso per domani"
triggers:
  - trigger: time
    at: "20:00:00"
conditions:
  - condition: state
    entity_id: sensor.forum_casino_domani
    state: ["medio", "alto", "estremo"]
actions:
  - action: notify.notify
    data:
      title: "Forum: domani casino {{ states('sensor.forum_casino_domani') }}"
      message: >-
        {% set afflussi = state_attr('sensor.forum_casino_domani', 'finestre')
           | selectattr('tipo', 'eq', 'afflusso') | list %}
        {{ state_attr('sensor.forum_casino_domani', 'riepilogo') }}
        {%- if afflussi %}. Afflusso dalle {{ as_timestamp(afflussi[0].inizio) | timestamp_custom('%H:%M') }}
        {%- if afflussi[0].orario_stimato %} (orario stimato){% endif %}{% endif %}
```

#### Lunedì: la settimana

Il lunedì alle 8:00, dopo la raccolta settimanale (di default alle 4:17), un riepilogo dei giorni con eventi.

```yaml
alias: "Forum: riepilogo settimanale"
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: time
    weekday: mon
  - condition: numeric_state
    entity_id: sensor.forum_prossimi_7_giorni
    above: 0
actions:
  - action: notify.notify
    data:
      title: "Forum: {{ states('sensor.forum_prossimi_7_giorni') }} giorni con eventi questa settimana"
      message: |-
        {%- set nomi = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'] %}
        {%- for g in state_attr('sensor.forum_prossimi_7_giorni', 'giorni') %}
        {{ nomi[as_datetime(g.giorno).weekday()] }} {{ as_datetime(g.giorno).strftime('%d/%m') }}: {{ g.livello }} · {{ g.riepilogo }}
        {%- endfor %}
```

#### Quando comincia l'afflusso

```yaml
alias: "Forum: afflusso in corso"
triggers:
  - trigger: state
    entity_id: binary_sensor.forum_afflusso_in_corso
    to: "on"
actions:
  - action: notify.notify
    data:
      title: "Forum: afflusso in corso"
      message: >-
        {% set f = state_attr('binary_sensor.forum_afflusso_in_corso', 'attive')[0] %}
        {{ f.evento }} alle {{ f.orario }}{{ ' (orario stimato)' if f.orario_stimato }}:
        traffico fino alle {{ as_timestamp(f.fine) | timestamp_custom('%H:%M') }}
```

#### Esci di casa durante una fascia

Sostituisci `person.tu` con la tua persona.

```yaml
alias: "Forum: esci durante afflusso o deflusso"
triggers:
  - trigger: state
    entity_id: person.tu
    from: home
conditions:
  - condition: or
    conditions:
      - condition: state
        entity_id: binary_sensor.forum_afflusso_in_corso
        state: "on"
      - condition: state
        entity_id: binary_sensor.forum_deflusso_in_corso
        state: "on"
actions:
  - action: notify.notify
    data:
      title: "Forum: traffico in zona"
      message: >-
        {% set s = 'binary_sensor.forum_afflusso_in_corso' if is_state('binary_sensor.forum_afflusso_in_corso', 'on')
           else 'binary_sensor.forum_deflusso_in_corso' %}
        {% set f = state_attr(s, 'attive')[0] %}
        {{ f.tipo | capitalize }} per {{ f.evento }} ({{ f.venue }}) fino alle
        {{ as_timestamp(f.fine) | timestamp_custom('%H:%M') }}
```

### Notifiche su più dispositivi

Per mandare l'avviso a più telefoni o tablet scegliendo quali, crea un gruppo di notifica in `configuration.yaml` e usa `notify.telefoni` nell'automazione:

```yaml
notify:
  - platform: group
    name: telefoni
    services:
      - action: mobile_app_iphone      # i nomi esatti sono in Strumenti per sviluppatori › Azioni
      - action: mobile_app_pixel
```

Il gruppo inoltra anche i parametri `data` (link, priorità, livello iOS). Serve un riavvio di Home Assistant.

## Fonti dei dati

| Fonte | Cosa fornisce |
|---|---|
| [unipolforum.it](https://www.unipolforum.it/) e [teatrorepower.com](https://www.teatrorepower.com/) | Il calendario ufficiale: tutti gli eventi, comprese le partite di Serie A ed EuroLeague dell'Olimpia, la pallavolo e ogni replica a teatro. L'elenco non ha orari: li ricava dalla pagina di ogni evento, dove ci sono quasi sempre per il Repower e di rado per il Forum |
| [Rockol](https://www.rockol.it/) | Concerti all'Unipol Forum, senza orario |
| [Songkick](https://www.songkick.com/venues/4565288-unipol-forum) | Concerti all'Unipol Forum, quasi sempre con orario |
| [EuroLeague](https://www.euroleaguebasketball.net/) | Partite casalinghe dell'Olimpia Milano, con orario |

I siti ufficiali sono la fonte principale; le altre aggiungono gli orari e fanno da riserva se un sito non risponde. Quando più fonti riportano lo stesso evento, l'integrazione lo conta una volta sola e usa il titolo del sito ufficiale. Per l'orario l'ordine è: EuroLeague, poi la pagina evento ufficiale, poi Songkick.

Le richieste sono poche e distanziate: una raccolta a settimana, con le pause tra le pagine indicate nel `robots.txt` di ciascun sito, e solo su pagine che il `robots.txt` consente.

## Limiti

- **Orari**: per gli spettacoli al Repower arrivano dalle pagine evento ufficiali, per i concerti al Forum da Songkick, per l'EuroLeague dalla sua API. Le pagine del Forum di solito riportano solo la data, quindi le partite di Serie A e alcuni spettacoli restano senza orario: in quel caso le fasce usano l'orario tipico.
- **Sold out**: le fonti attive di solito non lo indicano, quindi quel bonus scatta raramente.
- **TicketOne**: blocca le richieste che non arrivano da un browser. L'opzione esiste ma è spenta, e di solito fallisce dopo 30 secondi.
- I dati dipendono da siti di terze parti e possono essere incompleti o cambiare senza preavviso. Usa l'indice come indicazione, non come certezza.

## Risoluzione dei problemi

**Mancano eventi o i sensori sono vuoti.** Apri `sensor.forum_ultimo_aggiornamento` e guarda gli attributi:
- `errori`: la fonte non era raggiungibile; di solito si risolve al giro successivo o premendo **Aggiorna eventi**.
- `fonti_vuote`: la fonte ha risposto ma non sono stati trovati eventi. Probabilmente il sito ha cambiato struttura: [apri una issue](https://github.com/PixelGoat8/ha-forum-eventi/issues).

**Log più dettagliati.** Aggiungi in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.forum_eventi: info
```

## Contribuire

Segnalazioni e proposte sono benvenute nelle [issue](https://github.com/PixelGoat8/ha-forum-eventi/issues). Per sviluppo, test e strumenti di diagnosi vedi [CONTRIBUTING.md](CONTRIBUTING.md).

## Avvertenze

Progetto personale e non ufficiale, senza alcun legame con Unipol Forum, Teatro Repower, Live Nation, TicketOne, Rockol, Songkick o EuroLeague. I nomi citati appartengono ai rispettivi proprietari.

## Licenza

[MIT](LICENSE)
