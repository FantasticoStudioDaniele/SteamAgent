"""Collector Marketing (Visits/Impressions Over Time + Ownership + Paesi) — portale NUOVO.

La pagina `navtrafficstats/<appid>` ha grafici jqplot i cui dati NON sono nel CSV:
stanno negli oggetti JS LIVE di window.
- `plotViews` / `plotImpressions`: serie storiche per sorgente. `.data` = lista di
  serie; ogni serie = [[ 'YYYY-MM-DD', valore ], ...]; `.series[i].label` = sorgente
  (la prima e' sempre 'Total').
- `plotOwners`: pie Owner vs Non-Owner. `.data[0]` = [[ 'Owners: X%', X ], ...].
- `plotCountries`: barre top-paesi per visite. `.data[0]` = conteggi visite, allineati
  a `.axes.yaxis.ticks` = ["Paese, NN%", ...].

Con `?preset_date_range=lifetime` tutto e' all-time in 1 sola richiesta. Le serie e i
top (sorgenti/paesi) sono i top-N del periodo; owners/paesi sono SNAPSHOT datati.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

from steam_agent.auth.session import authenticated_page
from steam_agent.settings import DATA_DIR

log = logging.getLogger(__name__)

_URL = "https://partner.steamgames.com/apps/navtrafficstats/{appid}?preset_date_range={preset}"

# Legge tutti gli oggetti jqplot live della pagina.
_EXTRACT_JS = """() => {
    const read = (name) => {
        const p = window[name];
        if (!p || !p.data) return null;
        return { labels: (p.series || []).map(s => s.label), data: p.data };
    };
    let owners = null;
    if (window.plotOwners && window.plotOwners.data && window.plotOwners.data[0])
        owners = window.plotOwners.data[0];
    let countries = null;
    if (window.plotCountries && window.plotCountries.data && window.plotCountries.data[0]) {
        let ticks = [];
        try {
            ticks = window.plotCountries.axes.yaxis.ticks.map(
                t => (t && t.label !== undefined) ? t.label : t);
        } catch (e) { ticks = []; }
        countries = { counts: window.plotCountries.data[0], ticks: ticks };
    }
    return {
        visits: read('plotViews'),
        impressions: read('plotImpressions'),
        owners: owners,
        countries: countries,
    };
}"""


def parse_marketing(extract: dict, app_id: int) -> list[dict]:
    """Serie Visits/Impressions Over Time -> righe per il DB."""
    rows: list[dict] = []
    for metric in ("visits", "impressions"):
        block = extract.get(metric) if extract else None
        if not block:
            continue
        labels = block.get("labels") or []
        for i, series in enumerate(block.get("data") or []):
            source = labels[i] if i < len(labels) else f"series{i}"
            for point in series or []:
                if not point or len(point) < 2:
                    continue
                try:
                    day = date.fromisoformat(str(point[0])[:10])
                except ValueError:
                    continue
                value = point[1]
                rows.append(
                    {
                        "app_id": app_id,
                        "date": day,
                        "metric": metric,
                        "source": str(source),
                        "value": int(value) if value is not None else 0,
                    }
                )
    return rows


def parse_owners(extract: dict, app_id: int, snapshot_date: date) -> dict | None:
    """Pie Ownership -> {owners_pct, non_owners_pct}."""
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
    """Barre top-paesi -> righe {country, visits, pct}. Tick = 'Paese, NN%'
    (split sull'ULTIMO ', ' perche' alcuni nomi contengono virgole)."""
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
                # i grafici si inizializzano in $(document).ready: dai un attimo e ricontrolla
                await page.wait_for_timeout(1200)
                payload = await page.evaluate(_EXTRACT_JS)
            daily = parse_marketing(payload, app_id)
            owners = parse_owners(payload, app_id, snapshot_date)
            countries = parse_countries(payload, app_id, snapshot_date)
            if daily or owners or countries:
                _archive_raw(app_id, preset, payload)
            log.info(
                "Marketing appid %s: %d righe serie, owners=%s, paesi=%d (%s).",
                app_id, len(daily), "si" if owners else "no", len(countries), preset,
            )
            return {"daily": daily, "owners": owners, "countries": countries}
        except Exception as exc:  # noqa: BLE001
            log.warning("Marketing appid %s tentativo %d: %s", app_id, attempt + 1, exc)
            await asyncio.sleep(2)
    return {"daily": [], "owners": None, "countries": []}


async def fetch_marketing(app_ids: list[int], preset: str = "lifetime") -> dict[int, dict]:
    """Per ogni app estrae serie Over Time + ownership + top-paesi (un page-load)."""
    snapshot_date = datetime.now(timezone.utc).date()
    out: dict[int, dict] = {}
    async with authenticated_page(portal="new") as page:
        for app_id in app_ids:
            out[app_id] = await _fetch_one(page, app_id, preset, snapshot_date)
            await asyncio.sleep(0.5)  # gentile sui server Steam
    return out
