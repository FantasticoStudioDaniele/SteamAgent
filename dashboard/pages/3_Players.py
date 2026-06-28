"""Players — DAU and peak concurrent users (time series)."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Players · SteamAgent", page_icon="👥", layout="wide")
st.title("👥 Players (DAU)")

df = data.players()
if df.empty:
    data.empty_note("players/DAU")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="pl_games")
df = data.filter_dates(df, "date", key="pl_dates")
if df.empty:
    st.warning("No rows with the current filters.")
    data.sidebar_refresh()
    st.stop()

avg_dau = df["daily_active_users"].mean()
peak = int(df["peak_concurrent_users"].max())
last_day = df["date"].max()
last_dau = int(df[df["date"] == last_day]["daily_active_users"].sum())

data.kpis(
    [
        ("Mean DAU (day·game)", data.fmt_int(avg_dau)),
        ("Peak concurrent", data.fmt_int(peak)),
        ("DAU last day", data.fmt_int(last_dau)),
        ("Days tracked", data.fmt_int(df["date"].nunique())),
    ]
)
st.divider()

break_by_game = st.checkbox("Break down by game", value=False)

st.subheader("DAU over time")
if break_by_game:
    series = df.groupby(["date", "game"], as_index=False)["daily_active_users"].sum()
    chart = alt.Chart(series).mark_line().encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("daily_active_users:Q", title="DAU"),
        color=alt.Color("game:N", title="Game"),
        tooltip=["date:T", "game:N", alt.Tooltip("daily_active_users:Q", format=",.0f")],
    )
else:
    series = df.groupby("date", as_index=False)["daily_active_users"].sum()
    chart = alt.Chart(series).mark_area(color="#66c0f4", opacity=0.5,
                                        line={"color": "#66c0f4"}).encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("daily_active_users:Q", title="DAU (sum)"),
        tooltip=["date:T", alt.Tooltip("daily_active_users:Q", format=",.0f")],
    )
st.altair_chart(chart.properties(height=320), width="stretch")

st.subheader("Peak concurrent users over time")
conc = df.groupby("date", as_index=False)["peak_concurrent_users"].max()
st.altair_chart(
    alt.Chart(conc)
    .mark_line(color="#f4a020")
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("peak_concurrent_users:Q", title="Peak concurrent"),
        tooltip=["date:T", alt.Tooltip("peak_concurrent_users:Q", format=",.0f")],
    )
    .properties(height=280),
    width="stretch",
)

st.subheader("Top games by peak concurrent")
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
        x=alt.X("peak_concurrent_users:Q", title="Peak"),
        y=alt.Y("game:N", sort="-x", title=None),
        tooltip=["game:N", alt.Tooltip("peak_concurrent_users:Q", format=",.0f")],
    )
    .properties(height=380),
    width="stretch",
)

st.subheader("Detail")
st.dataframe(
    df[["date", "game", "daily_active_users", "peak_concurrent_users"]]
    .sort_values("date", ascending=False),
    width="stretch",
    hide_index=True,
)
data.download(df, "players.csv")
data.sidebar_refresh()
