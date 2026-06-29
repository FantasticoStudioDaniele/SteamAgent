# Contributing to SteamAgent

Thanks for your interest! Here's how to get around.

## Development setup

```bash
uv sync                                # includes the dev-deps (pytest, ruff)
uv run playwright install chromium
uv run pytest -q                       # tests
uv run ruff check src dashboard tests  # lint (same as CI)
```

No Steam account? `uv run python scripts/make_demo_db.py` generates a synthetic DB so you
can run and develop the dashboard offline — see
[Try the demo](README.md#try-the-demo-no-account-needed). CI (`.github/workflows/ci.yml`)
runs ruff + pytest on every push/PR across Python 3.11–3.13.

## Project structure

- `src/steam_agent/auth/` — Playwright login to the two portals + Steam Guard (TOTP/code).
- `src/steam_agent/collectors/` — one file per dataset. Pattern: an async
  `fetch_<name>(...)` function that returns dict-rows.
- `src/steam_agent/storage/` — SQLAlchemy models (`models.py`) and idempotent
  persistence (`raw.py`, `save_<name>` functions).
- `src/steam_agent/cli.py` — Typer commands ("lazy" imports inside the commands that use the browser).
- `dashboard/` — Streamlit: `data.py` is the shared data-layer, `pages/` the pages.
- `scripts/` — portal page inspection tools (`inspect_partner.py`,
  `probe_marketing.py`, …): handy for discovering where the data lives.

## Adding a new collector

1. Create `collectors/<name>.py` with `fetch_<name>(...)`.
2. Add the model in `storage/models.py` and `save_<name>` in `storage/raw.py`
   (idempotent: full-refresh or upsert by key).
3. Add the command in `cli.py` (with local imports inside the function).
4. *(Optional)* loader in `dashboard/data.py` + page in `dashboard/pages/`.
5. `uv run steam-agent init-db` to create the table; test on a single appid.

## Style and rules

- Ruff with `line-length = 100`. Run `ruff check` before opening a PR.
- **Never** commit secrets: `.env`, `*.maFile`, `storage_state.json` and `data/`
  are already in `.gitignore`.
- Gentle rate limits toward Steam; collect **only** the data from your own portal.

## Pull requests

Small, focused PRs, with a description of what changes and how you tested it
(`pytest` green, dashboard screenshots if any).
