"""Traffic — store page visits and impressions, by source."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Traffic · SteamAgent", page_icon="🚦", layout="wide")
st.title("🚦 Store traffic")
st.caption(
    "Detailed per-source breakdown for the days collected via `collect-traffic` "
    "(one day at a time). For visits/impressions **over time**, see the Marketing page."
)

df = data.traffic()
if df.empty:
    data.empty_note("traffic")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="tr_games")
df = data.filter_dates(df, "date", key="tr_dates")
cats = sorted(df["category"].dropna().unique().tolist())
chosen_c = st.sidebar.multiselect("Source categories", cats, key="tr_cat", placeholder="All")
if chosen_c:
    df = df[df["category"].isin(chosen_c)]

if df.empty:
    st.warning("No rows with the current filters.")
    data.sidebar_refresh()
    st.stop()

impr = int(df["impressions"].sum())
vis = int(df["visits"].sum())
ctr = (vis / impr * 100) if impr else 0

data.kpis(
    [
        ("Impressions", data.fmt_int(impr)),
        ("Visits", data.fmt_int(vis)),
        ("CTR", data.fmt_pct(ctr)),
        ("Sources", data.fmt_int(df["feature"].nunique())),
    ]
)
st.divider()

st.subheader("Visits over time")
daily = df.groupby("date", as_index=False).agg(Visits=("visits", "sum"),
                                               Impressions=("impressions", "sum"))
long = daily.melt("date", value_vars=["Visits", "Impressions"],
                  var_name="metric", value_name="count")
st.altair_chart(
    alt.Chart(long)
    .mark_line()
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("count:Q", title="Count"),
        color=alt.Color("metric:N", title=None,
                        scale=alt.Scale(domain=["Visits", "Impressions"],
                                        range=["#66c0f4", "#9aa0a6"])),
        tooltip=["date:T", "metric:N", alt.Tooltip("count:Q", format=",.0f")],
    )
    .properties(height=300),
    width="stretch",
)

st.subheader("Top sources by visits")
df = df.copy()
df["source"] = df["category"].fillna("") + " · " + df["feature"].fillna("")
g = (
    df.groupby("source", as_index=False)
    .agg(Visits=("visits", "sum"), Impressions=("impressions", "sum"))
    .sort_values("Visits", ascending=False)
    .head(20)
)
st.altair_chart(
    alt.Chart(g)
    .mark_bar(color="#66c0f4")
    .encode(
        x=alt.X("Visits:Q", title="Visits"),
        y=alt.Y("source:N", sort="-x", title=None),
        tooltip=["source:N", alt.Tooltip("Visits:Q", format=",.0f"),
                 alt.Tooltip("Impressions:Q", format=",.0f")],
    )
    .properties(height=460),
    width="stretch",
)

st.subheader("Detail")
st.dataframe(
    df[["date", "game", "category", "feature", "impressions", "visits",
        "owner_impressions", "owner_visits"]]
    .sort_values(["date", "visits"], ascending=[False, False]),
    width="stretch",
    hide_index=True,
)
data.download(df, "traffic.csv")
data.sidebar_refresh()
