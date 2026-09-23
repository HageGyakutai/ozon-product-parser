"""Parse Ozon product pages and save the result to PostgreSQL or CSV."""

import argparse
import csv
import logging
import os
from collections.abc import Callable
from contextlib import ExitStack
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ozon_parser.browser_client import BrowserProductClient
from ozon_parser.client import fetch_product, product_session
from ozon_parser.database_runtime import prepare_database
from ozon_parser.extractor import extract_product
from ozon_parser.models import Product
from ozon_parser.storage import database_engine, save_product

LOGGER = logging.getLogger(__name__)


def _write_csv(path: Path, products: list[Product]) -> None:
    """Write products using the exact twelve columns required by the task."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(vars(products[0])))
        writer.writeheader()
        writer.writerows(vars(product) for product in products)
    LOGGER.info("CSV exported: %s rows to %s", len(products), path)


def main() -> None:
    """Run one parsing batch from command-line arguments."""
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("skus", nargs="+", help="Numeric Ozon product IDs")
    parser.add_argument(
        "--output",
        choices=("database", "csv"),
        default="database",
        help="Where to save parsed products (default: database)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="CSV path used with --output csv (default: output/products.csv)",
    )
    parser.add_argument(
        "--no-start-database",
        action="store_true",
        help="Fail instead of starting PostgreSQL with Docker Compose",
    )
    parser.add_argument(
        "--transport",
        choices=("requests", "browser"),
        default="requests",
        help="Product transport: requests (default) or Chrome browser",
    )
    parser.add_argument(
        "--browser-headless",
        action="store_true",
        help="Run a Playwright-launched browser without a visible window",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if any(not sku.isascii() or not sku.isdecimal() for sku in args.skus):
        parser.error("Each SKU must contain ASCII digits")
    if args.output == "database" and args.csv is not None:
        parser.error("--csv is available only with --output csv")
    if args.output == "csv" and args.no_start_database:
        parser.error("--no-start-database is available only with --output database")

    cookies_file = os.getenv("OZON_COOKIES_FILE", "cookies.json")
    csv_path = args.csv or Path("output/products.csv")
    engine: Engine | None = None
    products: list[Product] = []

    try:
        with ExitStack() as stack:
            fetch_html: Callable[[str], str]
            if args.transport == "browser":
                browser_client = stack.enter_context(
                    BrowserProductClient(
                        cookies_file,
                        browser_name=os.getenv("OZON_BROWSER", "chromium"),
                        channel=os.getenv("OZON_BROWSER_CHANNEL", "").strip() or None,
                        headless=args.browser_headless,
                        cdp_endpoint=os.getenv("OZON_CDP_ENDPOINT", "").strip() or None,
                    )
                )
                fetch_html = browser_client.fetch_product
            else:
                http_session = stack.enter_context(product_session(cookies_file))
                fetch_html = partial(fetch_product, http_session)

            database_session: Session | None = None
            if args.output == "database":
                engine = database_engine()
                prepare_database(engine, auto_start=not args.no_start_database)
                database_session = stack.enter_context(Session(engine))

            for sku in args.skus:
                try:
                    LOGGER.info("Parsing SKU=%s", sku)
                    product = extract_product(fetch_html(sku), sku)
                    if database_session is not None:
                        save_product(database_session, product)
                    products.append(product)
                    LOGGER.info("Parsed SKU=%s", sku)
                except (ValueError, OSError) as exc:
                    LOGGER.error("Failed SKU=%s: %s", sku, exc)
                except Exception:
                    LOGGER.exception("Unexpected failure for SKU=%s", sku)
    except (OSError, ValueError, RuntimeError) as exc:
        LOGGER.error("Cannot start parser: %s", exc)
        raise SystemExit(2) from None
    finally:
        if engine is not None:
            engine.dispose()

    if args.output == "csv" and products:
        _write_csv(csv_path, products)

    failed = len(args.skus) - len(products)
    LOGGER.info("Parsing complete: %s succeeded, %s failed", len(products), failed)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
