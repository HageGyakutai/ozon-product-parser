"""Automated Ozon phone login using a new Gmail verification message."""

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from ozon_parser.auth_guard import blocked_page_text
from ozon_parser.gmail import gmail_service, wait_for_code
from ozon_parser.session_data import ozon_cookie_domain, save_browser_session

LOGGER = logging.getLogger(__name__)


def ensure_not_blocked(context) -> None:
    for page in context.pages:
        if not page.is_closed() and (
            blocked_page_text(page.locator("body").inner_text())
            or "antibot challenge" in page.title().casefold()
        ):
            raise RuntimeError("Ozon refused this browser. No cookies saved; see incident on page.")


def current_page(context):
    return next((page for page in reversed(context.pages) if not page.is_closed()), None)


def login_page(context):
    """Return an open page, creating the initial tab for a fresh context."""
    return current_page(context) or context.new_page()


def authenticate(context, phone: str, gmail) -> None:
    page = login_page(context)
    page.goto("https://data.ozon.ru/", wait_until="domcontentloaded", timeout=30000)
    ensure_not_blocked(context)
    page.get_by_role("button", name=re.compile("Перейти к аналитике", re.I)).first.click()
    page = current_page(context)
    ensure_not_blocked(context)
    phone_input = page.get_by_placeholder(re.compile(r"9999|телефон", re.I))
    phone_input.wait_for(state="visible", timeout=15000)
    phone_input.fill(phone)
    started = datetime.now(UTC)
    page.get_by_role("button", name=re.compile(r"^Войти$|Продолжить", re.I)).click()
    LOGGER.info("Phone verification requested")
    ensure_not_blocked(context)
    LOGGER.info("Waiting for new Gmail verification email")
    code = wait_for_code(gmail, started)
    LOGGER.info("New Gmail verification email received")
    page = current_page(context)
    ensure_not_blocked(context)
    code_input = page.get_by_role("textbox", name=re.compile("код|code", re.I))
    code_input.wait_for(state="visible", timeout=15000)
    code_input.fill(code)
    # Ozon may submit automatically after the last digit.
    try:
        page.get_by_role("button", name=re.compile("Подтвердить|Продолжить|Войти", re.I)).click(
            timeout=3000
        )
    except PlaywrightTimeoutError:
        pass
    try:
        page.wait_for_url(re.compile(r"^https://data\.ozon\.ru/"), timeout=20000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Ozon did not return to data.ozon.ru after verification") from exc
    ensure_not_blocked(context)
    if "sso.ozon.ru" in current_page(context).url:
        raise RuntimeError("Ozon login was not completed")


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    phone = os.getenv("OZON_PHONE", "").strip()
    if not phone:
        raise ValueError("Set OZON_PHONE in .env before starting Ozon login")
    if not re.fullmatch(r"\+?[0-9]{10,15}", phone):
        raise ValueError("OZON_PHONE must contain 10–15 digits with optional leading +")
    LOGGER.info("Checking Gmail API access for Ozon verification")
    gmail = gmail_service(
        os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"),
        os.getenv("GMAIL_TOKEN_FILE", "token.json"),
    )
    LOGGER.info("Starting Ozon browser login")
    with sync_playwright() as playwright:
        browser_name = os.getenv("OZON_BROWSER", "chromium").strip().lower()
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise ValueError("OZON_BROWSER must be chromium, firefox or webkit")
        channel = os.getenv("OZON_BROWSER_CHANNEL", "").strip()
        if channel and channel not in {"chrome", "msedge"}:
            raise ValueError("OZON_BROWSER_CHANNEL must be chrome or msedge")
        if channel and browser_name != "chromium":
            raise ValueError("OZON_BROWSER_CHANNEL is available only with OZON_BROWSER=chromium")
        browser = getattr(playwright, browser_name).launch(
            headless=False, **({"channel": channel} if channel else {})
        )
        try:
            context = browser.new_context(locale="ru-RU")
            authenticate(context, phone, gmail)
            cookies = [
                cookie for cookie in context.cookies() if ozon_cookie_domain(cookie.get("domain"))
            ]
            if not cookies:
                raise RuntimeError("No Ozon cookies found after authentication")
            path = Path(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
            page = current_page(context)
            if page is None:
                raise RuntimeError("Browser page closed before session could be saved")
            user_agent = page.evaluate("navigator.userAgent")
            save_browser_session(path, cookies, user_agent)
            LOGGER.info("Ozon login completed; cookies saved")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
