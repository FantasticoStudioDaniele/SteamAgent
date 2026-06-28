"""Sessione autenticata verso i DUE portali partner di Steam.

- NUOVO portale: partner.steamgames.com (traffico, UTM, achievements...). Login
  via modal React aperto da `g_ShowLoginDialog`.
- VECCHIO portale: partner.steampowered.com (wishlist, vendite, regioni,
  financials...). Login col form Steam diretto. Sessione SEPARATA.

Entrambi usano lo stesso login Steam (username/password + authenticator). Steam
mostra di default la conferma via app mobile: clicchiamo "Enter a code instead" e
digitiamo il TOTP nelle 5 caselle segmentate. La storage_state conserva i cookie
di ENTRAMBI i portali. Possibile one-time conferma EMAIL (nuovo dispositivo):
in --headed la completa l'utente.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from steam_agent.auth.steam_guard import generate_twofactor_code
from steam_agent.settings import settings

log = logging.getLogger(__name__)

NEW_HOME = "https://partner.steamgames.com/"
NEW_DASHBOARD = "https://partner.steamgames.com/dashboard"
OLD_BASE = "https://partner.steampowered.com"
OLD_CHECK = f"{OLD_BASE}/dir.php"

_SIGNIN_BTN = 'button[onclick*="g_ShowLoginDialog"]'
_PASSWORD = "input[type='password']"
_USERNAME = "xpath=//input[@type='password']/preceding::input[@type='text'][1]"
_SEGMENT = "input[type='text']:not(#appHeaderFindInput)"


class SteamLoginError(RuntimeError):
    pass


async def _new_context(browser) -> BrowserContext:
    if settings.storage_state_path.exists():
        return await browser.new_context(storage_state=str(settings.storage_state_path))
    return await browser.new_context()


async def _twofactor_code(headless: bool) -> str | None:
    """Codice 2FA: TOTP se c'è lo shared_secret, altrimenti lo chiede a video.

    Senza shared_secret in modalità headless non è possibile procedere
    (login non presidiato): si solleva un errore con istruzioni.
    """
    secret = settings.steam_shared_secret.strip()
    if secret:
        return generate_twofactor_code(secret)
    if headless:
        raise SteamLoginError(
            "Nessuno STEAM_SHARED_SECRET e modalità headless: impossibile inserire il 2FA.\n"
            "Esegui `steam-agent login --headed` (inserisci il codice a mano) oppure "
            "configura STEAM_SHARED_SECRET per il login automatico."
        )
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(
        None, lambda: input("Codice Steam Guard (dall'app mobile o email): ").strip()
    )
    return code or None


async def _enter_2fa(page: Page, headless: bool) -> None:
    """Gestisce lo step 2FA: passa all'inserimento codice e digita il codice."""
    try:
        await page.locator(_PASSWORD).wait_for(state="hidden", timeout=30_000)
    except PlaywrightTimeoutError:
        pass

    link = page.get_by_text("Enter a code instead", exact=False)
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
        if ("email address at" in body or "from your email" in body) and headless:
            raise SteamLoginError(
                "Steam chiede conferma via EMAIL (nuovo dispositivo). Usa `login --headed`."
            )
        return

    body = (await page.locator("body").inner_text()).lower()
    if "email address at" in body or "from your email" in body:
        if headless:
            raise SteamLoginError(
                "Steam chiede conferma via EMAIL (nuovo dispositivo). Usa `login --headed`."
            )
        log.warning("Conferma EMAIL richiesta: inseriscila a mano nella finestra (attendo).")
        return

    code = await _twofactor_code(headless)
    if not code:
        log.warning("Nessun codice 2FA fornito.")
        return
    await seg.first.click()
    await page.keyboard.type(code, delay=120)
    log.info("Codice 2FA inserito.")


async def _fill_login_form(page: Page, headless: bool) -> None:
    """Compila il form Steam (gia' visibile in pagina) + gestisce il 2FA."""
    if not settings.steam_username or not settings.steam_password:
        raise SteamLoginError("STEAM_USERNAME/STEAM_PASSWORD non impostati nel .env")
    pwd = page.locator(_PASSWORD)
    await pwd.wait_for(state="visible", timeout=30_000)
    user = page.locator(_USERNAME)
    await user.click()
    await user.press_sequentially(settings.steam_username, delay=30)
    await pwd.click()
    await pwd.press_sequentially(settings.steam_password, delay=30)
    await pwd.press("Enter")
    await _enter_2fa(page, headless)


# ---------------- NUOVO portale (steamgames.com) ----------------
async def _is_new_authed(page: Page) -> bool:
    await page.goto(NEW_DASHBOARD, wait_until="networkidle")
    return await page.locator(_SIGNIN_BTN).count() == 0


async def detect_publishers(page: Page) -> dict[str, str]:
    """Editori affiliati ({partner_id: nome}) dal portale nuovo.

    Steam espone `window.g_rgAllAffiliatedPublishers` su ogni pagina del portale:
    serve ad auto-rilevare lo STEAM_PARTNER_ID senza configurarlo a mano.
    """
    try:
        await page.goto(NEW_HOME, wait_until="networkidle")
        raw = await page.evaluate("() => window.g_rgAllAffiliatedPublishers || {}")
        return {str(k): str(v) for k, v in (raw or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


async def _login_new(page: Page, headless: bool) -> None:
    log.info("Login portale NUOVO (steamgames.com)...")
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
        raise SteamLoginError("Login portale nuovo non completato. Usa `login --headed`.") from exc
    log.info("Portale nuovo: autenticato.")


# ---------------- VECCHIO portale (steampowered.com) ----------------
async def _is_old_authed(page: Page) -> bool:
    await page.goto(OLD_CHECK, wait_until="domcontentloaded")
    return "login" not in page.url.lower()


async def _login_old(page: Page, headless: bool) -> None:
    log.info("Login portale VECCHIO (steampowered.com)...")
    await page.goto(OLD_CHECK, wait_until="networkidle")
    if "login" not in page.url.lower():
        return
    await _fill_login_form(page, headless)
    wait_s = 60 if headless else 240
    try:
        await page.wait_for_url(lambda u: "login" not in u.lower(), timeout=wait_s * 1000)
    except PlaywrightTimeoutError as exc:
        raise SteamLoginError("Login portale vecchio non completato. Usa `login --headed`.") from exc
    log.info("Portale vecchio: autenticato.")


async def ensure_session(headless: bool = True) -> None:
    """Garantisce la sessione su ENTRAMBI i portali (login dove serve)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await _new_context(browser)
        page = await context.new_page()
        try:
            if await _is_new_authed(page):
                log.info("Portale nuovo: sessione valida.")
            else:
                await _login_new(page, headless)
            if await _is_old_authed(page):
                log.info("Portale vecchio: sessione valida.")
            else:
                await _login_old(page, headless)
            await context.storage_state(path=str(settings.storage_state_path))
        finally:
            await browser.close()


@asynccontextmanager
async def authenticated_page(
    headless: bool = True, portal: Literal["new", "old"] = "new"
) -> AsyncIterator[Page]:
    """Page autenticata sul portale richiesto ('new'=steamgames, 'old'=steampowered)."""
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
            yield page
        finally:
            try:
                await context.storage_state(path=str(settings.storage_state_path))
            except Exception:  # noqa: BLE001
                pass
            await browser.close()


async def fetch_publishers(headless: bool = True) -> dict[str, str]:
    """Apre una pagina autenticata sul portale nuovo e rileva gli editori affiliati."""
    async with authenticated_page(headless=headless, portal="new") as page:
        return await detect_publishers(page)
