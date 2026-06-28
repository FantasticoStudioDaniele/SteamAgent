"""Collector wishlist dal VECCHIO portale (partner.steampowered.com).

La pagina `app/wishlist/<appid>/` espone un export CSV via `report_csv.php` con la
query `QueryWishlistActionsForCSV`. Restituisce la SERIE STORICA GIORNALIERA
COMPLETA in una sola richiesta:

    DateLocal, Game, Adds, Deletes, PurchasesAndActivations, Gifts

Quindi basta 1 richiesta per gioco per tutto lo storico. Il "saldo wishlist"
(outstanding) = somma cumulativa di (Adds - Deletes - PurchasesAndActivations -
Gifts), calcolabile in fase di analisi.

Come per il traffico, serve "scaldare" la sessione del vecchio portale visitando
una pagina prima di scaricare i CSV. Il raw viene archiviato in
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
    """Parsa il CSV wishlist (salta le righe di intestazione fino a 'DateLocal')."""
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
    """Scarica il CSV wishlist di una app (warm per-app obbligatorio sul vecchio
    portale). Ritorna (righe, stato) con stato in {"ok", "empty", "fail"}:
    - ok    = CSV valido con dati
    - empty = CSV valido ma senza righe (app senza wishlist: demo/DLC) -> niente retry
    - fail  = risposta non valida (probabile throttling) -> da riprovare
    """
    try:
        await page.goto(f"{OLD}/app/wishlist/{app_id}/", wait_until=warm)
        resp = await page.context.request.get(_csv_url(app_id, date_start, date_end))
        text = await resp.text()
        if resp.status == 200 and "DateLocal" in text[:600]:
            rows = parse_wishlist_csv(text, app_id)
            _archive_raw(app_id, text, date_start, date_end)
            log.info("Wishlist appid %s: %d giorni.", app_id, len(rows))
            return rows, ("ok" if rows else "empty")
        return [], "fail"
    except Exception as exc:  # noqa: BLE001
        log.warning("Wishlist appid %s: %s", app_id, exc)
        return [], "fail"


async def fetch_wishlist(
    app_ids: list[int], date_start: str = "2010-01-01", date_end: str | None = None
) -> dict[int, list[dict]]:
    """Storico wishlist completo per ogni app, robusto al rate-limiting del portale.

    Passa 1 veloce; poi fino a 2 retry-pass (con attesa anti-throttle) solo sulle
    app risultate 'fail'. Le app 'empty' (demo/DLC senza wishlist) non si riprovano.
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
                log.info("Retry wishlist: %d app rimaste (attesa anti-throttle)...", len(pending))
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
            log.warning("Wishlist appid %s: nessun dato dopo i retry (throttling?).", app_id)
    return out
