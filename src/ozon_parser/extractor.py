"""Extract product data from JSON embedded in an authenticated product page."""

import json
import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from .models import Product


def number(value):
    if value is None or value == "":
        return None
    cleaned = re.sub(r"[^0-9,.\-]", "", str(value).replace("\u00a0", ""))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(",", "")
            if cleaned.rfind(".") > cleaned.rfind(",")
            else cleaned.replace(".", "").replace(",", ".")
        )
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def rich_content(value):
    if isinstance(value, dict):
        if any(
            str(k).lower() in {"image", "images", "table", "list", "ul", "ol"} and v
            for k, v in value.items()
        ):
            return True
        return any(rich_content(v) for v in value.values())
    if isinstance(value, list):
        return any(rich_content(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"<(?:img|table|ul|ol)\b", value, re.I))


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def first(node, *names):
    for item in walk(node):
        for key in names:
            if key in item and item[key] not in (None, ""):
                return item[key]
    return None


def characteristics(node):
    result = {}
    for item in walk(node):
        name = str(item.get("name", item.get("title", ""))).lower().strip()
        value = item.get("value", item.get("values"))
        if isinstance(value, list):
            value = ", ".join(
                str(v.get("name", v)) if isinstance(v, dict) else str(v) for v in value
            )
        if isinstance(value, (str, int)) and value:
            for field, aliases in {
                "color": ("цвет", "color"),
                "material": ("материал", "material"),
                "art_set": ("артикул производителя", "комплектация", "состав набора", "art set"),
            }.items():
                if name in aliases:
                    result[field] = str(value)
    return result


def extract_product(html: str, sku: str) -> Product:
    soup = BeautifulSoup(html, "html.parser")
    states = []
    for script in soup.select(
        'script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__'
    ):
        try:
            states.append(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError):
            continue
    if not states:
        raise ValueError("No parseable embedded JSON in product page; inspect authenticated HTML")
    candidates = [item for state in states for item in walk(state)]
    matches = [item for item in candidates if str(item.get("sku") or item.get("productId")) == sku]
    product_state = next((item for item in matches if item.get("@type") == "Product"), None)
    source = product_state or next(
        (
            item
            for item in matches
            if any(k in item for k in ("sku", "productId"))
            and any(k in item for k in ("name", "title"))
        ),
        None,
    )
    if not source:
        raise ValueError(f"Embedded JSON has no recognizable product for SKU={sku}")
    source_sku = source.get("sku") or source.get("productId")
    if source_sku is not None and str(source_sku) != sku:
        raise ValueError(f"Embedded product SKU={source_sku} differs from requested SKU={sku}")
    title = source.get("name") or source.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Product title missing in embedded JSON")
    offers = source.get("offers") or {}
    aggregate = source.get("aggregateRating") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    if not isinstance(aggregate, dict):
        aggregate = {}
    pictures = source.get("image") or source.get("images") or []
    if isinstance(pictures, str):
        pictures = [pictures]
    if isinstance(pictures, dict):
        pictures = [pictures.get("url")]
    details = characteristics(source)
    price = number(offers.get("price") if offers.get("price") is not None else source.get("price"))
    rating = number(
        aggregate.get("ratingValue")
        if aggregate.get("ratingValue") is not None
        else source.get("rating")
    )
    reviews = number(
        aggregate.get("reviewCount")
        if aggregate.get("reviewCount") is not None
        else source.get("reviewsCount")
    )
    if reviews is not None and reviews != int(reviews):
        raise ValueError("Reviews count must be an integer")
    return Product(
        sku=sku,
        title=title.strip(),
        price=price,
        rating=rating,
        reviews_total=int(reviews) if reviews is not None else None,
        cover_image=pictures[0] if pictures else None,
        photos_seller=int(source["photosSeller"])
        if str(source.get("photosSeller", "")).isdigit()
        else None,
        videos_seller=int(source["videosSeller"])
        if str(source.get("videosSeller", "")).isdigit()
        else None,
        color=details.get("color"),
        material=details.get("material"),
        art_set=details.get("art_set"),
        has_rich_content=rich_content(source.get("description"))
        or rich_content(source.get("richContent")),
    )
