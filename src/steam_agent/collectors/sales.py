"""Sales collector from the OLD portal (financial reports).

Source: `report_csv.php` with `QueryPartnerSalesByCountry` (publisher-wide). For a
date range it returns a CSV with one row per (Country, Sku, Platform):
Net Units Sold + Net Steam Sales (USD). SKU = "Name (packageId)".

Strategy: ONE request PER MONTH (publisher-wide, all products) -> monthly
history of sales by product/country/platform. Warm-once is enough
(publisher-wide report), but report_csv.php is rate-limited -> retry passes as for
wishlist. Raw archived in data/raw/sales/<YYYY-MM>.csv.

Note: "Net Steam Sales" is the gross revenue net of refunds/VAT; the partner share
(~70%) is in the HTML table of the monthly report (possible future extension).
"""
from __future__ import annotations

import asyncio
import calendar
import csv
import io
import logging
import re
from datetime import date

from steam_agent.auth.session import authenticated_page
from steam_agent.scraping import selectors as S
from steam_agent.settings import DATA_DIR, settings

log = logging.getLogger(__name__)

OLD = S.URL_OLD_BASE
_SKU_RE = re.compile(r"^(.*?)\s*\((\d+)\)\s*$")


def _to_int(value: str) -> int:
    value = (value or "").strip()
    return int(value) if value.lstrip("-").isdigit() else 0


def _to_float(value: str) -> float:
    try:
        return float((value or "").strip())
    except ValueError:
        return 0.0


def _csv_url(date_start: str, date_end: str) -> str:
    params = (
        f"query=QueryPartnerSalesByCountry^partner={settings.steam_partner_id}^division=0"
        f"^dateStart={date_start}^dateEnd={date_end}^interpreter=PartnerSalesByCountryInterpreter"
    )
    return f"{OLD}/report_csv.php?file=Sales_{date_start}&params={params}"


def parse_sales_csv(text: str, month: date) -> list[dict]:
    reader = csv.reader(io.StringIO(text))
    started = False
    rows: list[dict] = []
    for r in reader:
        if not r:
            continue
        if not started:
            if r[0].strip() == "Country":
                started = True
            continue
        if len(r) < 5:
            continue
        country = r[0].strip()
        sku = r[1].strip()
        if not country or country.lower() == "total":
            continue
        m = _SKU_RE.match(sku)
        rows.append(
            {
                "month": month,
                "country": country,
                "sku": sku,
                "package_id": int(m.group(2)) if m else None,
                "product_name": m.group(1).strip() if m else sku,
                "platform": r[2].strip(),
                "net_units": _to_int(r[3]),
                "net_sales_usd": _to_float(r[4]),
            }
        )
    return rows


def _archive_raw(month: date, text: str) -> None:
    out_dir = DATA_DIR / "raw" / "sales"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{month.strftime('%Y-%m')}.csv").write_text(text, encoding="utf-8")


def months_range(start: date, end: date) -> list[date]:
    y, m = start.year, start.month
    out: list[date] = []
    while (y, m) <= (end.year, end.month):
        out.append(date(y, m, 1))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


async def _fetch_month(page, month: date) -> tuple[list[dict], str]:
    date_start = month.strftime("%Y-%m-01")
    last_day = calendar.monthrange(month.year, month.month)[1]
    date_end = month.strftime(f"%Y-%m-{last_day:02d}")
    try:
        resp = await page.context.request.get(_csv_url(date_start, date_end))
        text = await resp.text()
        if resp.status == 200 and "Country,Sku" in text[:600]:
            rows = parse_sales_csv(text, month)
            _archive_raw(month, text)
            log.info("Sales %s: %d rows.", month.strftime("%Y-%m"), len(rows))
            return rows, ("ok" if rows else "empty")
        return [], "fail"
    except Exception as exc:  # noqa: BLE001
        log.warning("Sales %s: %s", month.strftime("%Y-%m"), exc)
        return [], "fail"


async def fetch_sales(months: list[date], on_result=None) -> dict[date, list[dict]]:
    """For each month download sales by country (all products), with retry passes.

    If `on_result(month, rows)` is provided, it is called as soon as a month is ready
    (incremental saving: an interruption does not lose the months already downloaded).
    """
    out: dict[date, list[dict]] = {}
    pending = list(months)
    async with authenticated_page(portal="old") as page:
        # Warm-once of the old portal (publisher-wide report).
        await page.goto(
            f"{OLD}/partner_report2.php?partnerid={settings.steam_partner_id}",
            wait_until="networkidle",
        )
        for pass_num in range(3):
            if not pending:
                break
            if pass_num > 0:
                log.info("Retry sales: %d months remaining (anti-throttle wait)...", len(pending))
                await asyncio.sleep(25)
            failed: list[date] = []
            for month in pending:
                rows, status = await _fetch_month(page, month)
                if status == "fail":
                    failed.append(month)
                else:
                    out[month] = rows
                    if on_result is not None:
                        on_result(month, rows)
                await asyncio.sleep(1.5)
            pending = failed
        for month in pending:
            out[month] = []
            log.warning("Sales %s: no data after retries.", month.strftime("%Y-%m"))
    return out
