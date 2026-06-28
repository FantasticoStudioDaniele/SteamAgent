"""Collector della lista giochi dal portale partner (richiede sessione autenticata).

Legge la pagina autorevole "All Applications" (`/apps/`) ed estrae appid + nome
dai link `/apps/landing/<appid>`. Esclude automaticamente il rumore (blog/news su
store.steampowered.com, switch lingua, ecc.).
"""
from __future__ import annotations

import html
import logging
import re

from steam_agent.auth.session import authenticated_page

log = logging.getLogger(__name__)

APPS_URL = "https://partner.steamgames.com/apps/"
_LANDING_RE = re.compile(r"/apps/landing/(\d+)")


async def fetch_games() -> list[dict]:
    games: dict[int, str] = {}
    async with authenticated_page() as page:
        await page.goto(APPS_URL, wait_until="networkidle")
        links = await page.eval_on_selector_all(
            "a[href*='/apps/landing/']",
            "els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))",
        )
        for link in links:
            m = _LANDING_RE.search(link["href"] or "")
            if not m:
                continue
            appid = int(m.group(1))
            name = html.unescape(link["text"] or "").strip()
            # Mantieni il nome piu' informativo se l'appid compare piu' volte.
            if appid not in games or (name and not games[appid]):
                games[appid] = name
        log.info("Trovate %d applicazioni dal portale partner.", len(games))
    return [
        {"appid": appid, "name": name}
        for appid, name in sorted(games.items(), key=lambda kv: kv[1].lower())
    ]
