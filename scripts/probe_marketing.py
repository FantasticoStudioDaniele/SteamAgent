"""Dev tool: ispeziona la sezione Marketing (Visits/Impressions Over Time) di
navtrafficstats per capire come sono incapsulati i dati delle due serie storiche.

Uso: uv run python scripts/probe_marketing.py [appid]
Salva script inline e risposte di rete in scratchpad per analisi.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from steam_agent.settings import DATA_DIR, settings

APPID = sys.argv[1] if len(sys.argv) > 1 else "858680"
URL = f"https://partner.steamgames.com/apps/navtrafficstats/{APPID}"
OUT = DATA_DIR / "_probe"
OUT.mkdir(parents=True, exist_ok=True)
KEYS = ("over time", "jqplot", "visits", "impression", "g_rg", ".plot(",
        "series", "rgrows", "rgdata", "navtraffic")


async def main() -> None:
    captured: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()

        async def on_response(resp):
            u = resp.url
            if "partner.steamgames.com" not in u:
                return
            ct = resp.headers.get("content-type", "")
            if any(s in u.lower() for s in ("navtraffic", "ajax", "traffic", "marketing")) or \
               "json" in ct:
                try:
                    body = await resp.text()
                except Exception:
                    body = "<no body>"
                captured.append({"url": u, "status": resp.status, "ct": ct,
                                 "len": len(body), "body": body[:4000]})

        page.on("response", on_response)
        await page.goto(URL, wait_until="networkidle")
        print("FINAL URL:", page.url)
        print("TITLE:", await page.title())

        # Tutti gli script inline, con flag se contengono keyword interessanti
        scripts = await page.eval_on_selector_all(
            "script",
            "els => els.map(e => ({src: e.src || '', text: e.textContent || ''}))",
        )
        inline = [s for s in scripts if not s["src"] and s["text"].strip()]
        print(f"\nINLINE SCRIPTS: {len(inline)} (su {len(scripts)} totali)")

        hit_blocks = []
        for i, s in enumerate(inline):
            low = s["text"].lower()
            hits = [k for k in KEYS if k in low]
            if hits:
                hit_blocks.append((i, hits, s["text"]))
                print(f"  script #{i}: {len(s['text'])} char, match={hits}")

        # Salva i blocchi interessanti
        for i, hits, text in hit_blocks:
            (OUT / f"mk_script_{i}.js").write_text(text, encoding="utf-8")

        # Globali JS che sembrano dati delle serie
        keys = await page.evaluate(
            "() => Object.keys(window).filter(k => "
            "/traffic|visit|impression|g_rg|chart|plot|nav|stat|series/i.test(k))"
        )
        print("\nGLOBALS:", keys)
        glob_dump = {}
        for k in keys:
            preview = await page.evaluate(
                "(k) => { try { return JSON.stringify(window[k]); } "
                "catch(e){ return String(window[k]); } }",
                k,
            )
            glob_dump[k] = preview
            print(f"  {k}: {(preview or '')[:160]}")

        (OUT / "mk_globals.json").write_text(
            "\n".join(f"=== {k} ===\n{v}" for k, v in glob_dump.items()), encoding="utf-8"
        )

        print(f"\nNETWORK CAPTURED: {len(captured)}")
        for c in captured:
            print(f"  [{c['status']}] {c['ct']} len={c['len']}  {c['url'][:120]}")
        (OUT / "mk_network.txt").write_text(
            "\n\n".join(
                f"=== [{c['status']}] {c['url']}\nCT: {c['ct']} LEN: {c['len']}\n{c['body']}"
                for c in captured
            ),
            encoding="utf-8",
        )
        print("\nSaved to scratchpad: mk_script_*.js, mk_globals.json, mk_network.txt")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
