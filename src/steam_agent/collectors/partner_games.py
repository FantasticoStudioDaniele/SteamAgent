"""Collector for the games list from the partner portal (requires an authenticated session).

Reads the authoritative "All Applications" page (`/apps/`) and extracts appid + name
from the `/apps/landing/<appid>` links. Automatically excludes noise (blog/news on
store.steampowered.com, language switch, etc.).
"""
from __future__ import annotations

import html
import logging

from steam_agent.auth.session import authenticated_page
from steam_agent.scraping import selectors as S

log = logging.getLogger(__name__)

APPS_URL = S.URL_PARTNER_APPS
_LANDING_RE = S.RE_APP_LANDING_ID


async def fetch_games() -> list[dict]:
    games: dict[int, str] = {}
    async with authenticated_page() as page:
        await page.goto(APPS_URL, wait_until="networkidle")
        links = await page.eval_on_selector_all(
            S.SEL_APP_LANDING_LINK,
            "els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))",
        )
        for link in links:
            m = _LANDING_RE.search(link["href"] or "")
            if not m:
                continue
            appid = int(m.group(1))
            name = html.unescape(link["text"] or "").strip()
            # Keep the more informative name if the appid appears more than once.
            if appid not in games or (name and not games[appid]):
                games[appid] = name
        log.info("Found %d applications from the partner portal.", len(games))
    return [
        {"appid": appid, "name": name}
        for appid, name in sorted(games.items(), key=lambda kv: kv[1].lower())
    ]
