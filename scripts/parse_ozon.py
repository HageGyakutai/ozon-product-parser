import argparse
import csv
import logging
import os
from contextlib import nullcontext
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

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
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if any(not sku.isdecimal() for sku in args.skus):
        parser.error("Each SKU must be numeric")
    if args.html_file and len(args.skus) != 1:
        parser.error("--html-file requires exactly one SKU")
    if args.html_file and args.debug_html_dir:
        parser.error("--debug-html-dir is only available in live mode")
    client = None
    if not args.html_file:
        try:
            client = product_session(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
        except (OSError, ValueError) as exc:
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
                html = saved_html if args.html_file else fetch_product(client, sku)
                if args.debug_html_dir:
                    save_debug_html(args.debug_html_dir / f"{sku}.html", html)
                product = extract_product(html, sku)
                save_product(db, product)
                products.append(product)
                logging.info("Saved SKU=%s", sku)
            except Exception:
                logging.exception("Failed SKU=%s", sku)
    if args.csv and products:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(vars(products[0])))
            writer.writeheader()
            writer.writerows(vars(item) for item in products)
    engine.dispose()
    if len(products) != len(args.skus):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
