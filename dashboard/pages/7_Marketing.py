"""Marketing — Visits/Impressions Over Time by source (jqplot time series)."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data

st.set_page_config(page_title="Marketing · SteamAgent", page_icon="📣", layout="wide")
st.title("📣 Marketing — visits & impressions over time")
st.caption("Time series by source, from the *Store Traffic Stats* page (per game).")

df = data.marketing()
if df.empty:
    data.empty_note("marketing")
    st.caption("Populate with: `uv run steam-agent collect-marketing`")
    data.sidebar_refresh()
    st.stop()

# --- game selection (top sources are per-game) ---
games = sorted(df["game"].dropna().unique().tolist())
game = st.sidebar.selectbox("Game", games, key="mk_game")
g = df[df["game"] == game].copy()

# --- period (shared picker: single-day guard + today-aware bounds) ---
g = data.filter_dates(g, "date", key="mk_dates")

# --- granularity (8 years of daily data is dense) ---
gran = st.sidebar.radio("Granularity", ["Month", "Week", "Day"], key="mk_gran")
freq = {"Day": "D", "Week": "W", "Month": "MS"}[gran]
drop_bot = st.sidebar.checkbox("Exclude Bot Traffic from visits", value=False, key="mk_bot")

if g.empty:
    st.warning("No data with the current filters.")
    data.sidebar_refresh()
    st.stop()


def resample(frame: pd.DataFrame) -> pd.DataFrame:
    out = (
        frame.set_index("date")
        .groupby("source")["value"]
        .resample(freq)
        .sum()
        .reset_index()
    )
    return out


def line_chart(frame: pd.DataFrame, title: str):
    r = resample(frame)
    order = (
        r.groupby("source")["value"].sum().sort_values(ascending=False).index.tolist()
    )
    return (
        alt.Chart(r)
        .mark_line()
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("value:Q", title=title),
            color=alt.Color("source:N", title="Source", sort=order),
            tooltip=["date:T", "source:N", alt.Tooltip("value:Q", format=",.0f")],
        )
        .properties(height=340)
    )


vis = g[g["metric"] == "visits"]
imp = g[g["metric"] == "impressions"]
if drop_bot:
    vis = vis[vis["source"] != "Bot Traffic"]

# KPI dal Total (preset-indipendente)
v_tot = int(vis[vis["source"] == "Total"]["value"].sum())
i_tot = int(imp[imp["source"] == "Total"]["value"].sum())
ctr = (v_tot / i_tot * 100) if i_tot else 0
data.kpis(
    [
        ("Visits (Total)", data.fmt_int(v_tot)),
        ("Impressions (Total)", data.fmt_int(i_tot)),
        ("CTR (visits/impr.)", data.fmt_pct(ctr)),
        ("Sources tracked", data.fmt_int(g["source"].nunique())),
    ]
)
st.divider()

st.subheader("Visits Over Time")
if vis.empty:
    st.info("No visits data.")
else:
    st.altair_chart(line_chart(vis, "Visits"), width="stretch")

st.subheader("Impressions Over Time")
if imp.empty:
    st.info("No impressions data.")
else:
    st.altair_chart(line_chart(imp, "Impressions"), width="stretch")

st.divider()
co, cc = st.columns([1, 2])
with co:
    st.subheader("Ownership")
    odf = data.marketing_owners()
    orow = odf[odf["game"] == game] if not odf.empty else odf
    if orow.empty:
        st.info("No ownership data.")
    else:
        latest = orow.sort_values("snapshot_date").iloc[-1]
        st.metric("Visits from Owners", data.fmt_pct(latest["owners_pct"]))
        pie = pd.DataFrame(
            {"type": ["Owner", "Non-Owner"],
             "pct": [latest["owners_pct"], latest["non_owners_pct"]]}
        )
        st.altair_chart(
            alt.Chart(pie)
            .mark_arc(innerRadius=55)
            .encode(
                theta="pct:Q",
                color=alt.Color("type:N", title=None,
                                scale=alt.Scale(domain=["Owner", "Non-Owner"],
                                                range=["#66c0f4", "#3a3f44"])),
                tooltip=["type:N", alt.Tooltip("pct:Q", format=".2f")],
            )
            .properties(height=240),
            width="stretch",
        )
        st.caption(f"Snapshot {latest['snapshot_date'].date()}")
with cc:
    st.subheader("Top countries by visits")
    cdf = data.marketing_country()
    crow = cdf[cdf["game"] == game] if not cdf.empty else cdf
    if crow.empty:
        st.info("No country data.")
    else:
        crow = crow[crow["snapshot_date"] == crow["snapshot_date"].max()]
        if st.checkbox("Exclude 'Unknown'", value=False, key="mk_unknown"):
            crow = crow[crow["country"].str.lower() != "unknown"]
        crow = crow.sort_values("visits", ascending=False)
        st.altair_chart(
            alt.Chart(crow)
            .mark_bar(color="#66c0f4")
            .encode(
                x=alt.X("visits:Q", title="Visits"),
                y=alt.Y("country:N", sort="-x", title=None),
                tooltip=["country:N", alt.Tooltip("visits:Q", format=",.0f"),
                         alt.Tooltip("pct:Q", title="share %", format=".0f")],
            )
            .properties(height=300),
            width="stretch",
        )

with st.expander("Detail / export"):
    show = g[["date", "metric", "source", "value"]].sort_values(
        ["metric", "date", "value"], ascending=[True, False, False]
    )
    st.dataframe(show, width="stretch", hide_index=True)
    data.download(show, f"marketing_{game}.csv")

data.sidebar_refresh()
