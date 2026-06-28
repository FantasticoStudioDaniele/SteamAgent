"""Collector players/DAU dal VECCHIO portale (partner.steampowered.com).

La pagina `app/players/<appid>/` espone via `report_csv.php` la query
`QueryDailyActiveUserHistory`: storico GIORNALIERO completo in una richiesta:
    DateReported, DailyActiveUsers, PeakConcurrentUsers

Stessi vincoli del vecchio portale: warm PER-APP obbligatorio + rate-limit ->
retry-pass (come le wishlist). Raw in data/raw/players/<appid>/<start>_to_<end>.csv.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date, datetime, timezone

from steam_agent.auth.session import authenticated_page
from steam_agent.settings import DATA_DIR

log = logging.getLogger(__name__)

OLD = "https://partner.steampowered.com"


def _to_int(value: str) -> int:
    value = (value or "").strip()
    return int(value) if value.lstrip("-").isdigit() else 0


def _csv_url(app_id: int, date_start: str, date_end: str) -> str:
    params = (
        f"query=QueryDailyActiveUserHistory^appID={app_id}"
        f"^dateStart={date_start}^dateEnd={date_end}^interpreter=PlayerCountInterpreter"
    )
    return f"{OLD}/report_csv.php?file=Players_{app_id}&params={params}"


def parse_players_csv(text: str, app_id: int) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    started = False
    rows: list[dict] = []
    for r in reader:
        if not r:
            continue
        if not started:
            if r and r[0].strip() == "DateReported":
                started = True
            continue
        if len(r) < 3:
            continue
        try:
            d = date.fromisoformat(r[0].strip())
        except ValueError:
            continue
        rows.append(
            {
                "app_id": app_id,
                "date": d,
                "daily_active_users": _to_int(r[1]),
                "peak_concurrent_users": _to_int(r[2]),
            }
        )
    return rows


def _archive_raw(app_id: int, text: str, date_start: str, date_end: str) -> None:
    out_dir = DATA_DIR / "raw" / "players" / str(app_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{date_start}_to_{date_end}.csv").write_text(text, encoding="utf-8")


async def _fetch_one(page, app_id: int, date_start: str, date_end: str, warm: str) -> tuple[list[dict], str]:
    try:
        await page.goto(f"{OLD}/app/players/{app_id}/", wait_until=warm)
        resp = await page.context.request.get(_csv_url(app_id, date_start, date_end))
        text = await resp.text()
        if resp.status == 200 and "DateReported" in text[:600]:
            rows = parse_players_csv(text, app_id)
            _archive_raw(app_id, text, date_start, date_end)
            log.info("Players appid %s: %d giorni.", app_id, len(rows))
            return rows, ("ok" if rows else "empty")
        return [], "fail"
    except Exception as exc:  # noqa: BLE001
        log.warning("Players appid %s: %s", app_id, exc)
        return [], "fail"


async def fetch_players(
    app_ids: list[int], date_start: str = "2010-01-01", date_end: str | None = None
) -> dict[int, list[dict]]:
    """Storico players completo per ogni app, robusto al rate-limiting (retry-pass)."""
    date_end = date_end or datetime.now(timezone.utc).date().isoformat()
    out: dict[int, list[dict]] = {}
    pending = list(app_ids)
    async with authenticated_page(portal="old") as page:
        for pass_num in range(3):
            if not pending:
                break
            warm = "domcontentloaded" if pass_num == 0 else "networkidle"
            if pass_num > 0:
                log.info("Retry players: %d app rimaste (attesa anti-throttle)...", len(pending))
                await asyncio.sleep(25)
            failed: list[int] = []
            for app_id in pending:
                rows, status = await _fetch_one(page, app_id, date_start, date_end, warm)
                if status == "fail":
                    failed.append(app_id)
                else:
                    out[app_id] = rows
                await asyncio.sleep(1.2 if pass_num == 0 else 3.0)
            pending = failed
        for app_id in pending:
            out[app_id] = []
            log.warning("Players appid %s: nessun dato dopo i retry.", app_id)
    return out
