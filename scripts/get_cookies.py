"""Interactive Ozon login and optional Gmail code polling."""

import argparse
import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from ozon_parser.auth_guard import blocked_page_text
from ozon_parser.gmail import gmail_service, wait_for_code


def ensure_not_blocked(pages) -> None:
    for current in pages:
        if not current.is_closed() and blocked_page_text(current.locator("body").inner_text()):
            raise RuntimeError("Ozon denied access in this browser. Cookies were not saved.")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gmail",
        action="store_true",
        help="Poll Gmail and show the new verification code privately in terminal",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    started = datetime.now(UTC)
    if args.gmail:

        def poll():
            try:
                service = gmail_service(
                    os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"),
                    os.getenv("GMAIL_TOKEN_FILE", "token.json"),
                )
                code = wait_for_code(service, started)
                print(f"Verification code (do not share): {code}")
            except Exception as exc:
                logging.error("Gmail verification failed: %s", type(exc).__name__)

        threading.Thread(target=poll, daemon=True).start()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto("https://data.ozon.ru/", wait_until="domcontentloaded", timeout=30000)
        ensure_not_blocked(context.pages)
        url = urlsplit(page.url)
        print(f"Browser page: {url.scheme}://{url.netloc}{url.path}")
        confirmation = input(
            "After you SEE the browser and complete login, type SAVE (Enter cancels): "
        )
        if confirmation != "SAVE":
            raise RuntimeError("Login was not confirmed; cookies were not saved")
        ensure_not_blocked(context.pages)
        cookies = [
            cookie for cookie in context.cookies() if cookie.get("domain", "").endswith("ozon.ru")
        ]
        if not cookies:
            raise RuntimeError("No Ozon cookies found; login did not complete")
        path = Path(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
        path.write_text(json.dumps(cookies), encoding="utf-8")
        path.chmod(0o600)
        logging.info("Saved browser cookies; Ozon authentication is not verified yet")
        browser.close()


if __name__ == "__main__":
    main()
