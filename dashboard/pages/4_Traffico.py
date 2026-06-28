"""Traffico — visite e impression della pagina store, per sorgente."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Traffico · SteamAgent", page_icon="🚦", layout="wide")
st.title("🚦 Traffico store")

df = data.traffic()
if df.empty:
    data.empty_note("traffico")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="tr_games")
df = data.filter_dates(df, "date", key="tr_dates")
cats = sorted(df["category"].dropna().unique().tolist())
chosen_c = st.sidebar.multiselect("Categorie sorgente", cats, key="tr_cat", placeholder="Tutte")
if chosen_c:
    df = df[df["category"].isin(chosen_c)]

if df.empty:
    st.warning("Nessuna riga con i filtri correnti.")
    data.sidebar_refresh()
    st.stop()

impr = int(df["impressions"].sum())
vis = int(df["visits"].sum())
ctr = (vis / impr * 100) if impr else 0

data.kpis(
    [
        ("Impression", data.fmt_int(impr)),
        ("Visite", data.fmt_int(vis)),
        ("CTR", data.fmt_pct(ctr)),
        ("Sorgenti", data.fmt_int(df["feature"].nunique())),
    ]
)
st.divider()

st.subheader("Visite nel tempo")
daily = df.groupby("date", as_index=False).agg(Visite=("visits", "sum"),
                                               Impression=("impressions", "sum"))
long = daily.melt("date", value_vars=["Visite", "Impression"],
                  var_name="metrica", value_name="valore")
st.altair_chart(
    alt.Chart(long)
    .mark_line()
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("valore:Q", title="Conteggio"),
        color=alt.Color("metrica:N", title=None,
                        scale=alt.Scale(domain=["Visite", "Impression"],
                                        range=["#66c0f4", "#9aa0a6"])),
        tooltip=["date:T", "metrica:N", alt.Tooltip("valore:Q", format=",.0f")],
    )
    .properties(height=300),
    width="stretch",
)

st.subheader("Top sorgenti per visite")
df = df.copy()
df["sorgente"] = df["category"].fillna("") + " · " + df["feature"].fillna("")
g = (
    df.groupby("sorgente", as_index=False)
    .agg(Visite=("visits", "sum"), Impression=("impressions", "sum"))
    .sort_values("Visite", ascending=False)
    .head(20)
)
st.altair_chart(
    alt.Chart(g)
    .mark_bar(color="#66c0f4")
    .encode(
        x=alt.X("Visite:Q", title="Visite"),
        y=alt.Y("sorgente:N", sort="-x", title=None),
        tooltip=["sorgente:N", alt.Tooltip("Visite:Q", format=",.0f"),
                 alt.Tooltip("Impression:Q", format=",.0f")],
    )
    .properties(height=460),
    width="stretch",
)

st.subheader("Dettaglio")
st.dataframe(
    df[["date", "game", "category", "feature", "impressions", "visits",
        "owner_impressions", "owner_visits"]]
    .sort_values(["date", "visits"], ascending=[False, False]),
    width="stretch",
    hide_index=True,
)
data.download(df, "traffico.csv")
data.sidebar_refresh()
