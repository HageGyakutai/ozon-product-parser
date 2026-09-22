import json
from decimal import Decimal

import pytest

from ozon_parser.extractor import extract_product, number


def html(description="Text"):
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "sku": "123",
        "name": "Example",
        "offers": {"price": "1 999,50"},
        "aggregateRating": {"ratingValue": "4.7", "reviewCount": "12"},
        "image": ["https://example.org/p.jpg"],
        "description": description,
        "characteristics": [{"name": "Цвет", "value": "Красный"}],
    }
    return '<script type="application/ld+json">' + json.dumps(data) + "</script>"


def test_product():
    item = extract_product(html(), "123")
    assert item.price == Decimal("1999.50")
    assert item.rating == Decimal("4.7")
    assert item.reviews_total == 12
    assert item.color == "Красный"
    assert item.material is None
    assert item.photos_seller is None
    assert item.has_rich_content is False


@pytest.mark.parametrize(
    "element", ["<img src='x'>", "<table><tr></tr></table>", "<ul><li>x</li></ul>"]
)
def test_rich(element):
    assert extract_product(html(element), "123").has_rich_content


def test_no_json():
    with pytest.raises(ValueError, match="embedded JSON"):
        extract_product("<html></html>", "123")


def test_number():
    assert number("1 999 ₽") == Decimal(1999)
