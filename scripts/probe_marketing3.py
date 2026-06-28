"""Ispeziona owners pie + countries bar (plotOwners/plotCountries) su navtrafficstats."""
from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

APPID = sys.argv[1] if len(sys.argv) > 1 else "858680"
URL = f"https://partner.steamgames.com/apps/navtrafficstats/{APPID}?preset_date_range=lifetime"


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")

        info = await page.evaluate(
            """() => {
                const out = {};
                const po = window.plotOwners;
                out.owners_data = po ? po.data : null;
                const pc = window.plotCountries;
                out.countries_data = pc ? pc.data : null;
                try { out.countries_ticks = pc ? pc.axes.yaxis.ticks.map(
                    t => (t && t.label !== undefined) ? t.label : t) : null; }
                catch(e){ out.countries_ticks = 'ERR:'+e; }
                // testo script con i literal originali (allineati, pre-reverse)
                const s = [...document.querySelectorAll('script')]
                    .map(e => e.textContent || '')
                    .find(t => t.includes('var dataCountries'));
                out.script_snippet = s ? s.slice(s.indexOf('var dataOwners'),
                    s.indexOf('var dataOwners') + 1200) : null;
                return out;
            }"""
        )
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
