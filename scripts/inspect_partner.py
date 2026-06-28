"""Dev tool: inspect a page of the partner portal with the saved session.

Usage:
    uv run python scripts/inspect_partner.py [URL]

Prints final URL, title, headings, links with appid and navigation links,
to identify the right page/structure from which to read the partner data.
Requires a valid storage_state (run `steam-agent login` first).
"""
from __future__ import annotations

import asyncio
import re
import sys

from playwright.async_api import async_playwright

from steam_agent.settings import settings

URL = sys.argv[1] if len(sys.argv) > 1 else "https://partner.steamgames.com/"
_APPID = re.compile(r"/(?:app|apps)/(?:details/|view/|landing/)?(\d+)")
_KW = re.compile(
    r"traffic|wishlist|sales|revenue|finance|marketing|utm|visit|impression|stats|"
    r"region|country|conversion|sell|report|download|\.csv",
    re.I,
)


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(settings.storage_state_path))
        page = await ctx.new_page()
        await page.goto(URL, wait_until="networkidle")
        print("REQUESTED:", URL)
        print("FINAL URL:", page.url)
        print("TITLE:", await page.title())

        headings = await page.eval_on_selector_all(
            "h1,h2,h3",
            "els => els.map(e => (e.textContent||'').trim()).filter(Boolean).slice(0,40)",
        )
        print("\nHEADINGS:")
        for h in headings:
            print("   -", h)

        links = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, text: (e.textContent||'').trim().slice(0,60)}))",
        )
        print("\nTOTAL LINKS:", len(links))

        apps: dict[str, str] = {}
        for link in links:
            m = _APPID.search(link["href"] or "")
            if m:
                apps.setdefault(m.group(1), link["text"])
        print("\nAPP-ID LINKS (appid -> text):")
        for a, t in apps.items():
            print("   ", a, "->", repr(t))

        print("\nNAV-ish LINKS:")
        seen: set[tuple[str, str]] = set()
        for link in links:
            t = link["text"] or ""
            href = link["href"] or ""
            if t and _KW.search(t) and (t, href) not in seen:
                seen.add((t, href))
                print("   ", repr(t), "->", href)

        print("\nSIGN-IN / LOGIN elements (a/button/form):")
        signin = await page.eval_on_selector_all(
            "a[href], button, form",
            """els => els
                .map(e => ({tag: e.tagName,
                            text: (e.textContent||'').trim().slice(0,40),
                            href: e.getAttribute('href')||'',
                            action: e.getAttribute('action')||'',
                            onclick: (e.getAttribute('onclick')||'').slice(0,120)}))
                .filter(o => /sign\\s*in|login|openid|accedi/i.test(
                    o.text + ' ' + o.href + ' ' + o.action + ' ' + o.onclick))""",
        )
        for s in signin:
            print("   ", s)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
