"""Reusable query + semantic layer over the warehouse.

Pure pandas/SQLAlchemy — no Streamlit, no UI. This is the single place that
encodes the business rules for reading the collected data:

  * readable game names from the portfolio config (`name_map`, `with_game`);
  * the sales ``product_name`` -> appid mapping, longest-prefix so DLC and
    soundtracks roll up into their base game (`sales_with_game`);
  * JSON columns (playtime ``distribution``) decoded to dicts (`playtime`).

Every consumer — the Streamlit dashboard, the planned NL->SQL assistant, a
future MCP server — shares one correct view of the data by importing this
module instead of re-querying the tables by hand. Functions accept an optional
SQLAlchemy ``engine`` (default: the shared one in ``storage.db``) so the layer
can be pointed at any database, which also makes it testable in isolation.
"""
from __future__ import annotations

import html
import json
import re

import pandas as pd
from sqlalchemy.engine import Engine

from steam_agent.games import load_games
from steam_agent.storage.db import engine as default_engine


def _resolve(engine: Engine | None) -> Engine:
    return engine if engine is not None else default_engine


# ---------------------------------------------------------------- DB reading
def read_table(
    table: str,
    engine: Engine | None = None,
    date_cols: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Read a whole table into a DataFrame (empty frame if it doesn't exist yet).

    ``table`` is one of our own table names — it is interpolated into the query,
    so never pass untrusted input here.
    """
    try:
        return pd.read_sql_query(
            f"SELECT * FROM {table}", _resolve(engine), parse_dates=list(date_cols)
        )
    except Exception:  # table not created yet
        return pd.DataFrame()


# ----------------------------------------------------------- name resolution
def _unescape(s: str) -> str:
    """Repeated html.unescape (some names are escaped several times)."""
    s = s or ""
    prev = None
    while prev != s:
        prev, s = s, html.unescape(s)
    return s


def _norm(s: str) -> str:
    """Normalized form for name matching: lowercase, no punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", _unescape(s).lower()).strip()


def name_map() -> dict[int, str]:
    """{appid: name} from the portfolio config (de-escaped names)."""
    return {int(g["appid"]): _unescape(g["name"]) for g in load_games() if g.get("appid")}


def with_game(df: pd.DataFrame, col: str = "app_id") -> pd.DataFrame:
    """Add the readable ``game`` column derived from ``app_id``."""
    if df.empty:
        df = df.copy()
        df["game"] = pd.Series(dtype="object")
        return df
    df = df.copy()
    df["game"] = df[col].map(name_map()).fillna(df[col].astype(str))
    return df


# ------------------------------------------------------------ dataset readers
def wishlist(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("wishlist_daily", engine, ("date",)))


def players(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("players_daily", engine, ("date",)))


def traffic(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("traffic_daily", engine, ("date",)))


def reviews(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("review", engine, ("created_at",)))


def snapshots(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("game_snapshot", engine, ("collected_at",)))


# Steam's "Over Time" series occasionally begin with a stray point detached from
# the real, daily-continuous data (e.g. a single visit years before launch). The
# series are daily, so a leading gap this large is never legitimate; left in, it
# stretches the dashboard's date range and chart axis back to a bogus start.
_MARKETING_LEADING_GAP_DAYS = 90


def _drop_leading_outliers(
    df: pd.DataFrame, gap_days: int = _MARKETING_LEADING_GAP_DAYS
) -> pd.DataFrame:
    """Per app, drop stray leading points detached from the daily-continuous series."""
    if df.empty or "app_id" not in df or "date" not in df:
        return df
    parts = []
    for _, grp in df.groupby("app_id", sort=False):
        days = pd.DatetimeIndex(grp["date"].drop_duplicates().sort_values())
        cut = 0
        while cut + 1 < len(days) and (days[cut + 1] - days[cut]).days > gap_days:
            cut += 1
        parts.append(grp[grp["date"] >= days[cut]] if len(days) else grp)
    return pd.concat(parts, ignore_index=True) if parts else df


def marketing(engine: Engine | None = None) -> pd.DataFrame:
    return _drop_leading_outliers(
        with_game(read_table("marketing_daily", engine, ("date",)))
    )


def marketing_owners(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("marketing_owners", engine, ("snapshot_date",)))


def marketing_country(engine: Engine | None = None) -> pd.DataFrame:
    return with_game(read_table("marketing_country", engine, ("snapshot_date",)))


def sales(engine: Engine | None = None) -> pd.DataFrame:
    return read_table("sales_by_country", engine, ("month",))


def _as_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return {}
    return {}


def playtime(engine: Engine | None = None) -> pd.DataFrame:
    df = with_game(read_table("playtime_snapshot", engine, ("snapshot_date",)))
    if not df.empty:
        df["distribution"] = df["distribution"].map(_as_dict)
    return df


def sales_with_game(engine: Engine | None = None) -> pd.DataFrame:
    """Sales with ``app_id``/``game`` derived from ``product_name`` (match by name,
    longest prefix: so DLC/soundtracks roll up into the base game)."""
    df = sales(engine)
    if df.empty:
        df = df.copy()
        df["app_id"] = pd.Series(dtype="Int64")
        df["game"] = pd.Series(dtype="object")
        return df
    df = df.copy()
    df["product_name"] = df["product_name"].fillna("").map(_unescape)
    # normalized catalog, from longest to shortest name (most specific prefix)
    cat = sorted(((_norm(n), a, n) for a, n in name_map().items()), key=lambda t: -len(t[0]))
    exact = {nn: (a, n) for nn, a, n in cat}
    amap: dict[str, object] = {}
    gmap: dict[str, str] = {}
    for prod in df["product_name"].unique():
        pn = _norm(prod)
        if pn in exact:
            aid, g = exact[pn]
        else:
            aid, g = pd.NA, prod or "(unknown)"
            for nn, a, n in cat:
                if nn and pn.startswith(nn):
                    aid, g = a, n
                    break
        amap[prod], gmap[prod] = aid, g
    df["app_id"] = df["product_name"].map(amap).astype("Int64")
    df["game"] = df["product_name"].map(gmap)
    return df
