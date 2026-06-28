"""Dump dei link (href grezzi) di una pagina partner usando la sessione salvata.

Uso: uv run python scripts/dump_links.py URL [filtro_substring]
"""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

URL = sys.argv[1]
FILT = sys.argv[2].lower() if len(sys.argv) > 2 else ""


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        print("TITLE:", await page.title())
        hrefs = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.getAttribute('href')).filter(Boolean)"
        )
        shown = [h for h in sorted(set(hrefs)) if not FILT or FILT in h.lower()]
        print(f"link (filtro='{FILT}'): {len(shown)}")
        for h in shown:
            print(" ", h)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
