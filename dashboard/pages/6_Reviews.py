"""Reviews — sentiment, volume, languages and text exploration."""
from __future__ import annotations

import altair as alt
import streamlit as st

import data

st.set_page_config(page_title="Reviews · SteamAgent", page_icon="⭐", layout="wide")
st.title("⭐ Reviews")

df = data.reviews()
if df.empty:
    data.empty_note("reviews")
    data.sidebar_refresh()
    st.stop()

df = data.filter_games(df, key="rv_games")
df = data.filter_dates(df, "created_at", key="rv_dates")
langs = sorted(df["language"].dropna().unique().tolist())
chosen_l = st.sidebar.multiselect("Languages", langs, key="rv_lang", placeholder="All")
if chosen_l:
    df = df[df["language"].isin(chosen_l)]
voto = st.sidebar.radio("Rating", ["All", "Positive only", "Negative only"], key="rv_voto")
if voto == "Positive only":
    df = df[df["voted_up"] == 1]
elif voto == "Negative only":
    df = df[df["voted_up"] == 0]

if df.empty:
    st.warning("No reviews with the current filters.")
    data.sidebar_refresh()
    st.stop()

tot = len(df)
pos = float(df["voted_up"].mean() * 100)
med_pt = df["playtime_at_review_min"].median()

data.kpis(
    [
        ("Reviews", data.fmt_int(tot)),
        ("% positive", data.fmt_pct(pos)),
        ("Languages", data.fmt_int(df["language"].nunique())),
        ("Median playtime at review", data.mins_label(med_pt) if med_pt and med_pt == med_pt else "—"),
    ]
)
st.divider()

c1, c2 = st.columns(2)
with c1:
    st.subheader("% positive by game")
    g = df.groupby("game", as_index=False).agg(n=("recommendation_id", "count"),
                                               pos=("voted_up", "mean"))
    g["pct"] = (g["pos"] * 100).round(0)
    g = g.sort_values("pct", ascending=False)
    st.altair_chart(
        alt.Chart(g)
        .mark_bar(color="#66c0f4")
        .encode(
            x=alt.X("pct:Q", title="% positive", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("game:N", sort="-x", title=None),
            tooltip=["game:N", alt.Tooltip("pct:Q", title="% pos."),
                     alt.Tooltip("n:Q", title="N")],
        )
        .properties(height=380),
        width="stretch",
    )
with c2:
    st.subheader("Most frequent languages")
    g = (
        df.groupby("language", as_index=False)
        .agg(n=("recommendation_id", "count"))
        .sort_values("n", ascending=False)
        .head(15)
    )
    st.altair_chart(
        alt.Chart(g)
        .mark_bar(color="#66c0f4")
        .encode(
            x=alt.X("n:Q", title="Reviews"),
            y=alt.Y("language:N", sort="-x", title=None),
            tooltip=["language:N", alt.Tooltip("n:Q", title="N")],
        )
        .properties(height=380),
        width="stretch",
    )

st.subheader("Volume over time")
if df["created_at"].notna().any():
    ts = df.dropna(subset=["created_at"]).copy()
    ts["month"] = ts["created_at"].dt.to_period("M").dt.to_timestamp()
    vol = ts.groupby(["month", "voted_up"], as_index=False).agg(n=("recommendation_id", "count"))
    vol["rating"] = vol["voted_up"].map({1: "Positive", 0: "Negative"})
    st.altair_chart(
        alt.Chart(vol)
        .mark_bar()
        .encode(
            x=alt.X("month:T", title=None),
            y=alt.Y("n:Q", title="Reviews"),
            color=alt.Color("rating:N", title=None,
                            scale=alt.Scale(domain=["Positive", "Negative"],
                                            range=["#93c47d", "#e06666"])),
            tooltip=["month:T", "rating:N", alt.Tooltip("n:Q", title="N")],
        )
        .properties(height=280),
        width="stretch",
    )

st.subheader("Review text")
q = st.text_input("Search text", key="rv_search", placeholder="keyword…")
view = df.copy()
if q:
    view = view[view["review_text"].fillna("").str.contains(q, case=False)]
view = view.sort_values("created_at", ascending=False, na_position="last")
view["rating"] = view["voted_up"].map({1: "👍", 0: "👎"})
view["hours"] = (view["playtime_at_review_min"].fillna(0) / 60).round(1)
st.caption(f"{len(view)} reviews")
st.dataframe(
    view[["created_at", "game", "rating", "language", "hours", "votes_up", "review_text"]]
    .rename(columns={"review_text": "text"}),
    width="stretch",
    hide_index=True,
    column_config={
        "created_at": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
        "hours": st.column_config.NumberColumn("Hours", format="%.1f"),
        "text": st.column_config.TextColumn("Text", width="large"),
    },
)
data.download(view, "reviews.csv")
data.sidebar_refresh()
