"""SteamAgent — Dashboard (Phase 4).

Start:  uv run streamlit run dashboard/app.py
        (extra deps: uv sync --extra dashboard)

Overview page: portfolio KPIs + main trends + per-game scorecard.
The detail pages live in `dashboard/pages/`.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from steam_agent.settings import settings

import data

st.set_page_config(page_title="SteamAgent", page_icon="🎮", layout="wide")
st.title("🎮 SteamAgent — Overview")
st.caption(
    "Data from your Steam developer account"
    + (f" · {settings.studio_name}" if settings.studio_name else "")
)

sales = data.sales_with_game()
wl = data.wishlist()
pl = data.players()
rv = data.reviews()
pt = data.playtime()

if sales.empty and wl.empty and pl.empty and rv.empty:
    st.info(
        "Empty database. Populate the data from the CLI, e.g.:\n\n"
        "```\nuv run steam-agent collect-sales\nuv run steam-agent collect-wishlist\n"
        "uv run steam-agent collect-players\nuv run steam-agent collect-reviews\n```"
    )
    st.stop()

# --------------------------------------------------------------------- KPI
rev_tot = float(sales["net_sales_usd"].sum()) if not sales.empty else 0
units = int(sales["net_units"].sum()) if not sales.empty else 0
wl_net = int(wl["adds"].sum() - wl["deletes"].sum()) if not wl.empty else 0
rev_count = int(len(rv))
pos = float(rv["voted_up"].mean() * 100) if not rv.empty else 0
peak = int(pl["peak_concurrent_users"].max()) if not pl.empty else 0
n_games = len(data.name_map())

data.kpis(
    [
        ("Net revenue", data.fmt_money(rev_tot)),
        ("Units sold", data.fmt_int(units)),
        ("Net wishlists", data.fmt_int(wl_net)),
        ("Reviews", data.fmt_int(rev_count)),
        ("% positive", data.fmt_pct(pos)),
        ("Peak concurrent", data.fmt_int(peak)),
    ]
)
st.caption(f"Portfolio: {n_games} games tracked")
st.divider()

# ------------------------------------------------------------ trends
c1, c2 = st.columns([3, 2])

with c1:
    st.subheader("Net revenue by month")
    if sales.empty:
        data.empty_note("sales")
    else:
        m = sales.groupby("month", as_index=False)["net_sales_usd"].sum()
        chart = (
            alt.Chart(m)
            .mark_bar(color="#66c0f4")
            .encode(
                x=alt.X("month:T", title=None),
                y=alt.Y("net_sales_usd:Q", title="USD"),
                tooltip=[
                    alt.Tooltip("month:T", title="Month"),
                    alt.Tooltip("net_sales_usd:Q", title="USD", format=",.0f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, width="stretch")

with c2:
    st.subheader("Top games by revenue")
    if sales.empty:
        data.empty_note("sales")
    else:
        g = (
            sales.groupby("game", as_index=False)["net_sales_usd"]
            .sum()
            .sort_values("net_sales_usd", ascending=False)
            .head(12)
        )
        chart = (
            alt.Chart(g)
            .mark_bar(color="#66c0f4")
            .encode(
                x=alt.X("net_sales_usd:Q", title="USD"),
                y=alt.Y("game:N", sort="-x", title=None),
                tooltip=[
                    "game:N",
                    alt.Tooltip("net_sales_usd:Q", title="USD", format=",.0f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, width="stretch")

# --------------------------------------------------------- per-game scorecard
st.divider()
st.subheader("Per-game scorecard")

nm = data.name_map()
board = pd.DataFrame({"app_id": list(nm.keys()), "Game": list(nm.values())})
board["app_id"] = board["app_id"].astype("Int64")

if not sales.empty:
    s = sales.dropna(subset=["app_id"]).groupby("app_id", as_index=False).agg(
        Revenue=("net_sales_usd", "sum"), Units=("net_units", "sum")
    )
    board = board.merge(s, on="app_id", how="left")
if not wl.empty:
    w = wl.groupby("app_id", as_index=False).agg(a=("adds", "sum"), d=("deletes", "sum"))
    w["Net_wishlists"] = w["a"] - w["d"]
    board = board.merge(w[["app_id", "Net_wishlists"]], on="app_id", how="left")
if not pl.empty:
    p = pl.groupby("app_id", as_index=False).agg(Peak=("peak_concurrent_users", "max"))
    board = board.merge(p, on="app_id", how="left")
if not rv.empty:
    r = rv.groupby("app_id", as_index=False).agg(
        Reviews=("recommendation_id", "count"), pos=("voted_up", "mean")
    )
    r["Positive_%"] = (r["pos"] * 100).round(0)
    board = board.merge(r[["app_id", "Reviews", "Positive_%"]], on="app_id", how="left")
if not pt.empty:
    latest = pt.sort_values("snapshot_date").groupby("app_id", as_index=False).tail(1)
    board = board.merge(
        latest[["app_id", "median_minutes"]].rename(columns={"median_minutes": "Median_min"}),
        on="app_id",
        how="left",
    )

sort_col = "Revenue" if "Revenue" in board else "Game"
board = board.sort_values(sort_col, ascending=False, na_position="last").drop(columns=["app_id"])

st.dataframe(
    board,
    width="stretch",
    hide_index=True,
    column_config={
        "Revenue": st.column_config.NumberColumn("Revenue", format="$%.0f"),
        "Units": st.column_config.NumberColumn("Units", format="%.0f"),
        "Net_wishlists": st.column_config.NumberColumn("Net wishlists", format="%.0f"),
        "Peak": st.column_config.NumberColumn("Peak conc.", format="%.0f"),
        "Reviews": st.column_config.NumberColumn("Reviews", format="%.0f"),
        "Positive_%": st.column_config.NumberColumn("% pos.", format="%.0f%%"),
        "Median_min": st.column_config.NumberColumn("Median (min)", format="%.0f"),
    },
)
data.download(board, "scorecard.csv")

data.sidebar_refresh()
