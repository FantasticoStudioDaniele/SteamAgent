"""Vendite — ricavi netti e unità per mese, paese, gioco, piattaforma."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Vendite · SteamAgent", page_icon="💰", layout="wide")
st.title("💰 Vendite")

df = data.sales_with_game()
if df.empty:
    data.empty_note("vendite")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="sales_games")
df = data.filter_dates(df, "month", key="sales_dates")
plats = sorted(df["platform"].dropna().unique().tolist())
chosen_p = st.sidebar.multiselect("Piattaforme", plats, key="sales_plat", placeholder="Tutte")
if chosen_p:
    df = df[df["platform"].isin(chosen_p)]

if df.empty:
    st.warning("Nessuna riga con i filtri correnti.")
    data.sidebar_refresh()
    st.stop()

rev = float(df["net_sales_usd"].sum())
units = int(df["net_units"].sum())
n_countries = int(df["country"].nunique())
asp = rev / units if units else 0

data.kpis(
    [
        ("Ricavi netti", data.fmt_money(rev)),
        ("Unità nette", data.fmt_int(units)),
        ("Prezzo medio", data.fmt_money(asp)),
        ("Paesi", data.fmt_int(n_countries)),
    ]
)
st.divider()

# Ricavi + unità per mese
st.subheader("Andamento mensile")
m = df.groupby("month", as_index=False).agg(
    Ricavi=("net_sales_usd", "sum"), Unità=("net_units", "sum")
)
base = alt.Chart(m).encode(x=alt.X("month:T", title=None))
bars = base.mark_bar(color="#66c0f4").encode(
    y=alt.Y("Ricavi:Q", title="Ricavi (USD)"),
    tooltip=[alt.Tooltip("month:T", title="Mese"), alt.Tooltip("Ricavi:Q", format=",.0f")],
)
line = base.mark_line(color="#f4a020", point=True).encode(
    y=alt.Y("Unità:Q", title="Unità"),
    tooltip=[alt.Tooltip("month:T", title="Mese"), alt.Tooltip("Unità:Q", format=",.0f")],
)
st.altair_chart(
    alt.layer(bars, line).resolve_scale(y="independent").properties(height=320),
    width="stretch",
)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Top paesi per ricavi")
    g = (
        df.groupby("country", as_index=False)["net_sales_usd"]
        .sum()
        .sort_values("net_sales_usd", ascending=False)
        .head(15)
    )
    st.altair_chart(
        alt.Chart(g)
        .mark_bar(color="#66c0f4")
        .encode(
            x=alt.X("net_sales_usd:Q", title="USD"),
            y=alt.Y("country:N", sort="-x", title=None),
            tooltip=["country:N", alt.Tooltip("net_sales_usd:Q", format=",.0f")],
        )
        .properties(height=380),
        width="stretch",
    )
with c2:
    st.subheader("Top giochi per ricavi")
    g = (
        df.groupby("game", as_index=False)["net_sales_usd"]
        .sum()
        .sort_values("net_sales_usd", ascending=False)
        .head(15)
    )
    st.altair_chart(
        alt.Chart(g)
        .mark_bar(color="#66c0f4")
        .encode(
            x=alt.X("net_sales_usd:Q", title="USD"),
            y=alt.Y("game:N", sort="-x", title=None),
            tooltip=["game:N", alt.Tooltip("net_sales_usd:Q", format=",.0f")],
        )
        .properties(height=380),
        width="stretch",
    )

st.subheader("Mix per piattaforma")
pmix = df.groupby("platform", as_index=False).agg(
    Ricavi=("net_sales_usd", "sum"), Unità=("net_units", "sum")
)
st.altair_chart(
    alt.Chart(pmix)
    .mark_arc(innerRadius=60)
    .encode(
        theta="Ricavi:Q",
        color=alt.Color("platform:N", title="Piattaforma"),
        tooltip=["platform:N", alt.Tooltip("Ricavi:Q", format=",.0f")],
    )
    .properties(height=260),
    width="stretch",
)

st.subheader("Dettaglio")
st.dataframe(
    df[["month", "game", "product_name", "country", "platform", "net_units", "net_sales_usd"]]
    .sort_values(["month", "net_sales_usd"], ascending=[False, False]),
    width="stretch",
    hide_index=True,
)
data.download(df, "vendite.csv")
data.sidebar_refresh()
