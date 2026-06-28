"""Giocatori — DAU e picco di utenti concorrenti (serie storica)."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Giocatori · SteamAgent", page_icon="👥", layout="wide")
st.title("👥 Giocatori (DAU)")

df = data.players()
if df.empty:
    data.empty_note("players/DAU")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="pl_games")
df = data.filter_dates(df, "date", key="pl_dates")
if df.empty:
    st.warning("Nessuna riga con i filtri correnti.")
    data.sidebar_refresh()
    st.stop()

avg_dau = df["daily_active_users"].mean()
peak = int(df["peak_concurrent_users"].max())
last_day = df["date"].max()
last_dau = int(df[df["date"] == last_day]["daily_active_users"].sum())

data.kpis(
    [
        ("DAU medio (giorno·gioco)", data.fmt_int(avg_dau)),
        ("Picco concorrenti", data.fmt_int(peak)),
        ("DAU ultimo giorno", data.fmt_int(last_dau)),
        ("Giorni tracciati", data.fmt_int(df["date"].nunique())),
    ]
)
st.divider()

break_by_game = st.checkbox("Dettaglia per gioco", value=False)

st.subheader("DAU nel tempo")
if break_by_game:
    series = df.groupby(["date", "game"], as_index=False)["daily_active_users"].sum()
    chart = alt.Chart(series).mark_line().encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("daily_active_users:Q", title="DAU"),
        color=alt.Color("game:N", title="Gioco"),
        tooltip=["date:T", "game:N", alt.Tooltip("daily_active_users:Q", format=",.0f")],
    )
else:
    series = df.groupby("date", as_index=False)["daily_active_users"].sum()
    chart = alt.Chart(series).mark_area(color="#66c0f4", opacity=0.5,
                                        line={"color": "#66c0f4"}).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("daily_active_users:Q", title="DAU (somma)"),
        tooltip=["date:T", alt.Tooltip("daily_active_users:Q", format=",.0f")],
    )
st.altair_chart(chart.properties(height=320), width="stretch")

st.subheader("Picco di utenti concorrenti nel tempo")
conc = df.groupby("date", as_index=False)["peak_concurrent_users"].max()
st.altair_chart(
    alt.Chart(conc)
    .mark_line(color="#f4a020")
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("peak_concurrent_users:Q", title="Picco concorrenti"),
        tooltip=["date:T", alt.Tooltip("peak_concurrent_users:Q", format=",.0f")],
    )
    .properties(height=280),
    width="stretch",
)

st.subheader("Top giochi per picco concorrenti")
g = (
    df.groupby("game", as_index=False)["peak_concurrent_users"]
    .max()
    .sort_values("peak_concurrent_users", ascending=False)
    .head(15)
)
st.altair_chart(
    alt.Chart(g)
    .mark_bar(color="#66c0f4")
    .encode(
        x=alt.X("peak_concurrent_users:Q", title="Picco"),
        y=alt.Y("game:N", sort="-x", title=None),
        tooltip=["game:N", alt.Tooltip("peak_concurrent_users:Q", format=",.0f")],
    )
    .properties(height=380),
    width="stretch",
)

st.subheader("Dettaglio")
st.dataframe(
    df[["date", "game", "daily_active_users", "peak_concurrent_users"]]
    .sort_values("date", ascending=False),
    width="stretch",
    hide_index=True,
)
data.download(df, "giocatori.csv")
data.sidebar_refresh()
