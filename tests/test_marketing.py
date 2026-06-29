"""Unit tests for the marketing collector's pure parsing logic (no browser/DB)."""
from __future__ import annotations

from datetime import date

from steam_agent.collectors.marketing import parse_marketing


def test_parse_marketing_drops_stray_leading_point():
    """Steam's Total series starts with a stray point years before launch."""
    extract = {
        "visits": {
            "labels": ["Total"],
            "data": [[["2017-07-20", 2], ["2026-04-20", 3], ["2026-04-21", 6]]],
        },
        "impressions": None,
    }
    rows = parse_marketing(extract, app_id=4651840)
    days = sorted(r["date"] for r in rows)
    assert days[0] == date(2026, 4, 20)  # 2017 outlier dropped before storing
    assert all(d.year == 2026 for d in days)
    assert len(rows) == 2


def test_parse_marketing_keeps_continuous_series():
    """A daily-continuous series is stored intact, per source."""
    extract = {
        "visits": {
            "labels": ["Total", "Discovery Queue"],
            "data": [
                [["2026-04-20", 3], ["2026-04-21", 6]],
                [["2026-04-20", 1], ["2026-04-21", 2]],
            ],
        },
        "impressions": None,
    }
    rows = parse_marketing(extract, app_id=4651840)
    assert len(rows) == 4
    assert {r["source"] for r in rows} == {"Total", "Discovery Queue"}
    assert min(r["date"] for r in rows) == date(2026, 4, 20)
