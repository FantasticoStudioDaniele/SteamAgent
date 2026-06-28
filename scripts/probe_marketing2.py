"""Verifica formato dati live jqplot + range lifetime per navtrafficstats."""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

APPID = sys.argv[1] if len(sys.argv) > 1 else "858680"
PRESET = sys.argv[2] if len(sys.argv) > 2 else "lifetime"
URL = f"https://partner.steamgames.com/apps/navtrafficstats/{APPID}?preset_date_range={PRESET}"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        print("URL:", page.url)

        info = await page.evaluate(
            """() => {
                const out = {};
                for (const name of ['plotViews','plotImpressions']) {
                    const p = window[name];
                    if (!p) { out[name] = null; continue; }
                    out[name] = {
                        nseries: p.data.length,
                        labels: (p.series||[]).map(s => s.label),
                        npoints: p.data[0] ? p.data[0].length : 0,
                        first3: p.data[0] ? p.data[0].slice(0,3) : [],
                        last3: p.data[0] ? p.data[0].slice(-3) : [],
                        xtype: p.data[0] && p.data[0][0] ? typeof p.data[0][0][0] : 'n/a',
                    };
                }
                return out;
            }"""
        )
        import json
        print(json.dumps(info, indent=2, default=str))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
