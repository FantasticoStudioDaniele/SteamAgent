"""Wishlist collector from the OLD portal (partner.steampowered.com).

The `app/wishlist/<appid>/` page exposes a CSV export via `report_csv.php` with the
`QueryWishlistActionsForCSV` query. It returns the COMPLETE DAILY HISTORY
in a single request:

    DateLocal, Game, Adds, Deletes, PurchasesAndActivations, Gifts

So a single request per game covers the whole history. The "wishlist balance"
(outstanding) = cumulative sum of (Adds - Deletes - PurchasesAndActivations -
Gifts), computable at analysis time.

As with traffic, you need to "warm" the old portal session by visiting a
page before downloading the CSVs. The raw is archived in
data/raw/wishlist/<appid>/<start>_to_<end>.csv.
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
        f"query=QueryWishlistActionsForCSV^appID={app_id}"
        f"^dateStart={date_start}^dateEnd={date_end}^interpreter=WishlistReportInterpreter"
    )
    return f"{OLD}/report_csv.php?file=SteamWishlists_{app_id}&params={params}"


def parse_wishlist_csv(text: str, app_id: int) -> list[dict]:
    """Parse the wishlist CSV (skip the header rows up to 'DateLocal')."""
    reader = csv.reader(io.StringIO(text))
    started = False
    rows: list[dict] = []
    for r in reader:
        if not r:
            continue
        if not started:
            if r and r[0].strip() == "DateLocal":
                started = True
            continue
        if len(r) < 6:
            continue
        try:
            d = date.fromisoformat(r[0].strip())
        except ValueError:
            continue
        rows.append(
            {
                "app_id": app_id,
                "date": d,
                "adds": _to_int(r[2]),
                "deletes": _to_int(r[3]),
                "purchases_activations": _to_int(r[4]),
                "gifts": _to_int(r[5]),
            }
        )
    return rows


def _archive_raw(app_id: int, text: str, date_start: str, date_end: str) -> None:
    out_dir = DATA_DIR / "raw" / "wishlist" / str(app_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{date_start}_to_{date_end}.csv").write_text(text, encoding="utf-8")


async def _fetch_one(
    page, app_id: int, date_start: str, date_end: str, warm: str
) -> tuple[list[dict], str]:
    """Download the wishlist CSV for one app (per-app warm is mandatory on the old
    portal). Returns (rows, status) with status in {"ok", "empty", "fail"}:
    - ok    = valid CSV with data
    - empty = valid CSV but no rows (app without wishlist: demo/DLC) -> no retry
    - fail  = invalid response (likely throttling) -> to be retried
    """
    try:
        await page.goto(f"{OLD}/app/wishlist/{app_id}/", wait_until=warm)
        resp = await page.context.request.get(_csv_url(app_id, date_start, date_end))
        text = await resp.text()
        if resp.status == 200 and "DateLocal" in text[:600]:
            rows = parse_wishlist_csv(text, app_id)
            _archive_raw(app_id, text, date_start, date_end)
            log.info("Wishlist appid %s: %d days.", app_id, len(rows))
            return rows, ("ok" if rows else "empty")
        return [], "fail"
    except Exception as exc:  # noqa: BLE001
        log.warning("Wishlist appid %s: %s", app_id, exc)
        return [], "fail"


async def fetch_wishlist(
    app_ids: list[int], date_start: str = "2010-01-01", date_end: str | None = None
) -> dict[int, list[dict]]:
    """Complete wishlist history for each app, robust to the portal's rate limiting.

    One fast pass; then up to 2 retry passes (with anti-throttle wait) only on the
    apps that came back 'fail'. The 'empty' apps (demo/DLC without wishlist) are not retried.
    """
    date_end = date_end or datetime.now(timezone.utc).date().isoformat()
    out: dict[int, list[dict]] = {}
    pending = list(app_ids)
    async with authenticated_page(portal="old") as page:
        for pass_num in range(3):
            if not pending:
                break
            warm = "domcontentloaded" if pass_num == 0 else "networkidle"
            if pass_num > 0:
                log.info("Retry wishlist: %d apps remaining (anti-throttle wait)...", len(pending))
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
            log.warning("Wishlist appid %s: no data after retries (throttling?).", app_id)
    return out
