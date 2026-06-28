"""SQLAlchemy ORM models: raw landing + public + traffic + wishlist + sales + reviews."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RawPayload(Base):
    """Raw landing: every response from every source, historized by date."""

    __tablename__ = "raw_payload"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    app_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GameSnapshot(Base):
    """Typed snapshot: public metrics per appid and instant (time series)."""

    __tablename__ = "game_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    current_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_positive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_score_desc: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrafficDaily(Base):
    """Store page traffic per source, one day at a time (time series)."""

    __tablename__ = "traffic_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(160))
    feature: Mapped[str] = mapped_column(String(160))
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    owner_impressions: Mapped[int] = mapped_column(Integer, default=0)
    owner_visits: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("app_id", "date", "category", "feature", name="uq_traffic_daily"),
    )


class WishlistDaily(Base):
    """Wishlist actions per day (full time series since launch)."""

    __tablename__ = "wishlist_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    adds: Mapped[int] = mapped_column(Integer, default=0)
    deletes: Mapped[int] = mapped_column(Integer, default=0)
    purchases_activations: Mapped[int] = mapped_column(Integer, default=0)
    gifts: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("app_id", "date", name="uq_wishlist_daily"),)


class SalesByCountry(Base):
    """Monthly sales per product/country/platform (Net Units + Net Steam Sales USD)."""

    __tablename__ = "sales_by_country"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date, index=True)  # first day of the month
    country: Mapped[str] = mapped_column(String(80))
    sku: Mapped[str] = mapped_column(String(160))  # "Name (packageId)"
    package_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    product_name: Mapped[str] = mapped_column(String(160))
    platform: Mapped[str] = mapped_column(String(32))
    net_units: Mapped[int] = mapped_column(Integer, default=0)
    net_sales_usd: Mapped[float] = mapped_column(Float, default=0.0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("month", "country", "sku", "platform", name="uq_sales_by_country"),
    )


class Review(Base):
    """User review (public appreviews API). PK = recommendationid (upsert)."""

    __tablename__ = "review"

    recommendation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voted_up: Mapped[bool] = mapped_column(Boolean, default=False)
    votes_up: Mapped[int] = mapped_column(Integer, default=0)
    votes_funny: Mapped[int] = mapped_column(Integer, default=0)
    playtime_at_review_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayersDaily(Base):
    """DAU and peak concurrent users per day (time series since launch)."""

    __tablename__ = "players_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    daily_active_users: Mapped[int] = mapped_column(Integer, default=0)
    peak_concurrent_users: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("app_id", "date", name="uq_players_daily"),)


class MarketingDaily(Base):
    """'Visits/Impressions Over Time' time series per source (Marketing page).

    Data extracted from the live jqplot objects (no CSV). `metric` = 'visits'|'impressions',
    `source` = source label (the 'Total' series is included). One row per
    (app, day, metric, source).
    """

    __tablename__ = "marketing_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    metric: Mapped[str] = mapped_column(String(16))  # visits | impressions
    source: Mapped[str] = mapped_column(String(160))
    value: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("app_id", "date", "metric", "source", name="uq_marketing_daily"),
    )


class MarketingOwners(Base):
    """Owner vs Non-Owner visits breakdown (pie 'Ownership', dated snapshot)."""

    __tablename__ = "marketing_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    owners_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    non_owners_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("app_id", "snapshot_date", name="uq_marketing_owners"),
    )


class MarketingCountry(Base):
    """Top countries by visits (bars 'by Country', dated snapshot): count + share %."""

    __tablename__ = "marketing_country"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    country: Mapped[str] = mapped_column(String(80))
    visits: Mapped[int] = mapped_column(Integer, default=0)
    pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("app_id", "snapshot_date", "country", name="uq_marketing_country"),
    )


class PlaytimeSnapshot(Base):
    """LIFETIME playtime statistics (dated snapshot, not a time series).

    `distribution` = {minutes_threshold (str): user percentage}, e.g. {"10":73,"60":34}.
    """

    __tablename__ = "playtime_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(Integer, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    lifetime_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distribution: Mapped[dict] = mapped_column(JSON)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("app_id", "snapshot_date", name="uq_playtime_snapshot"),)
