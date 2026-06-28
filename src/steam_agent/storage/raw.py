"""Persistenza: record grezzi, snapshot pubblici, traffico, wishlist, vendite."""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable

from sqlalchemy import delete

from steam_agent.collectors.base import RawRecord, utcnow
from steam_agent.storage.db import SessionLocal, init_db
from steam_agent.storage.models import (
    GameSnapshot,
    MarketingCountry,
    MarketingDaily,
    MarketingOwners,
    PlayersDaily,
    PlaytimeSnapshot,
    RawPayload,
    Review,
    SalesByCountry,
    TrafficDaily,
    WishlistDaily,
)

log = logging.getLogger(__name__)


def save_raw(records: Iterable[RawRecord]) -> int:
    """Append-only della landing grezza. Restituisce il numero di record salvati."""
    init_db()
    count = 0
    with SessionLocal() as session:
        for r in records:
            session.add(
                RawPayload(
                    source=r.source,
                    key=r.key,
                    app_id=r.app_id,
                    payload=r.payload,
                    collected_at=r.collected_at,
                )
            )
            count += 1
        session.commit()
    return count


def build_snapshot(app_id: int, records: list[RawRecord]) -> GameSnapshot:
    """Estrae dai record grezzi un snapshot tipizzato e leggibile."""
    by_source = {r.source: r.payload for r in records}
    details = by_source.get("store_appdetails", {})
    reviews = by_source.get("appreviews_summary", {})
    players = by_source.get("current_players", {})

    price = None
    if isinstance(details.get("price_overview"), dict):
        price = details["price_overview"].get("final_formatted")
    elif details.get("is_free"):
        price = "Free"

    return GameSnapshot(
        app_id=app_id,
        name=details.get("name"),
        current_players=players.get("player_count"),
        reviews_total=reviews.get("total_reviews"),
        reviews_positive=reviews.get("total_positive"),
        review_score_desc=reviews.get("review_score_desc"),
        price=price,
        collected_at=utcnow(),
    )


def save_snapshot(snap: GameSnapshot) -> None:
    init_db()
    with SessionLocal() as session:
        session.add(snap)
        session.commit()


def save_traffic(app_id: int, day: date, rows: list[dict]) -> int:
    """Idempotente: sostituisce le righe traffico per (app_id, day)."""
    init_db()
    with SessionLocal() as session:
        session.execute(
            delete(TrafficDaily).where(
                TrafficDaily.app_id == app_id, TrafficDaily.date == day
            )
        )
        now = utcnow()
        for r in rows:
            session.add(TrafficDaily(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_wishlist(app_id: int, rows: list[dict]) -> int:
    """Idempotente: sostituisce l'intero storico wishlist dell'app (full refresh)."""
    init_db()
    with SessionLocal() as session:
        session.execute(delete(WishlistDaily).where(WishlistDaily.app_id == app_id))
        now = utcnow()
        for r in rows:
            session.add(WishlistDaily(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_sales(month: date, rows: list[dict]) -> int:
    """Idempotente: sostituisce le vendite del mese."""
    init_db()
    with SessionLocal() as session:
        session.execute(delete(SalesByCountry).where(SalesByCountry.month == month))
        now = utcnow()
        for r in rows:
            session.add(SalesByCountry(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_reviews(rows: list[dict]) -> int:
    """Upsert delle recensioni per recommendation_id (idempotente)."""
    init_db()
    with SessionLocal() as session:
        for r in rows:
            session.merge(Review(**r))
        session.commit()
    return len(rows)


def save_players(app_id: int, rows: list[dict]) -> int:
    """Idempotente: sostituisce l'intero storico players dell'app (full refresh)."""
    init_db()
    with SessionLocal() as session:
        session.execute(delete(PlayersDaily).where(PlayersDaily.app_id == app_id))
        now = utcnow()
        for r in rows:
            session.add(PlayersDaily(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_marketing(app_id: int, rows: list[dict]) -> int:
    """Idempotente: sostituisce l'intera serie marketing dell'app (full refresh)."""
    init_db()
    with SessionLocal() as session:
        session.execute(delete(MarketingDaily).where(MarketingDaily.app_id == app_id))
        now = utcnow()
        for r in rows:
            session.add(MarketingDaily(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_marketing_owners(app_id: int, snap: dict | None) -> int:
    """Idempotente: salva/sostituisce lo snapshot owners per (app_id, snapshot_date)."""
    if not snap:
        return 0
    init_db()
    with SessionLocal() as session:
        session.execute(
            delete(MarketingOwners).where(
                MarketingOwners.app_id == snap["app_id"],
                MarketingOwners.snapshot_date == snap["snapshot_date"],
            )
        )
        session.add(MarketingOwners(collected_at=utcnow(), **snap))
        session.commit()
    return 1


def save_marketing_country(app_id: int, rows: list[dict]) -> int:
    """Idempotente: sostituisce i top-paesi per (app_id, snapshot_date)."""
    if not rows:
        return 0
    init_db()
    snap_date = rows[0]["snapshot_date"]
    with SessionLocal() as session:
        session.execute(
            delete(MarketingCountry).where(
                MarketingCountry.app_id == app_id,
                MarketingCountry.snapshot_date == snap_date,
            )
        )
        now = utcnow()
        for r in rows:
            session.add(MarketingCountry(collected_at=now, **r))
        session.commit()
    return len(rows)


def save_playtime(snap: dict | None) -> int:
    """Idempotente: salva/sostituisce lo snapshot playtime per (app_id, snapshot_date)."""
    if not snap:
        return 0
    init_db()
    with SessionLocal() as session:
        session.execute(
            delete(PlaytimeSnapshot).where(
                PlaytimeSnapshot.app_id == snap["app_id"],
                PlaytimeSnapshot.snapshot_date == snap["snapshot_date"],
            )
        )
        session.add(PlaytimeSnapshot(collected_at=utcnow(), **snap))
        session.commit()
    return 1
