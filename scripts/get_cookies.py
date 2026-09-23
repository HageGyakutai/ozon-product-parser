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
from ozon_parser.cdp_browser import ensure_cdp_browser
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
    if not page.url.startswith("https://data.ozon.ru/"):
        # Ozon can keep loading background resources for a long time. Waiting for
        # the navigation commit is enough; the locator below verifies UI readiness.
        page.goto("https://data.ozon.ru/", wait_until="commit", timeout=30000)
    else:
        LOGGER.info("Reusing data.ozon.ru page already open in Chrome")
    ensure_not_blocked(context)
    analytics_button = page.get_by_role(
        "button", name=re.compile("Перейти к аналитике", re.I)
    ).first
    analytics_button.wait_for(state="visible", timeout=30000)
    analytics_button.click()
    page.wait_for_url(
        re.compile(r"^https://sso\.ozon\.ru/"),
        wait_until="commit",
        timeout=30000,
    )
    page = current_page(context)
    ensure_not_blocked(context)
    # The current Ozon ID form exposes no placeholder attribute. Waiting on
    # the semantic input selector also avoids racing the page's DOM rendering.
    phone_input = page.locator(
        'input[type="tel"], input[autocomplete="tel"], input[name*="phone" i]'
    ).first
    phone_input.wait_for(state="visible", timeout=30000)
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
    # Ozon renders the confirmation control without an accessible name.
    # At this step the verification code is the only visible input.
    code_input = page.locator("input:visible").first
    code_input.wait_for(state="visible", timeout=30000)
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
        cdp_url = os.getenv("OZON_CDP_ENDPOINT", "").strip() or os.getenv(
            "OZON_CDP_URL", ""
        ).strip()
        if cdp_url:
            if browser_name != "chromium":
                raise ValueError("OZON_CDP_URL is available only with OZON_BROWSER=chromium")
            ensure_cdp_browser(cdp_url, start_url="https://data.ozon.ru/")
            LOGGER.info("Connecting to Chrome session via CDP")
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            if not browser.contexts:
                raise RuntimeError("Connected Chrome has no browser context")
            context = browser.contexts[0]
            owns_browser = False
        else:
            browser = getattr(playwright, browser_name).launch(
                headless=False, **({"channel": channel} if channel else {})
            )
            context = browser.new_context(locale="ru-RU")
            owns_browser = True
        try:
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
            if owns_browser:
                browser.close()


if __name__ == "__main__":
    main()
