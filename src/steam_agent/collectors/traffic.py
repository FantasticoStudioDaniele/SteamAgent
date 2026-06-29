"""Collector for store page traffic from the partner portal (requires a session).

Source: the "Marketing & Visibility" page (`navtrafficstats/<appid>`) exposes a
CSV export with the breakdown by source: Page/Category, Page/Feature ->
Impressions, Visits, Owner Impressions, Owner Visits.

Details discovered in the field:
- The CSV honors the range passed as a query: `preset_date_range` (yesterday,
  1week, 1month, 3months, 6months, 1year, lifetime) or `custom` +
  `start_date`/`end_date` in MM/DD/YYYY format.
- BUT you first need to "warm" the session by visiting a portal page (it sets
  the partner token via login/settoken); without it, the CSV comes back empty.

Strategy: one day at a time (custom single-day) for each app -> daily history
of traffic by source. Daily totals = sum over the rows.
The raw CSV is archived in data/raw/traffic/<appid>/<YYYY-MM-DD>.csv.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import date

from steam_agent.auth.session import authenticated_page
from steam_agent.scraping import selectors as S
from steam_agent.settings import DATA_DIR

log = logging.getLogger(__name__)

_TRAFFIC_URL = S.URL_TRAFFIC


def _to_int(value: str) -> int:
    value = (value or "").strip()
    return int(value) if value.lstrip("-").isdigit() else 0


def parse_traffic_csv(text: str, app_id: int, day: date) -> list[dict]:
    """Parse the traffic CSV into rows ready for the DB."""
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    next(reader, None)  # header
    rows: list[dict] = []
    for r in reader:
        if len(r) < 6 or not (r[0] or r[1]):
            continue
        rows.append(
            {
                "app_id": app_id,
                "date": day,
                "category": r[0].strip(),
                "feature": r[1].strip(),
                "impressions": _to_int(r[2]),
                "visits": _to_int(r[3]),
                "owner_impressions": _to_int(r[4]),
                "owner_visits": _to_int(r[5]),
            }
        )
    return rows


def _archive_raw(app_id: int, day: date, text: str) -> None:
    out_dir = DATA_DIR / "raw" / "traffic" / str(app_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{day.isoformat()}.csv").write_text(text, encoding="utf-8")


async def fetch_traffic(app_ids: list[int], day: date) -> dict[int, list[dict]]:
    """For each app download the traffic CSV for day `day` and return the rows."""
    out: dict[int, list[dict]] = {}
    d = day.strftime("%m/%d/%Y")
    async with authenticated_page() as page:
        warmed = False
        for app_id in app_ids:
            base = _TRAFFIC_URL.format(appid=app_id)
            try:
                if not warmed:
                    # Warm the partner session once (sets the token).
                    await page.goto(base, wait_until="networkidle")
                    warmed = True
                url = (
                    f"{base}?format=csv&preset_date_range=custom"
                    f"&start_date={d}&end_date={d}"
                )
                resp = await page.context.request.get(url)
                text = await resp.text()
                if resp.status != 200 or "<html" in text[:200].lower():
                    log.warning("Traffic appid %s: invalid response (status %s).",
                                app_id, resp.status)
                    out[app_id] = []
                    continue
                _archive_raw(app_id, day, text)
                out[app_id] = parse_traffic_csv(text, app_id, day)
                log.info("Traffic appid %s (%s): %d rows.", app_id, day, len(out[app_id]))
                await asyncio.sleep(0.4)  # gentle on the Steam servers
            except Exception as exc:  # noqa: BLE001
                log.warning("Traffic appid %s failed: %s", app_id, exc)
                out[app_id] = []
    return out
