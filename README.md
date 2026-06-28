# SteamAgent

Raccolta automatica di **tutti i dati del tuo account Steam developer/partner**
— vendite, wishlist, traffico, marketing, giocatori, recensioni, tempo di gioco —
con **dashboard** di visualizzazione e base per elaborazioni LLM.

Steam espone pochi dati via API: alcuni si scaricano in CSV dai portali partner,
altri vanno letti dall'HTML/JS delle pagine. SteamAgent automatizza login e
raccolta e salva tutto in un database locale (SQLite, o Postgres in produzione).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Usa i **tuoi** dati dal **tuo** portale partner: raccolta legittima. Niente
> scraping di terze parti (es. SteamDB), rate limit gentili.

## Cosa raccoglie

| Dataset | Contenuto |
|---|---|
| **Vendite** | unità + ricavi netti per prodotto/paese (mensile) |
| **Wishlist** | aggiunte/rimozioni/attivazioni (giornaliero) |
| **Marketing** | visite & impression per sorgente (storia completa) + ownership + top paesi |
| **Giocatori** | DAU + picco di utenti concorrenti (giornaliero) |
| **Playtime** | tempo medio/mediano + distribuzione lifetime (snapshot) |
| **Recensioni** | testo + voto + lingua (API pubblica) |
| **Traffico** | breakdown dettagliato visite/impression per sorgente (giornaliero) |

Più una **dashboard Streamlit** con panoramica e una pagina per dataset.

## Requisiti

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/)
- Un **account Steam dedicato al bot** (vedi [Prerequisito](#prerequisito-account-bot))

## Avvio rapido

```bash
git clone <repo-url> SteamAgent && cd SteamAgent
uv sync                                  # crea .venv e installa le dipendenze
uv run playwright install chromium       # browser per il login al portale

uv run steam-agent setup                 # wizard: credenziali, login, partner, giochi, DB
uv run steam-agent collect-all           # scarica tutti i dati
uv run streamlit run dashboard/app.py    # dashboard su http://localhost:8501
```

Il comando **`setup`** è interattivo: chiede le credenziali del bot, apre il
browser per il login (gestisce la conferma email e il codice 2FA), **rileva da
solo** il tuo `partner_id` e il nome studio, scarica la lista giochi e inizializza
il database. In qualsiasi momento, **`uv run steam-agent doctor`** verifica che
tutti i prerequisiti siano a posto.

## Prerequisito: account bot

1. Crea un **account Steam dedicato** (non il tuo personale) e invitalo nel tuo
   Steamworks con permesso di **sola lettura dei report** (non admin). Isola le credenziali.
2. **2FA / Steam Guard** — due strade:
   - **Semplice (locale):** non configurare nulla. A ogni `login` inserisci a mano
     il codice Steam Guard (dall'app mobile o dall'email).
   - **Automatico (server non presidiato):** estrai lo `shared_secret`
     dell'authenticator con [steamguard-cli](https://github.com/dyc3/steamguard-cli)
     o Steam Desktop Authenticator e mettilo in `STEAM_SHARED_SECRET`: il login userà
     il TOTP, adatto a uno scheduler.
3. *(opzionale)* una **publisher Web API key** dello Steamworks → `STEAM_PUBLISHER_API_KEY`.

> Il primo login conviene farlo con interfaccia grafica (lo fa `setup`, oppure
> `login --headed`): Steam può chiedere una conferma "nuovo dispositivo" via email.
> Dopo, la sessione è salvata in `data/storage_state.json` e i login successivi
> sono automatici.

## Comandi

```bash
uv run steam-agent setup             # wizard di primo avvio
uv run steam-agent doctor            # verifica i prerequisiti
uv run steam-agent collect-all       # aggiorna TUTTI i dataset in sequenza
uv run steam-agent login [--headed]  # solo login/refresh della sessione
uv run steam-agent collect-games     # aggiorna la lista giochi (config/games.yaml)

# singoli dataset:
uv run steam-agent collect-marketing # visite/impression per sorgente + ownership + paesi
uv run steam-agent collect-wishlist
uv run steam-agent collect-sales [--since YYYY-MM] [--month YYYY-MM]
uv run steam-agent collect-players
uv run steam-agent collect-playtime
uv run steam-agent collect-reviews
uv run steam-agent collect-traffic [--day YYYY-MM-DD]
uv run steam-agent show              # ultimi snapshot pubblici
```

Tutti i collector sono **idempotenti** (rilanciabili quando vuoi). Marketing,
wishlist e players riscaricano l'intera storia (un lancio = dati completi); le
vendite si aggiornano per-mese; il traffico per-giorno; le recensioni in upsert.

## Dashboard

```bash
uv run streamlit run dashboard/app.py
```

Multipage (`dashboard/pages/`), legge il DB con lo stesso engine dei collector
(quindi funziona anche con Postgres). Cache 5 min, pulsante **Aggiorna dati**.
Pagine: **Panoramica · Vendite · Wishlist · Giocatori · Traffico · Playtime ·
Recensioni · Marketing**.

## Configurazione (`.env`)

| Variabile | Obblig. | Note |
|---|---|---|
| `STEAM_USERNAME` / `STEAM_PASSWORD` | sì | account bot dedicato |
| `STEAM_SHARED_SECRET` | no | login automatico (TOTP); vuoto = codice manuale |
| `STEAM_PARTNER_ID` | per le vendite | auto-rilevato da `setup` |
| `STUDIO_NAME` | no | mostrato in dashboard; auto-rilevato |
| `ANTHROPIC_API_KEY` | no | funzioni LLM (roadmap) |
| `DATABASE_URL` | no | default SQLite; per Postgres cambia qui |
| `STEAM_PUBLISHER_API_KEY` | no | Steamworks Web API |

Copia `.env.example` in `.env`, oppure lascia fare a `setup`. Il `.env`, la
sessione (`storage_state.json`) e i dati locali (`data/`) sono in `.gitignore`:
non finiscono mai nel repository.

## Come funziona (in breve)

- `src/steam_agent/auth/` — login automatico ai portali partner (Playwright + Steam Guard).
- `src/steam_agent/collectors/` — un modulo per dataset (download CSV o scraping HTML/JS).
- `src/steam_agent/storage/` — modelli SQLAlchemy, landing grezza + warehouse tipizzato.
- `dashboard/` — Streamlit.

Steam ha **due portali** con login separati: `partner.steamgames.com` (nuovo:
traffico, marketing) e `partner.steampowered.com` (vecchio: vendite, wishlist,
players, playtime). Una stessa sessione copre entrambi.

## Deploy (server sempre attivo)

Codice cross-platform. In produzione: passa a Postgres (`DATABASE_URL`), configura
`STEAM_SHARED_SECRET` per il login non presidiato e schedula `collect-all`
(cron / systemd timer / Task Scheduler).

## Roadmap

- [x] Auth automatica ai due portali + lista giochi
- [x] Collector: vendite, wishlist, marketing, players, playtime, recensioni, traffico
- [x] Dashboard Streamlit (panoramica + pagina per dataset)
- [ ] Layer LLM (insight, anomalie, sentiment recensioni, Q&A in linguaggio naturale → SQL)
- [ ] Scheduler, alert, scraper auto-riparanti

## Licenza

[MIT](LICENSE). Contributi benvenuti — vedi [CONTRIBUTING.md](CONTRIBUTING.md).

## Note legali

Raccogli **i tuoi** dati dal tuo portale partner: uso legittimo. Niente scraping di
terze parti (es. SteamDB). Rispetta i Terms di Steam e usa rate limit gentili.
