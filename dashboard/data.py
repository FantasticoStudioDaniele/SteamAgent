"""Streamlit data facade: caching + UI helpers over `steam_agent.analytics`.

The query/semantic layer lives in `steam_agent.analytics` (reusable, no
Streamlit — shared by the dashboard, the planned NL->SQL assistant and any MCP
server). This module only adds the dashboard concerns: `st.cache_data` caching
(5-min TTL, cleared by the "Refresh data" button) and the small UI/formatting
helpers the pages share. Pages keep importing `data` and calling `data.X`.
"""
from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from steam_agent import analytics
from steam_agent.storage.db import init_db

init_db()
alt.data_transformers.disable_max_rows()

TTL = 300  # seconds


# --------------------------------------------------- cached data accessors
# Thin cached wrappers over the analytics layer: caching is a dashboard concern,
# so it lives here and not in the reusable module.
@st.cache_data(ttl=TTL, show_spinner=False)
def name_map() -> dict[int, str]:
    return analytics.name_map()


@st.cache_data(ttl=TTL, show_spinner=False)
def wishlist() -> pd.DataFrame:
    return analytics.wishlist()


@st.cache_data(ttl=TTL, show_spinner=False)
def players() -> pd.DataFrame:
    return analytics.players()


@st.cache_data(ttl=TTL, show_spinner=False)
def traffic() -> pd.DataFrame:
    return analytics.traffic()


@st.cache_data(ttl=TTL, show_spinner=False)
def reviews() -> pd.DataFrame:
    return analytics.reviews()


@st.cache_data(ttl=TTL, show_spinner=False)
def snapshots() -> pd.DataFrame:
    return analytics.snapshots()


@st.cache_data(ttl=TTL, show_spinner=False)
def marketing() -> pd.DataFrame:
    return analytics.marketing()


@st.cache_data(ttl=TTL, show_spinner=False)
def marketing_owners() -> pd.DataFrame:
    return analytics.marketing_owners()


@st.cache_data(ttl=TTL, show_spinner=False)
def marketing_country() -> pd.DataFrame:
    return analytics.marketing_country()


@st.cache_data(ttl=TTL, show_spinner=False)
def sales() -> pd.DataFrame:
    return analytics.sales()


@st.cache_data(ttl=TTL, show_spinner=False)
def playtime() -> pd.DataFrame:
    return analytics.playtime()


@st.cache_data(ttl=TTL, show_spinner=False)
def sales_with_game() -> pd.DataFrame:
    return analytics.sales_with_game()


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
    # Let the range reach today even when the latest data is a few days old: the
    # calendar's relative presets ("Past week/month/year") end *today*, so a
    # max_value pinned to the last data day makes them trip date_input's
    # out-of-range error. The filter below still clips to whatever data exists.
    sel = st.sidebar.date_input(
        label, (lo, hi), min_value=lo, max_value=max(hi, date.today()), key=key
    )
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
