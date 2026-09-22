import json
from decimal import Decimal

import pytest

from ozon_parser.extractor import decode_nested_json, extract_product, number


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


def test_rejects_wrong_sku():
    with pytest.raises(ValueError, match="SKU=123"):
        extract_product(html().replace('"sku": "123"', '"sku": "456"'), "123")


def test_chooses_requested_product_from_multiple_json_scripts():
    item = extract_product(html().replace('"sku": "123"', '"sku": "456"') + html(), "123")
    assert item.sku == "123"
    assert item.price == Decimal("1999.50")


def embedded(state):
    return '<script type="application/json">' + json.dumps(state) + "</script>"


def test_nested_serialized_json_and_non_json_text():
    state = {
        "widget": json.dumps(
            {
                "items": [
                    json.dumps(
                        {
                            "@type": "Product",
                            "sku": "123",
                            "name": "Nested",
                            "description": "{not JSON}",
                        }
                    )
                ]
            }
        )
    }
    assert extract_product(embedded(state), "123").title == "Nested"
    assert decode_nested_json("plain [text] and 123") == "plain [text] and 123"
    assert decode_nested_json("123") == "123"
    assert decode_nested_json("{not JSON}") == "{not JSON}"


def test_selects_matching_sku_without_mixing_other_product_fields():
    other = {
        "@type": "Product",
        "sku": "456",
        "name": "Other",
        "price": 1,
        "richContent": {"image": "https://example.org/review.jpg"},
    }
    wanted = {"@type": "Product", "sku": "123", "name": "Wanted", "price": 2}
    item = extract_product(embedded({"products": [other, wanted]}), "123")
    assert (item.title, item.price, item.has_rich_content) == ("Wanted", Decimal(2), False)


def test_price_rating_reviews_cover_media_and_characteristics():
    state = {
        "@type": "Product",
        "sku": "123",
        "name": "Item",
        "price": "999",
        "offers": [{"price": "invalid"}, {"price": "1 234,50"}],
        "aggregateRating": {"ratingValue": "4.8", "reviewCount": "37"},
        "image": ["https://example.org/cover.jpg", "https://example.org/2.jpg"],
        "photosSeller": 2,
        "videosSeller": 1,
        "characteristics": [
            {"name": "Состав набора", "value": "Три предмета"},
            {"name": "Комплектация", "value": "Коробка"},
            {"name": "Артикул производителя", "value": "M-123"},
            {"name": "Цвет", "value": "Красный"},
            {"name": "Материал", "value": "Хлопок"},
        ],
        "reviews": [{"image": ["https://example.org/review.jpg"]}],
        "description": "Text",
    }
    item = extract_product(embedded(state), "123")
    assert item.price == Decimal("1234.50")
    assert (item.rating, item.reviews_total) == (Decimal("4.8"), 37)
    assert item.cover_image == "https://example.org/cover.jpg"
    assert (item.photos_seller, item.videos_seller) == (2, 1)
    assert (item.color, item.material, item.art_set) == ("Красный", "Хлопок", "M-123")
    assert item.has_rich_content is False


def test_separate_rich_widget_for_requested_sku():
    product = {"@type": "Product", "sku": "123", "name": "Item"}
    widget = {"sku": "123", "richContent": {"widgets": [{"table": {"rows": [1]}}]}}
    assert extract_product(embedded({"items": [product, widget]}), "123").has_rich_content


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sku", "123"),
        ("title", "Item"),
        ("price", Decimal("15.50")),
        ("rating", Decimal("4.9")),
        ("reviews_total", 9),
        ("cover_image", "https://example.org/cover.jpg"),
        ("photos_seller", 3),
        ("videos_seller", 2),
        ("color", "Белый"),
        ("material", "Хлопок"),
        ("art_set", "A-1"),
        ("has_rich_content", True),
    ],
)
def test_each_required_field(field, value):
    state = {
        "@type": "Product",
        "sku": "123",
        "name": "Item",
        "offers": {"price": "15,50"},
        "aggregateRating": {"ratingValue": "4.9", "reviewCount": 9},
        "image": "https://example.org/cover.jpg",
        "photosSeller": 3,
        "videosSeller": 2,
        "characteristics": [
            {"name": "Цвет", "value": "Белый"},
            {"name": "Материал", "value": "Хлопок"},
            {"name": "Артикул производителя", "value": "A-1"},
        ],
        "richContent": {"list": ["one"]},
    }
    assert getattr(extract_product(embedded(state), "123"), field) == value


def test_price_uses_product_fallback_if_offers_have_no_valid_price():
    state = {
        "@type": "Product",
        "sku": "123",
        "name": "Item",
        "price": "90",
        "offers": [{"price": None}, {"price": "unknown"}],
    }
    assert extract_product(embedded(state), "123").price == Decimal("90")


def test_dom_characteristics_fill_missing_json_fields():
    page = html().replace(
        "</script>",
        """</script>
        <dl><dt><span>Цвет</span></dt><dd>Синий</dd></dl>
        <dl><dt><span>Материал</span></dt><dd>Бумага</dd></dl>
        <dl><dt><span>Артикул производителя</span></dt><dd>ABC-42</dd></dl>
        """,
    )
    page = page.replace(
        '"characteristics": [{"name": "Цвет", "value": "Красный"}],',
        '"characteristics": [],',
    )
    item = extract_product(page, "123")
    assert (item.color, item.material, item.art_set) == ("Синий", "Бумага", "ABC-42")


def test_json_characteristics_have_priority_over_dom_fallback():
    page = html() + """
    <dl><dt>Цвет</dt><dd>Синий</dd></dl>
    <dl><dt>Материал</dt><dd>Бумага</dd></dl>
    """
    item = extract_product(page, "123")
    assert item.color == "Красный"
    assert item.material == "Бумага"
