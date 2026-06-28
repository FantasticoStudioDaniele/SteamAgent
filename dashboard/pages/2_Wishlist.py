"""Wishlist — aggiunte/rimozioni giornaliere, saldo cumulato, conversioni."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Wishlist · SteamAgent", page_icon="❤️", layout="wide")
st.title("❤️ Wishlist")

df = data.wishlist()
if df.empty:
    data.empty_note("wishlist")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="wl_games")
df = data.filter_dates(df, "date", key="wl_dates")
if df.empty:
    st.warning("Nessuna riga con i filtri correnti.")
    data.sidebar_refresh()
    st.stop()

adds = int(df["adds"].sum())
dels = int(df["deletes"].sum())
conv = int(df["purchases_activations"].sum())
net = adds - dels

data.kpis(
    [
        ("Aggiunte", data.fmt_int(adds)),
        ("Rimozioni", data.fmt_int(dels)),
        ("Saldo netto", data.fmt_int(net)),
        ("Acquisti/attivazioni", data.fmt_int(conv)),
    ]
)
st.divider()

# Andamento giornaliero adds vs deletes (aggregato sui giochi selezionati)
st.subheader("Aggiunte vs rimozioni (giornaliero)")
daily = df.groupby("date", as_index=False).agg(
    Aggiunte=("adds", "sum"),
    Rimozioni=("deletes", "sum"),
    Acquisti=("purchases_activations", "sum"),
)
long = daily.melt("date", value_vars=["Aggiunte", "Rimozioni", "Acquisti"],
                  var_name="tipo", value_name="valore")
st.altair_chart(
    alt.Chart(long)
    .mark_line()
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("valore:Q", title="Conteggio"),
        color=alt.Color("tipo:N", title=None,
                        scale=alt.Scale(domain=["Aggiunte", "Rimozioni", "Acquisti"],
                                        range=["#66c0f4", "#e06666", "#93c47d"])),
        tooltip=["date:T", "tipo:N", alt.Tooltip("valore:Q", format=",.0f")],
    )
    .properties(height=300),
    width="stretch",
)

# Saldo wishlist cumulato (stima outstanding = cumsum(adds - deletes - conversioni))
st.subheader("Saldo wishlist cumulato (stima outstanding)")
daily = daily.sort_values("date")
daily["Outstanding"] = (daily["Aggiunte"] - daily["Rimozioni"] - daily["Acquisti"]).cumsum()
st.altair_chart(
    alt.Chart(daily)
    .mark_area(color="#66c0f4", opacity=0.5, line={"color": "#66c0f4"})
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("Outstanding:Q", title="Wishlist attive (stima)"),
        tooltip=["date:T", alt.Tooltip("Outstanding:Q", format=",.0f")],
    )
    .properties(height=280),
    width="stretch",
)
st.caption("Stima: cumulata di aggiunte − rimozioni − acquisti/attivazioni.")

st.subheader("Top giochi per aggiunte")
g = (
    df.groupby("game", as_index=False)["adds"]
    .sum()
    .sort_values("adds", ascending=False)
    .head(15)
)
st.altair_chart(
    alt.Chart(g)
    .mark_bar(color="#66c0f4")
    .encode(
        x=alt.X("adds:Q", title="Aggiunte"),
        y=alt.Y("game:N", sort="-x", title=None),
        tooltip=["game:N", alt.Tooltip("adds:Q", format=",.0f")],
    )
    .properties(height=380),
    width="stretch",
)

st.subheader("Dettaglio")
st.dataframe(
    df[["date", "game", "adds", "deletes", "purchases_activations", "gifts"]]
    .sort_values("date", ascending=False),
    width="stretch",
    hide_index=True,
)
data.download(df, "wishlist.csv")
data.sidebar_refresh()
