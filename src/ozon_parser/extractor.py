"""Extract product data from JSON embedded in an authenticated product page."""

import json
import re
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from .models import Product

MAX_JSON_DEPTH = 20
MAX_JSON_STRING = 2_000_000


def decode_nested_json(value, depth=0):
    """Decode serialized objects/arrays only; leave ordinary description text intact."""
    if depth >= MAX_JSON_DEPTH:
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) > MAX_JSON_STRING or not stripped.startswith(("{", "[")):
            return value
        try:
            decoded = json.loads(stripped)
        except (ValueError, TypeError):
            return value
        if not isinstance(decoded, (dict, list)):
            return value
        return decode_nested_json(decoded, depth + 1)
    if isinstance(value, dict):
        return {key: decode_nested_json(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_nested_json(item, depth + 1) for item in value]
    return value


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
    # Manufacturer article has priority over set contents or packaging.
    art_priority = ("артикул производителя", "art set", "комплектация", "состав набора")
    articles = {}
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
            }.items():
                if name in aliases and field not in result:
                    result[field] = str(value)
            if name in art_priority:
                articles[name] = str(value)
    result["art_set"] = next((articles[name] for name in art_priority if name in articles), None)
    return result


DOM_CHARACTERISTIC_ALIASES = {
    "color": ("цвет", "color"),
    "material": ("материал", "material"),
}
DOM_ART_PRIORITY = ("артикул производителя", "art set", "комплектация", "состав набора")


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def dom_characteristics(soup: BeautifulSoup) -> dict[str, str | None]:
    """Read rendered product characteristics when Ozon JSON-LD omits them."""
    result: dict[str, str | None] = {}
    articles: dict[str, str] = {}

    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if dt is None or dd is None:
            continue
        name = _clean_text(dt.get_text(" ", strip=True)).casefold()
        value = _clean_text(dd.get_text(" ", strip=True))
        if not name or not value:
            continue
        for field, aliases in DOM_CHARACTERISTIC_ALIASES.items():
            if name in aliases and field not in result:
                result[field] = value
        if name in DOM_ART_PRIORITY and name not in articles:
            articles[name] = value

    # Ozon may render a label/value pair as adjacent generic blocks instead of dl/dt/dd.
    wanted_labels = {
        alias for aliases in DOM_CHARACTERISTIC_ALIASES.values() for alias in aliases
    } | set(DOM_ART_PRIORITY)
    for text_node in soup.find_all(string=True):
        label = _clean_text(str(text_node)).casefold()
        if label not in wanted_labels:
            continue
        parent = text_node.parent
        if parent is None:
            continue

        candidates = []
        current = parent
        for _ in range(4):
            sibling = current.find_next_sibling()
            if sibling is not None:
                candidates.append(sibling)
            current = current.parent
            if current is None:
                break

        value = next(
            (
                _clean_text(candidate.get_text(" ", strip=True))
                for candidate in candidates
                if _clean_text(candidate.get_text(" ", strip=True))
                and _clean_text(candidate.get_text(" ", strip=True)).casefold() != label
            ),
            None,
        )
        if not value:
            continue
        for field, aliases in DOM_CHARACTERISTIC_ALIASES.items():
            if label in aliases and field not in result:
                result[field] = value
        if label in DOM_ART_PRIORITY and label not in articles:
            articles[label] = value

    result["art_set"] = next(
        (articles[name] for name in DOM_ART_PRIORITY if name in articles),
        None,
    )
    return result


def offer_price(offers, fallback):
    """Prefer the first valid explicitly priced offer, then the product price."""
    for offer in offers if isinstance(offers, list) else [offers]:
        if isinstance(offer, dict) and (value := number(offer.get("price"))) is not None:
            return value
    return number(fallback)


def extract_product(html: str, sku: str) -> Product:
    soup = BeautifulSoup(html, "html.parser")
    states = []
    for script in soup.select(
        'script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__'
    ):
        try:
            states.append(decode_nested_json(json.loads(script.string or script.get_text())))
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
    if not isinstance(aggregate, dict):
        aggregate = {}
    pictures = source.get("image") or source.get("images") or []
    if isinstance(pictures, str):
        pictures = [pictures]
    if isinstance(pictures, dict):
        pictures = [pictures.get("url")]
    details = characteristics(source)
    dom_details = dom_characteristics(soup)
    for field in ("color", "material", "art_set"):
        if not details.get(field) and dom_details.get(field):
            details[field] = dom_details[field]
    price = offer_price(offers, source.get("price"))
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
    # Only widgets explicitly tied to the requested SKU can augment this product.
    linked = [item for item in matches if item is not source]
    rich_widgets = [item.get("richContent") for item in linked if "richContent" in item]
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
        or rich_content(source.get("richContent"))
        or any(rich_content(widget) for widget in rich_widgets),
    )
