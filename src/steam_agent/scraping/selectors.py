"""Centralized registry of every hard-coded Steam selector, URL and extraction
snippet used by the scrapers.

Steam restyles its partner portals without notice, so these literals are the most
fragile part of the project. Keeping them in one place — grouped by portal and
page — turns a breakage into a one-line fix and is the precondition for the
schema-drift detection that builds on top of them.

  NEW portal = partner.steamgames.com   (login shell, app list, traffic, marketing)
  OLD portal = partner.steampowered.com (sales, wishlist, players, playtime)
"""
from __future__ import annotations

import re

# --- Portal origins ---------------------------------------------------------
URL_NEW_BASE = "https://partner.steamgames.com"
URL_OLD_BASE = "https://partner.steampowered.com"

# --- NEW portal: login + authenticated shell (auth/session.py) --------------
URL_NEW_HOME = "https://partner.steamgames.com/"
URL_NEW_DASHBOARD = "https://partner.steamgames.com/dashboard"
SEL_SIGNIN_BTN = 'button[onclick*="g_ShowLoginDialog"]'
SEL_PASSWORD = "input[type='password']"
# The username field has no stable id/name — located positionally as the text
# input immediately before the password field. The single most fragile selector.
SEL_USERNAME = "xpath=//input[@type='password']/preceding::input[@type='text'][1]"
# The 5 segmented TOTP boxes; excludes the search box in the logged-in header.
SEL_TOTP_SEGMENT = "input[type='text']:not(#appHeaderFindInput)"
TXT_ENTER_CODE_INSTEAD = "Enter a code instead"
TXT_EMAIL_CONFIRM_AT = "email address at"
TXT_EMAIL_CONFIRM_FROM = "from your email"
# JS global injected on every authenticated portal page: {partner_id: name}.
JS_AFFILIATED_PUBLISHERS = "() => window.g_rgAllAffiliatedPublishers || {}"

# --- OLD portal: auth probe (auth/session.py) -------------------------------
URL_OLD_CHECK = "https://partner.steampowered.com/dir.php"

# --- NEW portal: marketing + traffic ----------------------------------------
URL_MARKETING_TMPL = (
    "https://partner.steamgames.com/apps/navtrafficstats/{appid}?preset_date_range={preset}"
)
URL_TRAFFIC = "https://partner.steamgames.com/apps/navtrafficstats/{appid}"
# Reads the live jqplot objects (this data is NOT in the CSV export).
JS_MARKETING_EXTRACT = """() => {
    const read = (name) => {
        const p = window[name];
        if (!p || !p.data) return null;
        return { labels: (p.series || []).map(s => s.label), data: p.data };
    };
    let owners = null;
    if (window.plotOwners && window.plotOwners.data && window.plotOwners.data[0])
        owners = window.plotOwners.data[0];
    let countries = null;
    if (window.plotCountries && window.plotCountries.data && window.plotCountries.data[0]) {
        let ticks = [];
        try {
            ticks = window.plotCountries.axes.yaxis.ticks.map(
                t => (t && t.label !== undefined) ? t.label : t);
        } catch (e) { ticks = []; }
        countries = { counts: window.plotCountries.data[0], ticks: ticks };
    }
    return {
        visits: read('plotViews'),
        impressions: read('plotImpressions'),
        owners: owners,
        countries: countries,
    };
}"""

# --- OLD portal: playtime (HTML tables, no CSV) -----------------------------
JS_PLAYTIME_TABLES = """() => [...document.querySelectorAll('table')].map(t =>
    [...t.querySelectorAll('tr')].map(r =>
        [...r.querySelectorAll('th,td')].map(c => (c.innerText || '').trim())))"""

# --- Schema-drift anchors (consumed by scraping.drift) ----------------------
# The ABSENCE of these structural markers in a *successful* (200) response is what
# signals Steam changed a layout — NOT a zero result count, which is a legitimately
# empty (but intact) report. See scraping/drift.py.
CSV_HEADER_SCAN_BYTES = 600
HTML_SENTINEL = "<html"
PLAYERS_CSV_HEADER_TOKEN = "DateReported"
WISHLIST_CSV_HEADER_TOKEN = "DateLocal"
SALES_CSV_HEADER_TOKEN = "Country,Sku"      # the report header line (drift gate)
SALES_CSV_HEADER_FIRST_CELL = "Country"     # first column where the parser starts
TRAFFIC_HEADER_TOKENS = ("Impressions", "Visits")
TRAFFIC_MIN_COLUMNS = 6
# Page-nav anchors. Real-account runs showed that demos / zero-data apps render a
# VALID page with NO charts (marketing) or NO tables (playtime), so "structure
# absent" alone is NOT drift. We classify against a page marker (proves the page
# rendered) and transient-error markers (a retryable auth/load glitch, not a
# layout change). Only "structure absent AND not the known page AND not an error"
# is real drift. See scraping.drift.page_outcome.
URL_FRAG_PLAYTIME = "/app/playtime/"
URL_FRAG_MARKETING = "navtrafficstats"
MARKETING_PAGE_MARKER = "Store Traffic Stats"      # the marketing page <title>/heading
PLAYTIME_PAGE_MARKER = "play time stats"           # "Lifetime play time stats: <game>"
TRANSIENT_PAGE_MARKERS = ("authentication failed", "failed to load app info")
# Authenticated-shell anchors: this JS global is injected on every authed page of
# BOTH portals; the search box exists only in the logged-in NEW-portal header.
SEL_APP_HEADER_FIND_INPUT = "#appHeaderFindInput"
JS_AFFILIATED_PUBLISHERS_DEFINED = (
    '() => typeof window.g_rgAllAffiliatedPublishers !== "undefined"'
)

# --- NEW portal: partner app list (collectors/partner_games.py) -------------
URL_PARTNER_APPS = "https://partner.steamgames.com/apps/"
# One source of truth for the landing-link path, so the CSS selector and the
# appid regex below can never disagree on a rename.
APP_LANDING_PATH_FRAGMENT = "/apps/landing/"
SEL_APP_LANDING_LINK = f"a[href*='{APP_LANDING_PATH_FRAGMENT}']"
RE_APP_LANDING_ID = re.compile(rf"{re.escape(APP_LANDING_PATH_FRAGMENT)}(\d+)")
