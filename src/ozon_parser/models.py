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
