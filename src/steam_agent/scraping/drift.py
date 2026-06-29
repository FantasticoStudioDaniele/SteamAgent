"""Schema-drift detection: tell "Steam changed the page layout" apart from
"this game/account legitimately has no data".

Every predicate keys on a MISSING STRUCTURAL ANCHOR (a header line, a chart
global, a table, the logged-in JS global) — never on a zero result count — so an
empty-but-intact page (a new account, a game with no wishlist/playtime, a quiet
sales month) is NOT mistaken for drift. The predicates are pure and Playwright-free
so they can be unit-tested offline.
"""
from __future__ import annotations

from collections.abc import Sequence


class SchemaDriftError(RuntimeError):
    """A portal page rendered, but its expected structure is gone (likely a
    Steam layout change). Distinct from a transient/auth failure and from an
    empty-but-valid result."""

    def __init__(self, source: str, detail: str, url: str | None = None) -> None:
        self.source = source
        self.detail = detail
        self.url = url
        msg = f"[{source}] schema drift: {detail}"
        super().__init__(f"{msg} ({url})" if url else msg)


def csv_header_drift(
    status: int,
    body: str,
    header_tokens: Sequence[str],
    *,
    scan_bytes: int = 600,
    min_columns: int | None = None,
    html_sentinel: str = "<html",
) -> bool:
    """True when a 200 response has a non-empty, non-HTML body whose expected CSV
    header is gone (Steam changed the report). False when the header is present but
    there are simply no data rows (a legitimately empty report), and False for
    non-200 / empty / HTML bodies (those are transient/auth failures, not drift)."""
    if status != 200:
        return False
    text = body.lstrip("﻿").strip()
    if not text:
        return False
    head = text[:scan_bytes].lower()
    if html_sentinel.lower() in head[:200]:
        return False  # an HTML error/login page -> transient, let it retry
    if not any(token.lower() in head for token in header_tokens):
        return True
    if min_columns is not None:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if len(first_line.split(",")) < min_columns:
            return True
    return False


def marketing_charts_missing(payload: dict | None) -> bool:
    """True when neither the visits nor the impressions jqplot object was readable
    (the marketing charts did not render at all). A game with no traffic still
    renders the charts with an empty `.data`, so it does not trip this."""
    p = payload or {}
    return p.get("visits") is None and p.get("impressions") is None


def playtime_layout_drift(
    nav_ok: bool, tables: list, final_url: str, expected_url_fragment: str
) -> bool:
    """True when navigation succeeded but the playtime page has zero <table>
    elements while still on the playtime URL. A game with no playtime keeps its
    table shell, so it does not trip this; an SSO/login bounce (URL changed) is
    excluded so a session expiry is not misread as a layout change."""
    return bool(nav_ok) and len(tables) == 0 and expected_url_fragment in (final_url or "")


def session_anchor_ok(global_defined: bool, header_box_count: int) -> bool:
    """Whether the authenticated shell is present after a login that reached its
    success URL. Keyed on the JS global being DEFINED (not non-empty), so an
    affiliate with zero apps still passes; drift is `not session_anchor_ok(...)`."""
    return bool(global_defined) or header_box_count > 0
