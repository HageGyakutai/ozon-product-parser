import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, create_engine, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import Product


class Base(DeclarativeBase):
    pass


class ProductRow(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    reviews_total: Mapped[int | None] = mapped_column(Integer)
    cover_image: Mapped[str | None] = mapped_column(Text)
    photos_seller: Mapped[int | None] = mapped_column(Integer)
    videos_seller: Mapped[int | None] = mapped_column(Integer)
    color: Mapped[str | None] = mapped_column(Text)
    material: Mapped[str | None] = mapped_column(Text)
    art_set: Mapped[str | None] = mapped_column(Text)
    has_rich_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def database_engine():
    url = os.getenv("DATABASE_URL")
    if not url or not url.startswith("postgresql+psycopg://"):
        raise ValueError("Set DATABASE_URL to a postgresql+psycopg:// URL")
    return create_engine(url, pool_pre_ping=True)


def save_product(session: Session, product: Product) -> None:
    values = vars(product)
    statement = insert(ProductRow).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[ProductRow.sku],
        set_={
            **{key: statement.excluded[key] for key in values if key != "sku"},
            "updated_at": func.now(),
        },
    )
    try:
        session.execute(statement)
        session.commit()
    except Exception:
        session.rollback()
        raise
