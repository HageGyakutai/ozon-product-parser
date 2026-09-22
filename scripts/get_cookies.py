"""Interactive login: user handles phone verification in browser; optionally poll Gmail for the code."""
import argparse
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from ozon_parser.gmail import gmail_service, wait_for_code


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--gmail", action="store_true", help="Poll Gmail and show the new verification code privately in terminal")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    started = datetime.now(timezone.utc)
    if args.gmail:
        def poll():
            try:
                service = gmail_service(os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"), os.getenv("GMAIL_TOKEN_FILE", "token.json"))
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
        input("Complete login in the browser, verify your account, then press Enter here to save cookies: ")
        cookies = [cookie for cookie in context.cookies() if cookie.get("domain", "").endswith("ozon.ru")]
        if not cookies:
            raise RuntimeError("No Ozon cookies found; login did not complete")
        path = Path(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
        path.write_text(json.dumps(cookies), encoding="utf-8")
        path.chmod(0o600)
        logging.info("Saved Ozon cookies")
        browser.close()


if __name__ == "__main__":
    main()
