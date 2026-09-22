from decimal import Decimal

import pytest

from ozon_parser.models import Product


@pytest.mark.parametrize(
    "changes",
    [
        {"sku": "bad"},
        {"title": " "},
        {"price": 1.25},
        {"price": Decimal("-1")},
        {"price": Decimal("NaN")},
        {"price": Decimal("1.001")},
        {"rating": Decimal("5.1")},
        {"reviews_total": -1},
        {"photos_seller": True},
        {"has_rich_content": "false"},
    ],
)
def test_reject_invalid_product(changes):
    with pytest.raises(ValueError):
        Product(**({"sku": "123", "title": "Test"} | changes))


def test_nullable_product_and_zero_values():
    item = Product(sku="123", title=" Test ", price=Decimal("0"), reviews_total=0)
    assert item.title == "Test"
    assert item.material is None
    assert item.price == Decimal("0")
    assert item.reviews_total == 0
