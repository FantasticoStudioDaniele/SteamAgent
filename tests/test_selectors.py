"""Lock the selector registry: every scraper sources its fragile literals from
`scraping.selectors`, and the partner-games CSS/regex stay in sync.

This is the safety net for the registry refactor — if someone edits a selector
back into a collector, or the landing-link CSS and regex drift apart, it fails here.
"""
from __future__ import annotations

from steam_agent.auth import session
from steam_agent.collectors import (
    marketing,
    partner_games,
    players,
    playtime,
    sales,
    traffic,
    wishlist,
)
from steam_agent.scraping import selectors as S


def test_collectors_source_selectors_from_registry():
    assert session._SIGNIN_BTN is S.SEL_SIGNIN_BTN
    assert session._USERNAME is S.SEL_USERNAME
    assert session._SEGMENT is S.SEL_TOTP_SEGMENT
    assert marketing._URL is S.URL_MARKETING_TMPL
    assert marketing._EXTRACT_JS is S.JS_MARKETING_EXTRACT
    assert playtime._TABLES_JS is S.JS_PLAYTIME_TABLES
    assert traffic._TRAFFIC_URL is S.URL_TRAFFIC
    assert players.OLD is wishlist.OLD is sales.OLD is S.URL_OLD_BASE
    assert partner_games.APPS_URL is S.URL_PARTNER_APPS
    assert partner_games._LANDING_RE is S.RE_APP_LANDING_ID


def test_portal_urls_point_at_the_right_host():
    for url in (S.URL_NEW_HOME, S.URL_NEW_DASHBOARD, S.URL_TRAFFIC,
                S.URL_MARKETING_TMPL, S.URL_PARTNER_APPS):
        assert url.startswith(S.URL_NEW_BASE)
    assert S.URL_OLD_CHECK.startswith(S.URL_OLD_BASE)


def test_marketing_extract_js_reads_the_expected_globals():
    for g in ("plotViews", "plotImpressions", "plotOwners", "plotCountries"):
        assert g in S.JS_MARKETING_EXTRACT


def test_landing_link_css_and_regex_share_one_fragment():
    # Both are derived from APP_LANDING_PATH_FRAGMENT, so a path rename is one edit.
    assert S.APP_LANDING_PATH_FRAGMENT in S.SEL_APP_LANDING_LINK
    m = S.RE_APP_LANDING_ID.search("https://partner.steamgames.com/apps/landing/440")
    assert m and m.group(1) == "440"
    assert S.RE_APP_LANDING_ID.search("/apps/other/440") is None
