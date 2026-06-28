"""Collector playtime (lifetime) dal VECCHIO portale, via scraping di 2 tabelle HTML.

`app/playtime/<appid>/` mostra statistiche di tempo di gioco LIFETIME:
- Sommario: utenti misurati, tempo medio/mediano.
- Distribuzione: % di utenti per soglia minima di tempo giocato (10m, 30m, 1h, ...).
Niente CSV: si leggono le tabelle. E' uno SNAPSHOT (non serie storica): lo si salva
datato (snapshot_date) e lo si puo' rilanciare periodicamente per vedere l'evoluzione.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone

from steam_agent.auth.session import authenticated_page

log = logging.getLogger(__name__)

OLD = "https://partner.steampowered.com"

_TABLES_JS = """() => [...document.querySelectorAll('table')].map(t =>
    [...t.querySelectorAll('tr')].map(r =>
        [...r.querySelectorAll('th,td')].map(c => (c.innerText || '').trim())))"""


def _to_minutes(text: str) -> int | None:
    text = (text or "").lower()
    h = re.search(r"(\d+)\s*hour", text)
    m = re.search(r"(\d+)\s*minute", text)
    if not h and not m:
        return None
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def parse_playtime(tables: list, app_id: int, snapshot_date: date) -> dict | None:
    lifetime_users = avg_minutes = median_minutes = None
    dist: dict[str, int] = {}
    for tbl in tables:
        for row in tbl:
            if not row:
                continue
            label = (row[0] or "").strip().lower()
            val = row[1].strip() if len(row) > 1 else ""
            if "lifetime users" in label:
                digits = re.sub(r"[^\d]", "", val)
                lifetime_users = int(digits) if digits else None
            elif "average time" in label:
                avg_minutes = _to_minutes(val)
            elif "median time" in label:
                median_minutes = _to_minutes(val)
            elif re.match(r"\d+\s*(hour|minute)", label) and val.endswith("%"):
                mins = _to_minutes(label)
                if mins is not None:
                    pct = re.sub(r"[^\d]", "", val)
                    dist[str(mins)] = int(pct) if pct else 0
    if not lifetime_users:
        return None
    return {
        "app_id": app_id,
        "snapshot_date": snapshot_date,
        "lifetime_users": lifetime_users,
        "avg_minutes": avg_minutes,
        "median_minutes": median_minutes,
        "distribution": dist,
    }


async def _fetch_one(page, app_id: int, snapshot_date: date) -> dict | None:
    for attempt in range(2):
        try:
            await page.goto(f"{OLD}/app/playtime/{app_id}/", wait_until="domcontentloaded")
            tables = await page.evaluate(_TABLES_JS)
            snap = parse_playtime(tables, app_id, snapshot_date)
            log.info("Playtime appid %s: %s", app_id, "ok" if snap else "nessun dato")
            return snap
        except Exception as exc:  # noqa: BLE001
            log.warning("Playtime appid %s tentativo %d: %s", app_id, attempt + 1, exc)
            await asyncio.sleep(2)
    return None


async def fetch_playtime(app_ids: list[int]) -> dict[int, dict | None]:
    """Snapshot playtime lifetime per ogni app (scraping tabelle)."""
    snapshot_date = datetime.now(timezone.utc).date()
    out: dict[int, dict | None] = {}
    async with authenticated_page(portal="old") as page:
        for app_id in app_ids:
            out[app_id] = await _fetch_one(page, app_id, snapshot_date)
            await asyncio.sleep(0.8)
    return out
