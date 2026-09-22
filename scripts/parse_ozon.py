import argparse
import csv
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from ozon_parser.client import fetch_product, product_session
from ozon_parser.extractor import extract_product
from ozon_parser.storage import database_engine, save_product


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("skus", nargs="+", help="Numeric Ozon product IDs")
    parser.add_argument("--csv", type=Path, help="Additional CSV export")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if any(not sku.isdecimal() for sku in args.skus):
        parser.error("Each SKU must be numeric")
    engine = database_engine()
    client = product_session(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
    products = []
    with Session(engine) as db:
        for sku in args.skus:
            try:
                logging.info("Parsing SKU=%s", sku)
                product = extract_product(fetch_product(client, sku), sku)
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
