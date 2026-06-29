"""Idempotency tests for the storage.raw save_* layer (isolated SQLite DB).

Each save_* documents an idempotency contract (delete-then-insert full refresh,
per-key replace, or upsert-by-id) but none was tested. These point the layer at a
throwaway engine — monkeypatching both ``raw.SessionLocal`` and ``raw.init_db``,
since save_* binds to the module-global engine at import — and assert that running
a collection twice does not duplicate rows.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from steam_agent.collectors.base import utcnow
from steam_agent.storage import raw
from steam_agent.storage.models import (
    Base,
    MarketingOwners,
    PlaytimeSnapshot,
    Review,
    SalesByCountry,
    TrafficDaily,
    WishlistDaily,
)


@pytest.fixture
def raw_db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{(tmp_path / 'raw.db').as_posix()}", future=True)
    Base.metadata.create_all(eng)
    test_session = sessionmaker(bind=eng, future=True, expire_on_commit=False)
    # save_* uses the module-global SessionLocal + init_db; redirect both so the
    # real DB at settings.database_url is never touched.
    monkeypatch.setattr(raw, "SessionLocal", test_session)
    monkeypatch.setattr(raw, "init_db", lambda: None)
    return eng


def _count(engine, model) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model))


def test_save_traffic_replaces_day(raw_db):
    rows = [
        {"app_id": 1, "date": date(2026, 1, 1), "category": "Steam", "feature": "Home",
         "impressions": 10, "visits": 2, "owner_impressions": 1, "owner_visits": 0},
        {"app_id": 1, "date": date(2026, 1, 1), "category": "Ext", "feature": "Web",
         "impressions": 5, "visits": 1, "owner_impressions": 0, "owner_visits": 0},
    ]
    assert raw.save_traffic(1, date(2026, 1, 1), rows) == 2
    raw.save_traffic(1, date(2026, 1, 1), rows)  # rerun same day
    assert _count(raw_db, TrafficDaily) == 2  # replaced for (app_id, day), not doubled


def test_save_wishlist_full_refresh(raw_db):
    raw.save_wishlist(1, [
        {"app_id": 1, "date": date(2026, 1, 1), "adds": 5, "deletes": 1,
         "purchases_activations": 0, "gifts": 0},
        {"app_id": 1, "date": date(2026, 1, 2), "adds": 6, "deletes": 0,
         "purchases_activations": 0, "gifts": 0},
    ])
    # a shorter re-collection replaces the whole history for the app
    raw.save_wishlist(1, [
        {"app_id": 1, "date": date(2026, 1, 1), "adds": 99, "deletes": 0,
         "purchases_activations": 0, "gifts": 0},
    ])
    assert _count(raw_db, WishlistDaily) == 1
    with Session(raw_db) as s:
        assert s.scalars(select(WishlistDaily)).one().adds == 99


def test_save_sales_replaces_month(raw_db):
    rows = [
        {"month": date(2026, 1, 1), "country": "US", "sku": "G (1)", "package_id": 1,
         "product_name": "G", "platform": "Windows", "net_units": 10, "net_sales_usd": 100.0},
    ]
    raw.save_sales(date(2026, 1, 1), rows)
    raw.save_sales(date(2026, 1, 1), rows)
    assert _count(raw_db, SalesByCountry) == 1


def test_save_reviews_upsert_by_id(raw_db):
    base = {
        "recommendation_id": "abc", "app_id": 1, "language": "english", "voted_up": True,
        "votes_up": 1, "votes_funny": 0, "playtime_at_review_min": 10,
        "created_at": None, "review_text": "v1", "collected_at": utcnow(),
    }
    raw.save_reviews([base])
    raw.save_reviews([dict(base, review_text="v2", voted_up=False, collected_at=utcnow())])
    assert _count(raw_db, Review) == 1  # merged by recommendation_id, not duplicated
    with Session(raw_db) as s:
        rev = s.get(Review, "abc")
        assert rev.review_text == "v2" and rev.voted_up is False


def test_save_playtime_snapshot_replaces_and_guards(raw_db):
    snap = {"app_id": 1, "snapshot_date": date(2026, 1, 1), "lifetime_users": 100,
            "avg_minutes": 60, "median_minutes": 30, "distribution": {"10": 50}}
    assert raw.save_playtime(snap) == 1
    raw.save_playtime(dict(snap, lifetime_users=200))
    assert _count(raw_db, PlaytimeSnapshot) == 1
    with Session(raw_db) as s:
        assert s.scalars(select(PlaytimeSnapshot)).one().lifetime_users == 200
    assert raw.save_playtime(None) == 0  # None guard, no write


def test_save_marketing_owners_replaces_and_guards(raw_db):
    snap = {"app_id": 1, "snapshot_date": date(2026, 1, 1),
            "owners_pct": 40.0, "non_owners_pct": 60.0}
    assert raw.save_marketing_owners(1, snap) == 1
    raw.save_marketing_owners(1, dict(snap, owners_pct=55.0))
    assert _count(raw_db, MarketingOwners) == 1
    assert raw.save_marketing_owners(1, None) == 0
