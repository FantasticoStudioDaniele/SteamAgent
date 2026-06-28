"""SteamAgent — Dashboard (Fase 4).

Avvio:  uv run streamlit run dashboard/app.py
        (deps extra: uv sync --extra dashboard)

Pagina di panoramica: KPI di portfolio + andamenti principali + scorecard
per gioco. Le pagine di dettaglio sono in `dashboard/pages/`.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from steam_agent.settings import settings

import data

st.set_page_config(page_title="SteamAgent", page_icon="🎮", layout="wide")
st.title("🎮 SteamAgent — Panoramica")
st.caption(
    "Dati del tuo account developer Steam"
    + (f" · {settings.studio_name}" if settings.studio_name else "")
)

sales = data.sales_with_game()
wl = data.wishlist()
pl = data.players()
rv = data.reviews()
pt = data.playtime()

if sales.empty and wl.empty and pl.empty and rv.empty:
    st.info(
        "Database vuoto. Popola i dati dalla CLI, per es.:\n\n"
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
        ("Ricavi netti", data.fmt_money(rev_tot)),
        ("Unità vendute", data.fmt_int(units)),
        ("Wishlist nette", data.fmt_int(wl_net)),
        ("Recensioni", data.fmt_int(rev_count)),
        ("% positive", data.fmt_pct(pos)),
        ("Picco concorrenti", data.fmt_int(peak)),
    ]
)
st.caption(f"Portfolio: {n_games} giochi tracciati")
st.divider()

# ------------------------------------------------------------ andamenti
c1, c2 = st.columns([3, 2])

with c1:
    st.subheader("Ricavi netti per mese")
    if sales.empty:
        data.empty_note("vendite")
    else:
        m = sales.groupby("month", as_index=False)["net_sales_usd"].sum()
        chart = (
            alt.Chart(m)
            .mark_bar(color="#66c0f4")
            .encode(
                x=alt.X("month:T", title=None),
                y=alt.Y("net_sales_usd:Q", title="USD"),
                tooltip=[
                    alt.Tooltip("month:T", title="Mese"),
                    alt.Tooltip("net_sales_usd:Q", title="USD", format=",.0f"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, width="stretch")

with c2:
    st.subheader("Top giochi per ricavi")
    if sales.empty:
        data.empty_note("vendite")
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

# --------------------------------------------------------- scorecard per gioco
st.divider()
st.subheader("Scorecard per gioco")

nm = data.name_map()
board = pd.DataFrame({"app_id": list(nm.keys()), "Gioco": list(nm.values())})
board["app_id"] = board["app_id"].astype("Int64")

if not sales.empty:
    s = sales.dropna(subset=["app_id"]).groupby("app_id", as_index=False).agg(
        Ricavi=("net_sales_usd", "sum"), Unità=("net_units", "sum")
    )
    board = board.merge(s, on="app_id", how="left")
if not wl.empty:
    w = wl.groupby("app_id", as_index=False).agg(a=("adds", "sum"), d=("deletes", "sum"))
    w["Wishlist_nette"] = w["a"] - w["d"]
    board = board.merge(w[["app_id", "Wishlist_nette"]], on="app_id", how="left")
if not pl.empty:
    p = pl.groupby("app_id", as_index=False).agg(Picco=("peak_concurrent_users", "max"))
    board = board.merge(p, on="app_id", how="left")
if not rv.empty:
    r = rv.groupby("app_id", as_index=False).agg(
        Recensioni=("recommendation_id", "count"), pos=("voted_up", "mean")
    )
    r["Positive_%"] = (r["pos"] * 100).round(0)
    board = board.merge(r[["app_id", "Recensioni", "Positive_%"]], on="app_id", how="left")
if not pt.empty:
    latest = pt.sort_values("snapshot_date").groupby("app_id", as_index=False).tail(1)
    board = board.merge(
        latest[["app_id", "median_minutes"]].rename(columns={"median_minutes": "Mediana_min"}),
        on="app_id",
        how="left",
    )

sort_col = "Ricavi" if "Ricavi" in board else "Gioco"
board = board.sort_values(sort_col, ascending=False, na_position="last").drop(columns=["app_id"])

st.dataframe(
    board,
    width="stretch",
    hide_index=True,
    column_config={
        "Ricavi": st.column_config.NumberColumn("Ricavi", format="$%.0f"),
        "Unità": st.column_config.NumberColumn("Unità", format="%.0f"),
        "Wishlist_nette": st.column_config.NumberColumn("Wishlist nette", format="%.0f"),
        "Picco": st.column_config.NumberColumn("Picco conc.", format="%.0f"),
        "Recensioni": st.column_config.NumberColumn("Recensioni", format="%.0f"),
        "Positive_%": st.column_config.NumberColumn("% pos.", format="%.0f%%"),
        "Mediana_min": st.column_config.NumberColumn("Mediana (min)", format="%.0f"),
    },
)
data.download(board, "scorecard.csv")

data.sidebar_refresh()
