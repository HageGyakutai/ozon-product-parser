"""Exercise the migrated PostgreSQL schema in isolated savepoint transactions."""

import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from ozon_parser.models import Product
from ozon_parser.storage import ProductRow, save_product


@pytest.fixture(scope="session")
def test_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must point to a PostgreSQL database ending in _test")
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    with patch.dict(os.environ, {"DATABASE_URL": url}):
        command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(test_engine):
    with test_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
        finally:
            transaction.rollback()


def product(**changes):
    return replace(Product(sku="123", title="Original", price=Decimal("19.99")), **changes)


def row(db):
    return db.scalar(select(ProductRow).where(ProductRow.sku == "123"))


def test_migration_applied(db):
    assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0001"


def test_insert(db):
    save_product(db, product())
    saved = row(db)
    assert saved.id is not None
    assert saved.title == "Original"
    assert saved.created_at.tzinfo is not None
    assert saved.updated_at.tzinfo is not None


def test_same_sku_no_duplicates(db):
    save_product(db, product())
    saved_id = row(db).id
    save_product(db, product(title="Updated"))
    assert (
        db.scalar(select(func.count()).select_from(ProductRow).where(ProductRow.sku == "123")) == 1
    )
    assert row(db).id == saved_id
    assert row(db).title == "Updated"


def test_price_and_decimal(db):
    save_product(db, product(price=Decimal("0.10")))
    assert row(db).price == Decimal("0.10")
    save_product(db, product(price=Decimal("1234567.89")))
    assert row(db).price == Decimal("1234567.89")
    assert isinstance(row(db).price, Decimal)


def test_rating_and_reviews(db):
    save_product(db, product(rating=Decimal("4.20"), reviews_total=2))
    save_product(db, product(rating=Decimal("4.80"), reviews_total=5))
    assert row(db).rating == Decimal("4.80")
    assert row(db).reviews_total == 5


def test_nullable_characteristics(db):
    save_product(db, product(color="Red", material="Cotton", art_set="A1"))
    save_product(db, product())
    saved = row(db)
    assert saved.color is saved.material is saved.art_set is None


def test_rich_content(db):
    save_product(db, product(has_rich_content=True))
    assert row(db).has_rich_content is True
    save_product(db, product(has_rich_content=False))
    assert row(db).has_rich_content is False


def test_media_counts(db):
    save_product(db, product(photos_seller=4, videos_seller=0))
    assert row(db).photos_seller == 4
    assert row(db).videos_seller == 0


def test_created_at_preserved(db):
    save_product(db, product())
    created = row(db).created_at
    save_product(db, product(title="Updated"))
    assert row(db).created_at == created
    assert row(db).updated_at >= created


def test_rollback_allows_next_product(db):
    # Force a database-level error to verify session recovery after failed persistence.
    broken = product()
    object.__setattr__(broken, "title", None)
    with pytest.raises(IntegrityError):
        save_product(db, broken)
    save_product(db, product())
    assert row(db).title == "Original"
