"""Dump tabelle (headers + prime righe) + link download di una pagina partner.

Uso: uv run python scripts/dump_tables.py URL
"""
from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

URL = sys.argv[1]


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        print("TITLE:", await page.title())

        dl = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href')).filter(h => h && /csv|download|excel|xls/i.test(h))",
        )
        print("download/csv links:", sorted(set(dl)))

        data = await page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('table').forEach((t, ti) => {
                    const rows = [...t.querySelectorAll('tr')].slice(0, 6).map(
                        r => [...r.querySelectorAll('th,td')].map(c => (c.innerText||'').trim().slice(0,24))
                    );
                    if (rows.length) out.push({ti, rows});
                });
                return out.slice(0, 8);
            }"""
        )
        print("tabelle:", len(data))
        for tb in data:
            print(f"=== table {tb['ti']} ===")
            for r in tb["rows"]:
                print("  ", r)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
