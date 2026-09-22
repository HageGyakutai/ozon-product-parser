import argparse
import csv
import logging
import os
from contextlib import nullcontext
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from ozon_parser.browser_client import BrowserProductClient
from ozon_parser.client import fetch_product, product_session
from ozon_parser.debug_html import save_debug_html
from ozon_parser.extractor import extract_product
from ozon_parser.storage import database_engine, save_product


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("skus", nargs="+", help="Numeric Ozon product IDs")
    parser.add_argument("--csv", type=Path, help="Additional CSV export")
    parser.add_argument(
        "--html-file", type=Path, help="Parse one saved HTML page without Ozon access"
    )
    parser.add_argument("--debug-html-dir", type=Path, help="Save redacted live HTML snapshots")
    parser.add_argument(
        "--transport",
        choices=("requests", "browser"),
        default="requests",
        help="Live product transport: requests (default) or Playwright browser",
    )
    parser.add_argument(
        "--browser-headless",
        action="store_true",
        help="Run browser transport without a visible window",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if any(not sku.isascii() or not sku.isdecimal() for sku in args.skus):
        parser.error("Each SKU must contain ASCII digits")
    if args.html_file and len(args.skus) != 1:
        parser.error("--html-file requires exactly one SKU")
    if args.html_file and args.debug_html_dir:
        parser.error("--debug-html-dir is only available in live mode")
    client = None
    if not args.html_file:
        cookies_file = os.getenv("OZON_COOKIES_FILE", "cookies.json")
        try:
            if args.transport == "browser":
                client = BrowserProductClient(
                    cookies_file,
                    browser_name=os.getenv("OZON_BROWSER", "chromium"),
                    channel=os.getenv("OZON_BROWSER_CHANNEL", "").strip() or None,
                    headless=args.browser_headless,
                    cdp_endpoint=os.getenv("OZON_CDP_ENDPOINT", "").strip() or None,
                )
            else:
                client = product_session(cookies_file)
        except (OSError, ValueError, RuntimeError) as exc:
            logging.error("Cannot start parser: %s", exc)
            raise SystemExit(2) from None
    else:
        try:
            saved_html = args.html_file.read_text(encoding="utf-8")
        except OSError as exc:
            logging.error("Cannot read saved HTML: %s", exc)
            raise SystemExit(2) from None
    try:
        engine = database_engine()
    except ValueError as exc:
        if client is not None:
            client.close()
        logging.error("Cannot start parser: %s", exc)
        raise SystemExit(2) from None
    products = []
    with client if client is not None else nullcontext(), Session(engine) as db:
        for sku in args.skus:
            try:
                logging.info("Parsing SKU=%s", sku)
                if args.html_file:
                    html = saved_html
                elif args.transport == "browser":
                    html = client.fetch_product(sku)
                else:
                    html = fetch_product(client, sku)
                if args.debug_html_dir:
                    save_debug_html(args.debug_html_dir / f"{sku}.html", html)
                product = extract_product(html, sku)
                save_product(db, product)
                products.append(product)
                logging.info("Saved SKU=%s", sku)
            except (ValueError, OSError) as exc:
                logging.error("Failed SKU=%s: %s", sku, exc)
            except Exception:
                logging.exception("Unexpected failure for SKU=%s", sku)
    if args.csv and products:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(vars(products[0])))
            writer.writeheader()
            writer.writerows(vars(item) for item in products)
        logging.info("CSV exported: %s rows", len(products))
    engine.dispose()
    logging.info(
        "Parsing complete: %s saved, %s failed", len(products), len(args.skus) - len(products)
    )
    if len(products) != len(args.skus):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
