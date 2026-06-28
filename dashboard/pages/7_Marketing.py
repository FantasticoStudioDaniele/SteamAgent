"""Marketing — Visits/Impressions Over Time per sorgente (serie storiche jqplot)."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data

st.set_page_config(page_title="Marketing · SteamAgent", page_icon="📣", layout="wide")
st.title("📣 Marketing — visite & impression nel tempo")
st.caption("Serie storiche per sorgente, dalla pagina *Store Traffic Stats* (per gioco).")

df = data.marketing()
if df.empty:
    data.empty_note("marketing")
    st.caption("Popola con: `uv run steam-agent collect-marketing`")
    data.sidebar_refresh()
    st.stop()

# --- selezione gioco (le sorgenti top sono per-gioco) ---
games = sorted(df["game"].dropna().unique().tolist())
game = st.sidebar.selectbox("Gioco", games, key="mk_game")
g = df[df["game"] == game].copy()

# --- periodo ---
lo, hi = g["date"].min().date(), g["date"].max().date()
sel = st.sidebar.date_input("Periodo", (lo, hi), min_value=lo, max_value=hi, key="mk_dates")
if isinstance(sel, (list, tuple)) and len(sel) == 2:
    a, b = pd.Timestamp(sel[0]), pd.Timestamp(sel[1]) + pd.Timedelta(days=1)
    g = g[(g["date"] >= a) & (g["date"] < b)]

# --- granularità (8 anni di dati giornalieri sono fitti) ---
gran = st.sidebar.radio("Granularità", ["Mese", "Settimana", "Giorno"], key="mk_gran")
freq = {"Giorno": "D", "Settimana": "W", "Mese": "MS"}[gran]
drop_bot = st.sidebar.checkbox("Escludi Bot Traffic dalle visite", value=False, key="mk_bot")

if g.empty:
    st.warning("Nessun dato con i filtri correnti.")
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
            color=alt.Color("source:N", title="Sorgente", sort=order),
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
        ("Visite (Total)", data.fmt_int(v_tot)),
        ("Impression (Total)", data.fmt_int(i_tot)),
        ("CTR (visite/impr.)", data.fmt_pct(ctr)),
        ("Sorgenti tracciate", data.fmt_int(g["source"].nunique())),
    ]
)
st.divider()

st.subheader("Visits Over Time")
if vis.empty:
    st.info("Nessun dato visite.")
else:
    st.altair_chart(line_chart(vis, "Visite"), width="stretch")

st.subheader("Impressions Over Time")
if imp.empty:
    st.info("Nessun dato impression.")
else:
    st.altair_chart(line_chart(imp, "Impression"), width="stretch")

st.divider()
co, cc = st.columns([1, 2])
with co:
    st.subheader("Ownership")
    odf = data.marketing_owners()
    orow = odf[odf["game"] == game] if not odf.empty else odf
    if orow.empty:
        st.info("Nessun dato ownership.")
    else:
        latest = orow.sort_values("snapshot_date").iloc[-1]
        st.metric("Visite da Owner", data.fmt_pct(latest["owners_pct"]))
        pie = pd.DataFrame(
            {"tipo": ["Owner", "Non-Owner"],
             "pct": [latest["owners_pct"], latest["non_owners_pct"]]}
        )
        st.altair_chart(
            alt.Chart(pie)
            .mark_arc(innerRadius=55)
            .encode(
                theta="pct:Q",
                color=alt.Color("tipo:N", title=None,
                                scale=alt.Scale(domain=["Owner", "Non-Owner"],
                                                range=["#66c0f4", "#3a3f44"])),
                tooltip=["tipo:N", alt.Tooltip("pct:Q", format=".2f")],
            )
            .properties(height=240),
            width="stretch",
        )
        st.caption(f"Snapshot {latest['snapshot_date'].date()}")
with cc:
    st.subheader("Top paesi per visite")
    cdf = data.marketing_country()
    crow = cdf[cdf["game"] == game] if not cdf.empty else cdf
    if crow.empty:
        st.info("Nessun dato paesi.")
    else:
        crow = crow[crow["snapshot_date"] == crow["snapshot_date"].max()]
        if st.checkbox("Escludi 'Unknown'", value=False, key="mk_unknown"):
            crow = crow[crow["country"].str.lower() != "unknown"]
        crow = crow.sort_values("visits", ascending=False)
        st.altair_chart(
            alt.Chart(crow)
            .mark_bar(color="#66c0f4")
            .encode(
                x=alt.X("visits:Q", title="Visite"),
                y=alt.Y("country:N", sort="-x", title=None),
                tooltip=["country:N", alt.Tooltip("visits:Q", format=",.0f"),
                         alt.Tooltip("pct:Q", title="quota %", format=".0f")],
            )
            .properties(height=300),
            width="stretch",
        )

with st.expander("Dettaglio / export"):
    show = g[["date", "metric", "source", "value"]].sort_values(
        ["metric", "date", "value"], ascending=[True, False, False]
    )
    st.dataframe(show, width="stretch", hide_index=True)
    data.download(show, f"marketing_{game}.csv")

data.sidebar_refresh()
