"""Playtime — tempo di gioco lifetime: medio/mediano + curva di distribuzione."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data

st.set_page_config(page_title="Playtime · SteamAgent", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempo di gioco (lifetime)")

df = data.playtime()
if df.empty:
    data.empty_note("playtime")
    data.sidebar_refresh()
    st.stop()

# Solo lo snapshot piu' recente per gioco
df = df.sort_values("snapshot_date").groupby("app_id", as_index=False).tail(1)
df = data.filter_games(df, key="pt_games")
if df.empty:
    st.warning("Nessun gioco selezionato.")
    data.sidebar_refresh()
    st.stop()

avg_w = (
    (df["avg_minutes"] * df["lifetime_users"]).sum() / df["lifetime_users"].sum()
    if df["lifetime_users"].sum()
    else 0
)
data.kpis(
    [
        ("Giochi con stats", data.fmt_int(df["app_id"].nunique())),
        ("Utenti misurati", data.fmt_int(df["lifetime_users"].sum())),
        ("Tempo medio (pond.)", data.mins_label(avg_w) if avg_w else "—"),
        ("Snapshot", str(df["snapshot_date"].max().date())),
    ]
)
st.divider()

st.subheader("Tempo mediano per gioco (engagement)")
rank = df.dropna(subset=["median_minutes"]).sort_values("median_minutes", ascending=False)
st.altair_chart(
    alt.Chart(rank)
    .mark_bar(color="#66c0f4")
    .encode(
        x=alt.X("median_minutes:Q", title="Minuti (mediana)"),
        y=alt.Y("game:N", sort="-x", title=None),
        tooltip=["game:N", alt.Tooltip("median_minutes:Q", title="Mediana (min)"),
                 alt.Tooltip("avg_minutes:Q", title="Media (min)"),
                 alt.Tooltip("lifetime_users:Q", title="Utenti", format=",.0f")],
    )
    .properties(height=max(240, 26 * len(rank))),
    width="stretch",
)

st.subheader("Curva di distribuzione")
st.caption("% di giocatori che hanno superato ciascuna soglia di tempo giocato.")
rows = []
for _, r in df.iterrows():
    for k, pct in (r["distribution"] or {}).items():
        try:
            mins = int(k)
        except (TypeError, ValueError):
            continue
        rows.append({"game": r["game"], "mins": mins,
                     "soglia": data.mins_label(mins), "pct": pct})

if not rows:
    st.info("Distribuzione non disponibile per la selezione.")
else:
    dist = pd.DataFrame(rows)
    order = [data.mins_label(m) for m in sorted(dist["mins"].unique())]
    st.altair_chart(
        alt.Chart(dist)
        .mark_line(point=True)
        .encode(
            x=alt.X("soglia:N", sort=order, title="Soglia di tempo giocato"),
            y=alt.Y("pct:Q", title="% giocatori"),
            color=alt.Color("game:N", title="Gioco"),
            tooltip=["game:N", "soglia:N", alt.Tooltip("pct:Q", title="%")],
        )
        .properties(height=340),
        width="stretch",
    )

st.subheader("Dettaglio")
st.dataframe(
    df[["game", "snapshot_date", "lifetime_users", "avg_minutes", "median_minutes"]]
    .sort_values("median_minutes", ascending=False),
    width="stretch",
    hide_index=True,
    column_config={
        "avg_minutes": st.column_config.NumberColumn("Media (min)", format="%.0f"),
        "median_minutes": st.column_config.NumberColumn("Mediana (min)", format="%.0f"),
        "lifetime_users": st.column_config.NumberColumn("Utenti", format="%.0f"),
    },
)
data.download(df.drop(columns=["distribution"], errors="ignore"), "playtime.csv")
data.sidebar_refresh()
