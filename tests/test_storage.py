import os
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from ozon_parser.models import Product
from ozon_parser.storage import Base, ProductRow, save_product


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_insert_and_upsert(db):
    save_product(
        db,
        Product(
            sku="test-1",
            title="Original",
            price=Decimal("19.99"),
            rating=Decimal("4.20"),
            reviews_total=2,
            has_rich_content=False,
        ),
    )
    save_product(
        db,
        Product(
            sku="test-1",
            title="Updated",
            price=Decimal("21.33"),
            rating=Decimal("4.80"),
            reviews_total=5,
            has_rich_content=True,
        ),
    )
    row = db.scalar(select(ProductRow).where(ProductRow.sku == "test-1"))
    assert db.scalar(select(func.count()).select_from(ProductRow)) == 1
    assert row.title == "Updated"
    assert row.price == Decimal("21.33")
    assert row.rating == Decimal("4.80")
    assert row.reviews_total == 5
    assert row.material is None
    assert row.has_rich_content is True
