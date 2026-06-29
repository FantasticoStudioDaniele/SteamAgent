"""Unit tests for the reusable analytics layer (no Streamlit, isolated DB).

These exercise the business rules that used to be locked inside the dashboard:
the sales product_name -> appid mapping (with DLC/soundtrack roll-up) and the
JSON `distribution` decoding. The layer is pointed at a throwaway SQLite engine,
which is exactly the reuse the extraction is meant to enable.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from steam_agent import analytics
from steam_agent.storage.models import (
    Base,
    MarketingDaily,
    PlaytimeSnapshot,
    SalesByCountry,
)


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}", future=True)
    Base.metadata.create_all(eng)
    # Fixed catalog so name matching is deterministic without config/games.yaml.
    monkeypatch.setattr(
        analytics,
        "load_games",
        lambda: [{"appid": 100, "name": "Super Game"}, {"appid": 200, "name": "Other Game"}],
    )
    return eng


def test_read_table_missing_returns_empty(engine):
    assert analytics.read_table("does_not_exist", engine).empty


def test_sales_with_game_maps_and_rolls_up(engine):
    with Session(engine) as s:
        s.add_all(
            [
                SalesByCountry(month=date(2025, 1, 1), country="US", sku="Super Game (111)",
                               product_name="Super Game", platform="Windows",
                               net_units=10, net_sales_usd=100.0, collected_at=_now()),
                SalesByCountry(month=date(2025, 1, 1), country="US", sku="Super Game OST (222)",
                               product_name="Super Game Soundtrack", platform="Windows",
                               net_units=2, net_sales_usd=8.0, collected_at=_now()),
                SalesByCountry(month=date(2025, 1, 1), country="US", sku="Mystery (999)",
                               product_name="Mystery", platform="Windows",
                               net_units=1, net_sales_usd=5.0, collected_at=_now()),
            ]
        )
        s.commit()

    df = analytics.sales_with_game(engine).set_index("product_name")
    # Base game and its soundtrack both roll up to the base appid (longest prefix).
    assert df.loc["Super Game", "app_id"] == 100
    assert df.loc["Super Game Soundtrack", "app_id"] == 100
    assert df.loc["Super Game Soundtrack", "game"] == "Super Game"
    # Unknown product: no appid, original name kept.
    assert pd.isna(df.loc["Mystery", "app_id"])
    assert df.loc["Mystery", "game"] == "Mystery"


def test_playtime_distribution_decoded_to_dict(engine):
    with Session(engine) as s:
        s.add(
            PlaytimeSnapshot(app_id=100, snapshot_date=date(2025, 1, 1), lifetime_users=50,
                             avg_minutes=120, median_minutes=30,
                             distribution={"10": 73, "60": 34}, collected_at=_now())
        )
        s.commit()

    df = analytics.playtime(engine)
    dist = df.iloc[0]["distribution"]
    assert isinstance(dist, dict)
    assert dist["10"] == 73
    assert df.iloc[0]["game"] == "Super Game"  # appid resolved to readable name


def test_marketing_drops_stray_leading_point(engine):
    """A stray point years before the real data must not stretch the date range."""
    start = date(2026, 4, 20)
    rows = [
        MarketingDaily(app_id=100, date=date(2017, 7, 20), metric="visits",
                       source="Total", value=2, collected_at=_now()),
    ]
    rows += [
        MarketingDaily(app_id=100, date=start + timedelta(days=k), metric="visits",
                       source="Total", value=k + 1, collected_at=_now())
        for k in range(10)  # real, daily-continuous data
    ]
    with Session(engine) as s:
        s.add_all(rows)
        s.commit()

    df = analytics.marketing(engine)
    assert df["date"].min().date() == start  # 2017 outlier dropped
    assert (df["date"].dt.year == 2017).sum() == 0
    assert len(df) == 10


def test_marketing_keeps_close_leading_point(engine):
    """A small leading gap is legitimate sparse data and must be kept."""
    rows = [
        MarketingDaily(app_id=100, date=date(2026, 4, 1), metric="visits",
                       source="Total", value=1, collected_at=_now()),
        MarketingDaily(app_id=100, date=date(2026, 4, 20), metric="visits",
                       source="Total", value=2, collected_at=_now()),  # 19-day gap
        MarketingDaily(app_id=100, date=date(2026, 4, 21), metric="visits",
                       source="Total", value=3, collected_at=_now()),
    ]
    with Session(engine) as s:
        s.add_all(rows)
        s.commit()

    df = analytics.marketing(engine)
    assert df["date"].min().date() == date(2026, 4, 1)  # nothing dropped
    assert len(df) == 3
