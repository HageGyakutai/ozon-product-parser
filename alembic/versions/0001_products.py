"""Create products table.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("rating", sa.Numeric(3, 2)),
        sa.Column("reviews_total", sa.Integer()),
        sa.Column("cover_image", sa.Text()),
        sa.Column("photos_seller", sa.Integer()),
        sa.Column("videos_seller", sa.Integer()),
        sa.Column("color", sa.Text()),
        sa.Column("material", sa.Text()),
        sa.Column("art_set", sa.Text()),
        sa.Column("has_rich_content", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)


def downgrade():
    op.drop_index("ix_products_sku", "products")
    op.drop_table("products")
