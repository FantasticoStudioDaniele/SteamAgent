"""Shared data access and UI helpers for the Streamlit dashboard.

Every page imports this module (`import data`). Tables are read via SQLAlchemy
(swappable engine: SQLite/Postgres) and cached with `st.cache_data` (TTL 5 min);
the "Refresh data" button clears the cache.
"""
from __future__ import annotations

import html
import json
import re

import altair as alt
import pandas as pd
import streamlit as st

from steam_agent.games import load_games
from steam_agent.storage.db import engine, init_db

init_db()
alt.data_transformers.disable_max_rows()

TTL = 300  # seconds


# ---------------------------------------------------------------- DB reading
@st.cache_data(ttl=TTL, show_spinner=False)
def _read(table: str, date_cols: tuple[str, ...] = ()) -> pd.DataFrame:
    """Read an entire table into a DataFrame (table names are our own constants)."""
    try:
        return pd.read_sql_query(
            f"SELECT * FROM {table}", engine, parse_dates=list(date_cols)
        )
    except Exception:  # table not present yet
        return pd.DataFrame()


def _unescape(s: str) -> str:
    """Repeated html.unescape (some names are escaped multiple times)."""
    s = s or ""
    prev = None
    while prev != s:
        prev, s = s, html.unescape(s)
    return s


def _norm(s: str) -> str:
    """Normalized form for name matching: lowercase, no punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", _unescape(s).lower()).strip()


@st.cache_data(ttl=TTL, show_spinner=False)
def name_map() -> dict[int, str]:
    """{appid: name} from the portfolio config (de-escaped names)."""
    return {int(g["appid"]): _unescape(g["name"]) for g in load_games() if g.get("appid")}


def _with_game(df: pd.DataFrame, col: str = "app_id") -> pd.DataFrame:
    """Add the `game` column (readable name) derived from `app_id`."""
    if df.empty:
        df = df.copy()
        df["game"] = pd.Series(dtype="object")
        return df
    df = df.copy()
    df["game"] = df[col].map(name_map()).fillna(df[col].astype(str))
    return df


def wishlist() -> pd.DataFrame:
    return _with_game(_read("wishlist_daily", ("date",)))


def players() -> pd.DataFrame:
    return _with_game(_read("players_daily", ("date",)))


def traffic() -> pd.DataFrame:
    return _with_game(_read("traffic_daily", ("date",)))


def reviews() -> pd.DataFrame:
    return _with_game(_read("review", ("created_at",)))


def snapshots() -> pd.DataFrame:
    return _with_game(_read("game_snapshot", ("collected_at",)))


def marketing() -> pd.DataFrame:
    return _with_game(_read("marketing_daily", ("date",)))


def marketing_owners() -> pd.DataFrame:
    return _with_game(_read("marketing_owners", ("snapshot_date",)))


def marketing_country() -> pd.DataFrame:
    return _with_game(_read("marketing_country", ("snapshot_date",)))


def sales() -> pd.DataFrame:
    return _read("sales_by_country", ("month",))


def _as_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        try:
            return json.loads(v)
        except Exception:
            return {}
    return {}


@st.cache_data(ttl=TTL, show_spinner=False)
def playtime() -> pd.DataFrame:
    df = _with_game(_read("playtime_snapshot", ("snapshot_date",)))
    if not df.empty:
        df["distribution"] = df["distribution"].map(_as_dict)
    return df


@st.cache_data(ttl=TTL, show_spinner=False)
def sales_with_game() -> pd.DataFrame:
    """Sales with `app_id`/`game` derived from `product_name` (match by name,
    longest prefix: so DLC/soundtracks roll up into the base game)."""
    df = sales()
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


# ------------------------------------------------------------- formatting
def fmt_int(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return "—"


def fmt_money(n, sym: str = "$") -> str:
    try:
        return f"{sym}{float(n):,.0f}".replace(",", ".")
    except Exception:
        return "—"


def fmt_pct(n) -> str:
    try:
        return f"{float(n):.0f}%"
    except Exception:
        return "—"


def mins_label(m) -> str:
    """Minutes -> readable label (10 min, 1 h, 2 h, ...)."""
    m = int(m)
    if m < 60:
        return f"{m} min"
    h = m / 60
    return f"{int(h)} h" if abs(h - round(h)) < 1e-9 else f"{h:.1f} h"


# ------------------------------------------------------------------ UI widgets
def kpis(items: list[tuple[str, str]]) -> None:
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)


def filter_games(df: pd.DataFrame, key: str, label: str = "Games") -> pd.DataFrame:
    if df.empty or "game" not in df:
        return df
    opts = sorted(df["game"].dropna().unique().tolist())
    chosen = st.sidebar.multiselect(label, opts, key=key, placeholder="All")
    return df[df["game"].isin(chosen)] if chosen else df


def filter_dates(df: pd.DataFrame, col: str, key: str, label: str = "Period") -> pd.DataFrame:
    if df.empty or col not in df or df[col].dropna().empty:
        return df
    lo = df[col].min().date()
    hi = df[col].max().date()
    if lo >= hi:  # only one day available: a range picker would error out
        st.sidebar.caption(f"{label}: {lo} (single day)")
        return df
    sel = st.sidebar.date_input(label, (lo, hi), min_value=lo, max_value=hi, key=key)
    if isinstance(sel, (list, tuple)) and len(sel) == 2:
        a = pd.Timestamp(sel[0])
        b = pd.Timestamp(sel[1]) + pd.Timedelta(days=1)
        df = df[(df[col] >= a) & (df[col] < b)]
    return df


def sidebar_refresh() -> None:
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption("Cache 5 min · local data")


def download(df: pd.DataFrame, name: str) -> None:
    st.download_button(
        "⬇️ Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=name,
        mime="text/csv",
    )


def empty_note(what: str) -> None:
    st.info(f"No data for **{what}**. Run the matching `collect-…` from the CLI.")
