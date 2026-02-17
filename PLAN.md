# SatoraXagent — Piano di Implementazione

## Stack Tecnologico

- **Python 3.11+**
- **Playwright** + **playwright-stealth** — automazione browser anti-detection
- **APScheduler** — scheduling 2 sessioni/giorno con orari variabili
- **Flask** — backend API per il frontend dashboard
- **HTML/CSS/JS** (vanilla + Chart.js) — frontend dashboard leggero

---

## Struttura del Progetto

```
SatoraXagent/
├── config/
│   └── settings.yaml              # profili target, limiti, finestre orarie
├── src/
│   ├── __init__.py
│   ├── main.py                    # entry point + scheduler
│   ├── browser.py                 # setup Playwright + stealth + persistent context
│   ├── actions.py                 # logica core: search, navigate, follow
│   ├── anti_detection.py          # delay randomici, mouse movement, scrolling umano
│   ├── session_tracker.py         # tracking follow + log eventi in JSON
│   └── dashboard/
│       ├── app.py                 # Flask server per la dashboard
│       ├── templates/
│       │   └── index.html         # pagina principale dashboard
│       └── static/
│           ├── style.css
│           └── dashboard.js       # logica frontend + grafici Chart.js
├── data/
│   ├── browser_state/             # contesto persistente Playwright (cookies)
│   └── session_log.json           # log strutturato di tutte le sessioni
├── requirements.txt
└── README.md
```

---

## Flusso Operativo di una Sessione

### 1. Avvio browser
- Playwright apre un browser con contesto persistente (`data/browser_state/`)
- Il primo avvio è in modalità visibile: l'utente fa login manualmente (incluso 2FA)
- Le sessioni successive riutilizzano i cookies salvati — nessun login automatico

### 2. Per ciascuno dei 5 profili target
- Click sulla barra di ricerca
- Digita il nome profilo con ritmo umano (keystroke delay 80-250ms, pause casuali)
- Seleziona il profilo dai risultati di ricerca
- Attende caricamento pagina (wait randomico 2-5s)
- Click su "Followers"
- Click sulla tab "Verified Followers"
- Scorre la lista dall'alto verso il basso
- Per ogni profilo nella lista:
  - Se il bottone dice "Follow" → click, poi pausa 15-45s
  - Se dice "Following" → skip
- **Max 6 follow per profilo target**
- Se appare un messaggio di **rate limit** → l'agent si ferma immediatamente, logga l'evento, e non riprende fino alla prossima sessione schedulata

### 3. Chiusura
- Salva il contesto browser
- Scrive nel log: timestamp, follow effettuati (chi e da quale profilo target), eventuali errori/blocchi

---

## Limiti e Rate Limiting

| Parametro | Valore |
|---|---|
| Max follow per profilo target | 6 |
| Max sessioni al giorno | 2 |
| Pausa tra un follow e l'altro | 15-45s (randomico, distribuzione gaussiana) |
| Pausa tra un profilo target e l'altro | 60-180s (randomico) |

### Gestione Rate Limit di X
- Se X mostra un messaggio di rate limit (popup, banner, o pagina di errore), l'agent:
  1. Logga l'evento con timestamp, profilo corrente, e messaggio rilevato
  2. Chiude il browser in modo pulito
  3. **Non ritenta** — aspetta la prossima sessione schedulata
  4. La sessione successiva riparte normalmente

---

## Scheduling (2 volte al giorno)

Configurazione in `settings.yaml`:

```yaml
target_profiles:
  - "profile_handle_1"
  - "profile_handle_2"
  - "profile_handle_3"
  - "profile_handle_4"
  - "profile_handle_5"

limits:
  max_follows_per_profile: 6
  max_sessions_per_day: 2
  follow_delay_min: 15
  follow_delay_max: 45
  profile_switch_delay_min: 60
  profile_switch_delay_max: 180

schedule:
  session_1:
    window_start: "09:00"
    window_end: "12:00"
  session_2:
    window_start: "17:00"
    window_end: "21:00"
```

All'avvio, APScheduler calcola un orario randomico dentro ciascuna finestra per quel giorno. Ogni giorno gli orari cambiano.

---

## Strategia Anti-Detection

| Tecnica | Dettaglio |
|---|---|
| **playwright-stealth** | Maschera navigator.webdriver, chrome.runtime, e altri segnali di automazione |
| **Delay umani** | Distribuzione gaussiana tra azioni, non uniforme |
| **Typing realistico** | 80-250ms tra tasti, pause casuali più lunghe ogni 3-5 caratteri |
| **Scroll naturale** | Scroll incrementale con velocità variabile e pause |
| **Mouse Bézier** | Movimento cursore lungo curve di Bézier verso il target, non teleport |
| **Orari variabili** | Offset randomico dentro le finestre orarie ogni giorno |
| **Viewport realistico** | Risoluzione e user-agent coerenti con un dispositivo reale |
| **Contesto persistente** | Cookies mantenuti, nessun login ripetuto |
| **Captcha detection** | Se appare un captcha, l'agent si ferma e logga — non insiste |

---

## Frontend Dashboard

### Tecnologia
- **Flask** serve la dashboard su `http://localhost:5000`
- **Chart.js** per i grafici
- Dati letti da `data/session_log.json`

### Pagina principale — cosa mostra

#### 1. Riepilogo giornaliero (tabella)
Per ogni giorno:
- **Data**
- **Sessione 1**: orario di esecuzione, numero follow effettuati
- **Sessione 2**: orario di esecuzione, numero follow effettuati
- **Totale follow del giorno**
- **Stato**: OK / Bloccato (rate limit) / Errore
- **Dettaglio blocco**: se bloccato, motivo e a che punto si è fermato

#### 2. Grafico a barre — Follow giornalieri
- Asse X: giorni
- Asse Y: numero di follow
- Barre colorate per sessione 1 e sessione 2

#### 3. Log eventi recenti
- Lista scrollabile degli ultimi eventi (follow, errori, rate limit, captcha)
- Ogni evento con timestamp, tipo, e dettaglio

#### 4. Stato attuale
- Prossima sessione schedulata (data/ora)
- Ultima sessione completata
- Totale follow effettuati (oggi / settimana / totale)

### Formato del log (`session_log.json`)

```json
{
  "sessions": [
    {
      "date": "2026-02-17",
      "session_number": 1,
      "started_at": "2026-02-17T10:23:14",
      "ended_at": "2026-02-17T10:31:42",
      "status": "completed",
      "profiles_visited": [
        {
          "handle": "profile_handle_1",
          "follows": ["user_a", "user_b", "user_c"],
          "skipped": ["user_d"],
          "follow_count": 3
        }
      ],
      "total_follows": 12,
      "error": null
    },
    {
      "date": "2026-02-17",
      "session_number": 2,
      "started_at": "2026-02-17T18:47:03",
      "ended_at": "2026-02-17T18:48:15",
      "status": "rate_limited",
      "profiles_visited": [
        {
          "handle": "profile_handle_1",
          "follows": ["user_e"],
          "skipped": [],
          "follow_count": 1
        }
      ],
      "total_follows": 1,
      "error": "Rate limit detected on profile_handle_2 after 1 follow"
    }
  ]
}
```

---

## Piano di Implementazione (ordine dei file)

### Step 1 — Setup progetto
- `requirements.txt`
- `config/settings.yaml`
- Struttura directory

### Step 2 — Core anti-detection
- `src/anti_detection.py` — delay gaussiani, mouse Bézier, typing umano, scroll naturale

### Step 3 — Browser management
- `src/browser.py` — setup Playwright con stealth, contesto persistente, gestione lifecycle

### Step 4 — Session tracker
- `src/session_tracker.py` — lettura/scrittura `session_log.json`, tracking limiti

### Step 5 — Logica core
- `src/actions.py` — search profilo, naviga followers, tab verified, follow con limiti e rate limit detection

### Step 6 — Entry point + scheduler
- `src/main.py` — APScheduler con finestre orarie, orchestrazione sessione completa

### Step 7 — Dashboard backend
- `src/dashboard/app.py` — Flask API che legge il log e serve la pagina

### Step 8 — Dashboard frontend
- `src/dashboard/templates/index.html` — layout pagina
- `src/dashboard/static/style.css` — stile
- `src/dashboard/static/dashboard.js` — fetch dati + grafici Chart.js

### Step 9 — README
- Istruzioni di setup, primo avvio (login manuale), configurazione profili target
