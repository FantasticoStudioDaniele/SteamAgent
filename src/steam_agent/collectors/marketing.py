"""Marketing collector (Visits/Impressions Over Time + Ownership + Countries) — NEW portal.

The `navtrafficstats/<appid>` page has jqplot charts whose data is NOT in the CSV:
it lives in the LIVE JS objects of window.
- `plotViews` / `plotImpressions`: history series by source. `.data` = list of
  series; each series = [[ 'YYYY-MM-DD', value ], ...]; `.series[i].label` = source
  (the first is always 'Total').
- `plotOwners`: Owner vs Non-Owner pie. `.data[0]` = [[ 'Owners: X%', X ], ...].
- `plotCountries`: top-countries bars by visits. `.data[0]` = visit counts, aligned
  to `.axes.yaxis.ticks` = ["Country, NN%", ...].

With `?preset_date_range=lifetime` everything is all-time in a single request. The series and the
top (sources/countries) are the top-N of the period; owners/countries are dated SNAPSHOTS.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from steam_agent.auth.session import authenticated_page
from steam_agent.scraping import report
from steam_agent.scraping import selectors as S
from steam_agent.scraping.artifacts import dump_page_artifact
from steam_agent.scraping.drift import marketing_charts_missing
from steam_agent.settings import DATA_DIR

log = logging.getLogger(__name__)

_URL = S.URL_MARKETING_TMPL

# Reads all the live jqplot objects of the page.
_EXTRACT_JS = S.JS_MARKETING_EXTRACT


# Steam's "Over Time" series occasionally start with a stray point detached from
# the real, daily-continuous data (e.g. a single visit years before launch). The
# data is daily, so a leading gap this large is never legitimate — drop such
# points so they don't pollute the stored date range.
_LEADING_GAP_DAYS = 90


def _trim_leading_gaps(points: list[tuple[date, int]]) -> list[tuple[date, int]]:
    """Drop stray leading points separated from the next point by a large gap."""
    pts = sorted(points)
    cut = 0
    while cut + 1 < len(pts) and (pts[cut + 1][0] - pts[cut][0]).days > _LEADING_GAP_DAYS:
        cut += 1
    return pts[cut:]


def parse_marketing(extract: dict, app_id: int) -> list[dict]:
    """Visits/Impressions Over Time series -> rows for the DB."""
    rows: list[dict] = []
    for metric in ("visits", "impressions"):
        block = extract.get(metric) if extract else None
        if not block:
            continue
        labels = block.get("labels") or []
        for i, series in enumerate(block.get("data") or []):
            source = labels[i] if i < len(labels) else f"series{i}"
            points: list[tuple[date, int]] = []
            for point in series or []:
                if not point or len(point) < 2:
                    continue
                try:
                    day = date.fromisoformat(str(point[0])[:10])
                except ValueError:
                    continue
                value = point[1]
                points.append((day, int(value) if value is not None else 0))
            for day, value in _trim_leading_gaps(points):
                rows.append(
                    {
                        "app_id": app_id,
                        "date": day,
                        "metric": metric,
                        "source": str(source),
                        "value": value,
                    }
                )
    return rows


def parse_owners(extract: dict, app_id: int, snapshot_date: date) -> dict | None:
    """Ownership pie -> {owners_pct, non_owners_pct}."""
    raw = extract.get("owners") if extract else None
    if not raw:
        return None
    owners_pct = non_owners_pct = None
    for item in raw:
        if not item or len(item) < 2:
            continue
        label = str(item[0]).lower()
        try:
            pct = float(item[1])
        except (TypeError, ValueError):
            continue
        if "non-owner" in label or "non owner" in label:
            non_owners_pct = pct
        elif "owner" in label:
            owners_pct = pct
    if owners_pct is None and non_owners_pct is None:
        return None
    if owners_pct is None and non_owners_pct is not None:
        owners_pct = round(100.0 - non_owners_pct, 2)
    if non_owners_pct is None and owners_pct is not None:
        non_owners_pct = round(100.0 - owners_pct, 2)
    return {
        "app_id": app_id,
        "snapshot_date": snapshot_date,
        "owners_pct": owners_pct,
        "non_owners_pct": non_owners_pct,
    }


def parse_countries(extract: dict, app_id: int, snapshot_date: date) -> list[dict]:
    """Top-countries bars -> rows {country, visits, pct}. Tick = 'Country, NN%'
    (split on the LAST ', ' because some names contain commas)."""
    block = extract.get("countries") if extract else None
    if not block:
        return []
    counts = block.get("counts") or []
    ticks = block.get("ticks") or []
    rows: list[dict] = []
    for i, tick in enumerate(ticks):
        if tick is None:
            continue
        text = str(tick)
        country, pct = text, None
        if ", " in text:
            country, pct_str = text.rsplit(", ", 1)
            pct_str = pct_str.strip().rstrip("%")
            try:
                pct = float(pct_str)
            except ValueError:
                pct = None
        visits = 0
        if i < len(counts):
            try:
                visits = int(counts[i])
            except (TypeError, ValueError):
                visits = 0
        rows.append(
            {
                "app_id": app_id,
                "snapshot_date": snapshot_date,
                "country": country.strip(),
                "visits": visits,
                "pct": pct,
            }
        )
    return rows


def _archive_raw(app_id: int, preset: str, extract: dict) -> None:
    out_dir = DATA_DIR / "raw" / "marketing"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{app_id}_{preset}.json").write_text(
        json.dumps(extract, ensure_ascii=False), encoding="utf-8"
    )


async def _fetch_one(page, app_id: int, preset: str, snapshot_date: date) -> dict:
    url = _URL.format(appid=app_id, preset=preset)
    for attempt in range(2):
        try:
            await page.goto(url, wait_until="networkidle")
            payload = await page.evaluate(_EXTRACT_JS)
            if not (payload.get("visits") or payload.get("impressions")):
                # the charts initialize in $(document).ready: wait a moment and recheck
                await page.wait_for_timeout(1200)
                payload = await page.evaluate(_EXTRACT_JS)
            if marketing_charts_missing(payload):
                # Both jqplot objects are absent after the document.ready re-check:
                # the page didn't render its charts (layout change), distinct from a
                # game with genuinely no traffic (charts present with empty data).
                art = await dump_page_artifact(page, "marketing", app_id, label=preset)
                report.record_drift(
                    "marketing", f"appid {app_id}: visits & impressions charts did not render",
                    str(art.get("url")),
                )
                return {"daily": [], "owners": None, "countries": []}
            daily = parse_marketing(payload, app_id)
            owners = parse_owners(payload, app_id, snapshot_date)
            countries = parse_countries(payload, app_id, snapshot_date)
            if daily or owners or countries:
                _archive_raw(app_id, preset, payload)
            log.info(
                "Marketing appid %s: %d series rows, owners=%s, countries=%d (%s).",
                app_id, len(daily), "yes" if owners else "no", len(countries), preset,
            )
            return {"daily": daily, "owners": owners, "countries": countries}
        except Exception as exc:  # noqa: BLE001
            log.warning("Marketing appid %s attempt %d: %s", app_id, attempt + 1, exc)
            await asyncio.sleep(2)
    return {"daily": [], "owners": None, "countries": []}


async def fetch_marketing(app_ids: list[int], preset: str = "lifetime") -> dict[int, dict]:
    """For each app extracts Over Time series + ownership + top-countries (one page-load)."""
    snapshot_date = datetime.now(timezone.utc).date()
    out: dict[int, dict] = {}
    async with authenticated_page(portal="new") as page:
        for app_id in app_ids:
            out[app_id] = await _fetch_one(page, app_id, preset, snapshot_date)
            await asyncio.sleep(0.5)  # gentle on the Steam servers
    return out
