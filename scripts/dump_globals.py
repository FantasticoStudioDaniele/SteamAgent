"""Dump of JS global variables (filtered) + number of tables of a partner page.

Usage: uv run python scripts/dump_globals.py URL [pattern_regex]
"""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

URL = sys.argv[1]
PAT = sys.argv[2] if len(sys.argv) > 2 else "player|dau|concurrent|g_rg|chart|stat|active|owner|unique"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        print("TITLE:", await page.title())

        keys = await page.evaluate(
            "(pat) => Object.keys(window).filter(k => new RegExp(pat, 'i').test(k))", PAT
        )
        print("GLOBALS:", keys)
        for k in keys:
            preview = await page.evaluate(
                "(k) => { try { const v = window[k]; const s = JSON.stringify(v); "
                "return s ? s.slice(0, 220) : String(v); } catch (e) { return 'ERR' } }",
                k,
            )
            print(f"  {k}: {preview}")

        tcount = await page.eval_on_selector_all("table", "els => els.length")
        print("tables:", tcount)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
