"""Wishlist — daily additions/removals, cumulative balance, conversions."""
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
    st.warning("No rows with the current filters.")
    data.sidebar_refresh()
    st.stop()

adds = int(df["adds"].sum())
dels = int(df["deletes"].sum())
conv = int(df["purchases_activations"].sum())
net = adds - dels

data.kpis(
    [
        ("Additions", data.fmt_int(adds)),
        ("Removals", data.fmt_int(dels)),
        ("Net balance", data.fmt_int(net)),
        ("Purchases/activations", data.fmt_int(conv)),
    ]
)
st.divider()

# Daily adds vs deletes trend (aggregated over the selected games)
st.subheader("Additions vs removals (daily)")
daily = df.groupby("date", as_index=False).agg(
    Additions=("adds", "sum"),
    Removals=("deletes", "sum"),
    Purchases=("purchases_activations", "sum"),
)
long = daily.melt("date", value_vars=["Additions", "Removals", "Purchases"],
                  var_name="type", value_name="count")
st.altair_chart(
    alt.Chart(long)
    .mark_line()
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("count:Q", title="Count"),
        color=alt.Color("type:N", title=None,
                        scale=alt.Scale(domain=["Additions", "Removals", "Purchases"],
                                        range=["#66c0f4", "#e06666", "#93c47d"])),
        tooltip=["date:T", "type:N", alt.Tooltip("count:Q", format=",.0f")],
    )
    .properties(height=300),
    width="stretch",
)

# Cumulative wishlist balance (outstanding estimate = cumsum(adds - deletes - conversions))
st.subheader("Cumulative wishlist balance (outstanding estimate)")
daily = daily.sort_values("date")
daily["Outstanding"] = (daily["Additions"] - daily["Removals"] - daily["Purchases"]).cumsum()
st.altair_chart(
    alt.Chart(daily)
    .mark_area(color="#66c0f4", opacity=0.5, line={"color": "#66c0f4"})
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("Outstanding:Q", title="Active wishlists (estimate)"),
        tooltip=["date:T", alt.Tooltip("Outstanding:Q", format=",.0f")],
    )
    .properties(height=280),
    width="stretch",
)
st.caption("Estimate: cumulative additions − removals − purchases/activations.")

st.subheader("Top games by additions")
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
        x=alt.X("adds:Q", title="Additions"),
        y=alt.Y("game:N", sort="-x", title=None),
        tooltip=["game:N", alt.Tooltip("adds:Q", format=",.0f")],
    )
    .properties(height=380),
    width="stretch",
)

st.subheader("Detail")
st.dataframe(
    df[["date", "game", "adds", "deletes", "purchases_activations", "gifts"]]
    .sort_values("date", ascending=False),
    width="stretch",
    hide_index=True,
)
data.download(df, "wishlist.csv")
data.sidebar_refresh()
