"""Validated product data shared by extractors and persistence adapters."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Product:
    sku: str
    title: str
    price: Decimal | None = None
    rating: Decimal | None = None
    reviews_total: int | None = None
    cover_image: str | None = None
    photos_seller: int | None = None
    videos_seller: int | None = None
    color: str | None = None
    material: str | None = None
    art_set: str | None = None
    has_rich_content: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.sku, str) or not self.sku.isascii() or not self.sku.isdecimal():
            raise ValueError("SKU must contain ASCII digits")
        if len(self.sku) > 64:
            raise ValueError("SKU exceeds database length")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Product title must not be empty")
        object.__setattr__(self, "title", self.title.strip())
        for name, maximum in (("price", Decimal("9999999999.99")), ("rating", Decimal("5"))):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or not Decimal("0") <= value <= maximum
                or value != value.quantize(Decimal("0.01"))
            ):
                raise ValueError(f"{name} must be a finite Decimal within range with <=2 decimals")
        for name in ("reviews_total", "photos_seller", "videos_seller"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 0 <= value <= 2147483647):
                raise ValueError(f"{name} must be a nonnegative PostgreSQL integer")
        if type(self.has_rich_content) is not bool:
            raise ValueError("has_rich_content must be boolean")
