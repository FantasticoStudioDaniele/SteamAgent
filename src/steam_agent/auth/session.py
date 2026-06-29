"""Authenticated session toward the TWO Steam partner portals.

- NEW portal: partner.steamgames.com (traffic, UTM, achievements...). Login
  via React modal opened by `g_ShowLoginDialog`.
- OLD portal: partner.steampowered.com (wishlist, sales, regions,
  financials...). Login with the direct Steam form. SEPARATE session.

Both use the same Steam login (username/password + authenticator). Steam
shows the mobile-app confirmation by default: we click "Enter a code instead"
and type the TOTP into the 5 segmented boxes. The storage_state keeps the
cookies of BOTH portals. Possible one-time EMAIL confirmation (new device):
in --headed the user completes it.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from steam_agent.auth.steam_guard import generate_twofactor_code
from steam_agent.scraping import selectors as S
from steam_agent.secure import secure_file
from steam_agent.settings import settings

log = logging.getLogger(__name__)

NEW_HOME = S.URL_NEW_HOME
NEW_DASHBOARD = S.URL_NEW_DASHBOARD
OLD_BASE = S.URL_OLD_BASE
OLD_CHECK = S.URL_OLD_CHECK

_SIGNIN_BTN = S.SEL_SIGNIN_BTN
_PASSWORD = S.SEL_PASSWORD
_USERNAME = S.SEL_USERNAME
_SEGMENT = S.SEL_TOTP_SEGMENT


class SteamLoginError(RuntimeError):
    pass


async def _new_context(browser) -> BrowserContext:
    if settings.storage_state_path.exists():
        return await browser.new_context(storage_state=str(settings.storage_state_path))
    return await browser.new_context()


async def _twofactor_code(headless: bool) -> str | None:
    """2FA code: TOTP if the shared_secret is present, otherwise prompts on screen.

    Without a shared_secret in headless mode it is not possible to proceed
    (unattended login): an error with instructions is raised.
    """
    secret = settings.steam_shared_secret.strip()
    if secret:
        return generate_twofactor_code(secret)
    if headless:
        raise SteamLoginError(
            "No STEAM_SHARED_SECRET and headless mode: cannot enter the 2FA.\n"
            "Run `steam-agent login --headed` (enter the code manually) or "
            "configure STEAM_SHARED_SECRET for automatic login."
        )
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(
        None, lambda: input("Steam Guard code (from the mobile app or email): ").strip()
    )
    return code or None


async def _enter_2fa(page: Page, headless: bool) -> None:
    """Handles the 2FA step: switches to code entry and types the code."""
    try:
        await page.locator(_PASSWORD).wait_for(state="hidden", timeout=30_000)
    except PlaywrightTimeoutError:
        pass

    link = page.get_by_text(S.TXT_ENTER_CODE_INSTEAD, exact=False)
    try:
        await link.wait_for(state="visible", timeout=15_000)
        await link.click()
    except PlaywrightTimeoutError:
        pass

    seg = page.locator(_SEGMENT)
    try:
        await seg.first.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeoutError:
        body = (await page.locator("body").inner_text()).lower()
        if (S.TXT_EMAIL_CONFIRM_AT in body or S.TXT_EMAIL_CONFIRM_FROM in body) and headless:
            raise SteamLoginError(
                "Steam requests EMAIL confirmation (new device). Use `login --headed`."
            )
        return

    body = (await page.locator("body").inner_text()).lower()
    if S.TXT_EMAIL_CONFIRM_AT in body or S.TXT_EMAIL_CONFIRM_FROM in body:
        if headless:
            raise SteamLoginError(
                "Steam requests EMAIL confirmation (new device). Use `login --headed`."
            )
        log.warning("EMAIL confirmation required: enter it manually in the window (waiting).")
        return

    code = await _twofactor_code(headless)
    if not code:
        log.warning("No 2FA code provided.")
        return
    await seg.first.click()
    await page.keyboard.type(code, delay=120)
    log.info("2FA code entered.")


async def _fill_login_form(page: Page, headless: bool) -> None:
    """Fills the Steam form (already visible on the page) + handles the 2FA."""
    if not settings.steam_username or not settings.steam_password:
        raise SteamLoginError("STEAM_USERNAME/STEAM_PASSWORD not set in the .env")
    pwd = page.locator(_PASSWORD)
    await pwd.wait_for(state="visible", timeout=30_000)
    user = page.locator(_USERNAME)
    await user.click()
    await user.press_sequentially(settings.steam_username, delay=30)
    await pwd.click()
    await pwd.press_sequentially(settings.steam_password, delay=30)
    await pwd.press("Enter")
    await _enter_2fa(page, headless)


# ---------------- NEW portal (steamgames.com) ----------------
async def _is_new_authed(page: Page) -> bool:
    await page.goto(NEW_DASHBOARD, wait_until="networkidle")
    return await page.locator(_SIGNIN_BTN).count() == 0


async def detect_publishers(page: Page) -> dict[str, str]:
    """Affiliated publishers ({partner_id: name}) from the new portal.

    Steam exposes `window.g_rgAllAffiliatedPublishers` on every portal page:
    used to auto-detect the STEAM_PARTNER_ID without configuring it manually.
    """
    try:
        await page.goto(NEW_HOME, wait_until="networkidle")
        raw = await page.evaluate(S.JS_AFFILIATED_PUBLISHERS)
        return {str(k): str(v) for k, v in (raw or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


async def _login_new(page: Page, headless: bool) -> None:
    log.info("Login NEW portal (steamgames.com)...")
    await page.goto(NEW_HOME, wait_until="networkidle")
    await page.locator(_SIGNIN_BTN).first.click()
    await _fill_login_form(page, headless)
    wait_s = 60 if headless else 240
    try:
        await page.wait_for_url(
            lambda u: "partner.steamgames.com/dashboard" in u and "goto=" not in u,
            timeout=wait_s * 1000,
        )
    except PlaywrightTimeoutError as exc:
        raise SteamLoginError("New portal login not completed. Use `login --headed`.") from exc
    log.info("New portal: authenticated.")


# ---------------- OLD portal (steampowered.com) ----------------
async def _is_old_authed(page: Page) -> bool:
    await page.goto(OLD_CHECK, wait_until="domcontentloaded")
    return "login" not in page.url.lower()


async def _login_old(page: Page, headless: bool) -> None:
    log.info("Login OLD portal (steampowered.com)...")
    await page.goto(OLD_CHECK, wait_until="networkidle")
    if "login" not in page.url.lower():
        return
    await _fill_login_form(page, headless)
    wait_s = 60 if headless else 240
    try:
        await page.wait_for_url(lambda u: "login" not in u.lower(), timeout=wait_s * 1000)
    except PlaywrightTimeoutError as exc:
        raise SteamLoginError("Old portal login not completed. Use `login --headed`.") from exc
    log.info("Old portal: authenticated.")


async def ensure_session(headless: bool = True) -> None:
    """Ensures the session on BOTH portals (login where needed)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await _new_context(browser)
        page = await context.new_page()
        try:
            if await _is_new_authed(page):
                log.info("New portal: valid session.")
            else:
                await _login_new(page, headless)
            if await _is_old_authed(page):
                log.info("Old portal: valid session.")
            else:
                await _login_old(page, headless)
            await context.storage_state(path=str(settings.storage_state_path))
            secure_file(settings.storage_state_path)
        finally:
            await browser.close()


@asynccontextmanager
async def authenticated_page(
    headless: bool = True, portal: Literal["new", "old"] = "new"
) -> AsyncIterator[Page]:
    """Authenticated page on the requested portal ('new'=steamgames, 'old'=steampowered)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await _new_context(browser)
        page = await context.new_page()
        try:
            if portal == "old":
                if not await _is_old_authed(page):
                    await _login_old(page, headless)
            else:
                if not await _is_new_authed(page):
                    await _login_new(page, headless)
            await context.storage_state(path=str(settings.storage_state_path))
            secure_file(settings.storage_state_path)
            yield page
        finally:
            try:
                await context.storage_state(path=str(settings.storage_state_path))
                secure_file(settings.storage_state_path)
            except Exception:  # noqa: BLE001
                pass
            await browser.close()


async def fetch_publishers(headless: bool = True) -> dict[str, str]:
    """Opens an authenticated page on the new portal and detects the affiliated publishers."""
    async with authenticated_page(headless=headless, portal="new") as page:
        return await detect_publishers(page)
