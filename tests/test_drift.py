"""Unit tests for the pure schema-drift predicates.

The whole point of these is the drift-vs-empty distinction: a layout change must
fire, but a legitimately empty (yet structurally intact) page must NOT.
"""
from __future__ import annotations

from steam_agent.scraping.drift import (
    SchemaDriftError,
    csv_header_drift,
    marketing_charts_missing,
    page_outcome,
    session_anchor_ok,
)

PLAYERS = ("DateReported",)
PLAYERS_BODY_OK = "Daily Active Users\nDateReported,DAU,Peak\n2026-01-01,10,2\n"
PLAYERS_BODY_EMPTY = "Daily Active Users\nDateReported,DAU,Peak\n"  # header, no rows


def test_csv_header_present_is_not_drift_even_with_zero_rows():
    assert csv_header_drift(200, PLAYERS_BODY_OK, PLAYERS) is False
    assert csv_header_drift(200, PLAYERS_BODY_EMPTY, PLAYERS) is False  # empty != drift


def test_csv_header_missing_on_200_is_drift():
    assert csv_header_drift(200, "Some,Other,Report\n1,2,3\n", PLAYERS) is True


def test_csv_non_200_and_empty_and_html_are_not_drift():
    assert csv_header_drift(500, PLAYERS_BODY_OK, PLAYERS) is False   # transient/auth
    assert csv_header_drift(200, "", PLAYERS) is False                # empty body
    assert csv_header_drift(200, "<html><body>login</body></html>", PLAYERS) is False


def test_csv_bom_prefixed_header_still_matches():
    assert csv_header_drift(200, "﻿DateReported,DAU,Peak\n2026-01-01,1,1\n", PLAYERS) is False


def test_csv_min_columns_catches_shrunken_traffic_header():
    tokens = ("Impressions", "Visits")
    full = "Page/Category,Page/Feature,Impressions,Visits,Owner Impressions,Owner Visits\nx,y,1,2,3,4\n"
    shrunk = "Impressions,Visits\n1,2\n"
    assert csv_header_drift(200, full, tokens, min_columns=6) is False
    assert csv_header_drift(200, shrunk, tokens, min_columns=6) is True  # tokens ok but too few cols


def test_marketing_charts_missing_only_when_both_absent():
    assert marketing_charts_missing({"visits": None, "impressions": None}) is True
    assert marketing_charts_missing({}) is True
    assert marketing_charts_missing(None) is True
    # a game with no traffic still renders the charts with empty data -> not drift
    assert marketing_charts_missing({"visits": {"labels": [], "data": []}, "impressions": None}) is False


def test_page_outcome_classifies_empty_transient_and_drift():
    # Real cases captured from a live run.
    markers = ("authentication failed", "failed to load app info")
    valid_marketing = "<title>Store Traffic Stats: Dumpling Squishy Demo</title>"
    valid_playtime = "<title>Lifetime play time stats: Dumpling Squishy Demo</title>"
    auth_error = "<body>Failed to load app info section 'common'! Account authentication failed</body>"

    # structure present -> ok regardless of the text
    assert page_outcome("", structure_present=True, page_marker="x", transient_markers=markers) == "ok"
    # a demo / zero-data app renders a valid page with no charts/tables -> empty
    assert page_outcome(valid_marketing, structure_present=False,
                        page_marker="Store Traffic Stats", transient_markers=markers) == "empty"
    assert page_outcome(valid_playtime, structure_present=False,
                        page_marker="play time stats", transient_markers=markers) == "empty"
    # an auth/load error page -> transient (retryable, not a layout change)
    assert page_outcome(auth_error, structure_present=False,
                        page_marker="Store Traffic Stats", transient_markers=markers) == "transient"
    # bounced off the expected page (SSO/login) -> transient
    assert page_outcome("login", structure_present=False, page_marker="Store Traffic Stats",
                        transient_markers=markers, on_expected_page=False) == "transient"
    # the page rendered but is neither the expected page nor a known error -> real drift
    assert page_outcome("<html>something else entirely</html>", structure_present=False,
                        page_marker="Store Traffic Stats", transient_markers=markers) == "drift"


def test_session_anchor_ok_keys_on_defined_not_nonempty():
    assert session_anchor_ok(True, 0) is True       # global defined (even if {} )
    assert session_anchor_ok(False, 1) is True       # header box present
    assert session_anchor_ok(False, 0) is False      # neither -> drift


def test_schema_drift_error_message():
    err = SchemaDriftError("marketing", "charts gone", url="https://x")
    assert err.source == "marketing" and err.url == "https://x"
    assert "marketing" in str(err) and "charts gone" in str(err)
