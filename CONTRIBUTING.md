# Contribuire a SteamAgent

Grazie per l'interesse! Di seguito come muoverti.

## Setup sviluppo

```bash
uv sync                              # include i dev-deps (pytest, ruff)
uv run playwright install chromium
uv run pytest -q                     # test
uv run ruff check src dashboard      # lint
```

## Struttura del progetto

- `src/steam_agent/auth/` — login Playwright ai due portali + Steam Guard (TOTP/codice).
- `src/steam_agent/collectors/` — un file per dataset. Pattern: una funzione
  `fetch_<nome>(...)` async che ritorna righe-dict.
- `src/steam_agent/storage/` — modelli SQLAlchemy (`models.py`) e persistenza
  idempotente (`raw.py`, funzioni `save_<nome>`).
- `src/steam_agent/cli.py` — comandi Typer (import "pigri" dentro i comandi che usano il browser).
- `dashboard/` — Streamlit: `data.py` è il data-layer condiviso, `pages/` le pagine.
- `scripts/` — strumenti di ispezione delle pagine del portale (`inspect_partner.py`,
  `probe_marketing.py`, …): utili per scoprire dove vivono i dati.

## Aggiungere un nuovo collector

1. Crea `collectors/<nome>.py` con `fetch_<nome>(...)`.
2. Aggiungi il modello in `storage/models.py` e `save_<nome>` in `storage/raw.py`
   (idempotente: full-refresh o upsert per chiave).
3. Aggiungi il comando in `cli.py` (con import locali dentro la funzione).
4. *(Opzionale)* loader in `dashboard/data.py` + pagina in `dashboard/pages/`.
5. `uv run steam-agent init-db` per creare la tabella; testa su un singolo appid.

## Stile e regole

- Ruff con `line-length = 100`. Lancia `ruff check` prima di aprire una PR.
- **Mai** segreti nei commit: `.env`, `*.maFile`, `storage_state.json` e `data/`
  sono già in `.gitignore`.
- Rate limit gentili verso Steam; si raccolgono **solo** i dati del proprio portale.

## Pull request

PR piccole e mirate, con una descrizione di cosa cambia e come l'hai testato
(`pytest` verde, eventuali screenshot della dashboard).
