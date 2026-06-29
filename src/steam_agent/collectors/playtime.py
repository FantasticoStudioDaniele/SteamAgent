"""Playtime (lifetime) collector from the OLD portal, via scraping 2 HTML tables.

`app/playtime/<appid>/` shows LIFETIME play-time statistics:
- Summary: measured users, average/median time.
- Distribution: % of users per minimum played-time threshold (10m, 30m, 1h, ...).
No CSV: the tables are read. It is a SNAPSHOT (not a history): it is saved
dated (snapshot_date) and can be re-run periodically to see the evolution.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timezone

from steam_agent.auth.session import authenticated_page
from steam_agent.scraping import selectors as S

log = logging.getLogger(__name__)

OLD = S.URL_OLD_BASE

_TABLES_JS = S.JS_PLAYTIME_TABLES


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
            log.info("Playtime appid %s: %s", app_id, "ok" if snap else "no data")
            return snap
        except Exception as exc:  # noqa: BLE001
            log.warning("Playtime appid %s attempt %d: %s", app_id, attempt + 1, exc)
            await asyncio.sleep(2)
    return None


async def fetch_playtime(app_ids: list[int]) -> dict[int, dict | None]:
    """Lifetime playtime snapshot for each app (table scraping)."""
    snapshot_date = datetime.now(timezone.utc).date()
    out: dict[int, dict | None] = {}
    async with authenticated_page(portal="old") as page:
        for app_id in app_ids:
            out[app_id] = await _fetch_one(page, app_id, snapshot_date)
            await asyncio.sleep(0.8)
    return out
