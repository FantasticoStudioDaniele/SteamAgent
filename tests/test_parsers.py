"""Offline unit tests for the collectors' PURE parsing logic.

These functions turn a raw Steam payload (CSV text, the playtime HTML tables, an
API review dict, or the marketing jqplot extract) into DB-ready rows. They hold
the brittle logic that silently breaks when Steam changes a format, so they are
exactly what needs regression coverage — and they need no browser, no login and
no database.
"""
from __future__ import annotations

from datetime import date

from steam_agent.collectors.marketing import parse_countries, parse_marketing, parse_owners
from steam_agent.collectors.players import parse_players_csv
from steam_agent.collectors.playtime import _to_minutes, parse_playtime
from steam_agent.collectors.reviews import _parse_review
from steam_agent.collectors.sales import _to_float, parse_sales_csv
from steam_agent.collectors.traffic import parse_traffic_csv
from steam_agent.collectors.wishlist import parse_wishlist_csv

# --------------------------------------------------------------------- CSV fixtures
# A leading BOM (﻿) like the real traffic export; the header is skipped
# positionally, the ",,,,," and short rows are dropped.
TRAFFIC_CSV = (
    "﻿Page/Category,Page/Feature,Impressions,Visits,Owner Impressions,Owner Visits\n"
    "Steam,Store Home,1000,120,50,8\n"
    "External,Other Websites,500,40,10,2\n"
    ",,,,,\n"
    "Steam\n"
)

# Old-portal report_csv.php exports have a preamble before the matched header.
PLAYERS_CSV = (
    "Daily Active Users\n"
    "Generated 2026-01-04\n"
    "DateReported,DailyActiveUsers,PeakConcurrentUsers\n"
    "2026-01-01,1000,150\n"
    "2026-01-02,1100,160\n"
    "2026-01-03,-5,0\n"
    "not-a-date,5,5\n"
    "short,row\n"
)

WISHLIST_CSV = (
    "Wishlist Actions\n"
    "DateLocal,Game,Adds,Deletes,PurchasesAndActivations,Gifts\n"
    "2026-01-01,My Game,80,12,5,1\n"
    "2026-01-02,My Game,90,15,6,0\n"
    "short,row\n"
)

SALES_CSV = (
    "Sales by Country\n"
    "Country,Sku,Platform,Net Units Sold,Net Steam Sales (USD)\n"
    "United States,My Game (12345),Windows,100,1999.50\n"
    "Germany,My Game Soundtrack (67890),Windows,10,49.90\n"
    "France,Bundle Pack,Linux,3,30.0\n"
    "Total,,,,\n"
)


# ------------------------------------------------------------------- traffic
def test_parse_traffic_csv():
    rows = parse_traffic_csv(TRAFFIC_CSV, app_id=440, day=date(2026, 1, 1))
    assert len(rows) == 2  # the empty and the short row are dropped
    first = rows[0]
    assert first["category"] == "Steam"  # BOM stripped, header skipped
    assert first["feature"] == "Store Home"
    assert (first["impressions"], first["visits"]) == (1000, 120)
    assert (first["owner_impressions"], first["owner_visits"]) == (50, 8)
    assert rows[0]["date"] == date(2026, 1, 1) and rows[0]["app_id"] == 440


# ------------------------------------------------------------------- players
def test_parse_players_csv_skips_preamble_and_bad_rows():
    rows = parse_players_csv(PLAYERS_CSV, app_id=440)
    assert len(rows) == 3  # preamble, non-date and short rows dropped
    assert [r["date"] for r in rows] == [date(2026, 1, d) for d in (1, 2, 3)]
    assert rows[0]["daily_active_users"] == 1000
    assert rows[0]["peak_concurrent_users"] == 150
    assert rows[2]["daily_active_users"] == -5  # negative coerced, not zeroed


# ------------------------------------------------------------------ wishlist
def test_parse_wishlist_csv():
    rows = parse_wishlist_csv(WISHLIST_CSV, app_id=440)
    assert len(rows) == 2
    assert (rows[0]["adds"], rows[0]["deletes"]) == (80, 12)
    assert (rows[0]["purchases_activations"], rows[0]["gifts"]) == (5, 1)
    assert rows[1]["date"] == date(2026, 1, 2)


# --------------------------------------------------------------------- sales
def test_parse_sales_csv_sku_split_and_total_skip():
    rows = parse_sales_csv(SALES_CSV, month=date(2026, 1, 1))
    assert len(rows) == 3  # the "Total" row is skipped
    by_name = {r["product_name"]: r for r in rows}
    # "Name (packageId)" split
    assert by_name["My Game"]["package_id"] == 12345
    assert by_name["My Game"]["net_units"] == 100
    assert by_name["My Game"]["net_sales_usd"] == 1999.50
    assert by_name["My Game Soundtrack"]["package_id"] == 67890
    # SKU without "(id)" -> no package, name kept verbatim
    assert by_name["Bundle Pack"]["package_id"] is None
    assert by_name["Bundle Pack"]["platform"] == "Linux"


def test_sales_to_float_handles_garbage():
    assert _to_float("1999.50") == 1999.50
    assert _to_float("") == 0.0
    assert _to_float("n/a") == 0.0


# ------------------------------------------------------------------ playtime
def test_parse_playtime_tables():
    tables = [
        [["Lifetime Users", "12,345"],
         ["Average Time", "3 hours 20 minutes"],
         ["Median Time", "45 minutes"]],
        [["Time Played", "Percent of Users"],
         ["10 minutes", "73%"],
         ["1 hour", "34%"],
         ["10 hours", "5%"]],
    ]
    snap = parse_playtime(tables, app_id=440, snapshot_date=date(2026, 1, 1))
    assert snap is not None
    assert snap["lifetime_users"] == 12345
    assert snap["avg_minutes"] == 200  # 3h20m
    assert snap["median_minutes"] == 45
    assert snap["distribution"] == {"10": 73, "60": 34, "600": 5}


def test_parse_playtime_returns_none_without_users():
    tables = [[["Average Time", "1 hour"]]]  # no "Lifetime Users" anchor
    assert parse_playtime(tables, app_id=440, snapshot_date=date(2026, 1, 1)) is None


def test_to_minutes():
    assert _to_minutes("3 hours 20 minutes") == 200
    assert _to_minutes("45 minutes") == 45
    assert _to_minutes("2 hours") == 120
    assert _to_minutes("n/a") is None


# ------------------------------------------------------------------- reviews
def test_parse_review_full_and_sparse():
    full = _parse_review(
        {
            "recommendationid": 987654,
            "author": {"playtime_at_review": 320},
            "language": "english",
            "voted_up": True,
            "votes_up": 12,
            "votes_funny": 3,
            "timestamp_created": 1700000000,
            "review": "Great game",
        },
        app_id=440,
    )
    assert full["recommendation_id"] == "987654"  # coerced to str (PK)
    assert full["voted_up"] is True
    assert full["votes_up"] == 12 and full["votes_funny"] == 3
    assert full["playtime_at_review_min"] == 320
    assert full["review_text"] == "Great game"
    assert full["created_at"].year == 2023 and full["created_at"].tzinfo is not None

    sparse = _parse_review({"recommendationid": 1}, app_id=440)
    assert sparse["recommendation_id"] == "1"
    assert sparse["voted_up"] is False
    assert sparse["votes_up"] == 0 and sparse["votes_funny"] == 0
    assert sparse["playtime_at_review_min"] is None
    assert sparse["created_at"] is None
    assert sparse["language"] is None


# ----------------------------------------------------------------- marketing
def test_parse_owners_and_derivation():
    extract = {"owners": [["Owners: 40%", 40.0], ["Non-Owners: 60%", 60.0]]}
    o = parse_owners(extract, app_id=440, snapshot_date=date(2026, 1, 1))
    assert (o["owners_pct"], o["non_owners_pct"]) == (40.0, 60.0)

    # only the non-owner slice present -> owners derived as 100 - non
    derived = parse_owners({"owners": [["Non-Owners: 70%", 70.0]]}, 440, date(2026, 1, 1))
    assert derived["owners_pct"] == 30.0
    assert parse_owners({}, 440, date(2026, 1, 1)) is None


def test_parse_countries_handles_comma_in_name():
    extract = {"countries": {"counts": [9000, 4000],
                             "ticks": ["United States, 60%", "Korea, South, 20%"]}}
    rows = parse_countries(extract, app_id=440, snapshot_date=date(2026, 1, 1))
    assert len(rows) == 2
    assert rows[0]["country"] == "United States" and rows[0]["pct"] == 60.0
    assert rows[0]["visits"] == 9000
    # split on the LAST ", " so the country name keeps its internal comma
    assert rows[1]["country"] == "Korea, South" and rows[1]["pct"] == 20.0


def test_parse_marketing_coerces_null_values():
    extract = {
        "visits": {"labels": ["Total"], "data": [[["2026-04-20", 5], ["2026-04-21", None]]]},
        "impressions": {"labels": ["Total"], "data": [[["2026-04-20", 100]]]},
    }
    rows = parse_marketing(extract, app_id=440)
    assert {r["metric"] for r in rows} == {"visits", "impressions"}
    null_pt = next(r for r in rows if r["metric"] == "visits" and r["date"] == date(2026, 4, 21))
    assert null_pt["value"] == 0  # None coerced to 0
