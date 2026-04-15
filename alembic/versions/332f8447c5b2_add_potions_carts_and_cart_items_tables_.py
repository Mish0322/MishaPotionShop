"""add potions carts and cart_items tables for version 2

Revision ID: 332f8447c5b2
Revises: 5f9f27c5c11e
Create Date: 2026-04-14 20:33:11.633014

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '332f8447c5b2'
down_revision: Union[str, None] = '5f9f27c5c11e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "potions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("red", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("green", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dark", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inventory", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("price >= 0", name="ck_potions_price_non_negative"),
        sa.CheckConstraint("red >= 0", name="ck_potions_red_non_negative"),
        sa.CheckConstraint("green >= 0", name="ck_potions_green_non_negative"),
        sa.CheckConstraint("blue >= 0", name="ck_potions_blue_non_negative"),
        sa.CheckConstraint("dark >= 0", name="ck_potions_dark_non_negative"),
        sa.CheckConstraint("inventory >= 0", name="ck_potions_inventory_non_negative"),
    )

    op.create_table(
        "carts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(), nullable=False),
        sa.Column("character_class", sa.String(), nullable=False),
        sa.Column("character_species", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
    )

    op.create_table(
        "cart_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cart_id", sa.Integer(), sa.ForeignKey("carts.id"), nullable=False),
        sa.Column("potion_id", sa.Integer(), sa.ForeignKey("potions.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("quantity > 0", name="ck_cart_items_quantity_positive"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO potions (sku, name, price, red, green, blue, dark, inventory)
            VALUES
                ('RED_POTION', 'red potion', 50, 100, 0, 0, 0, 0),
                ('GREEN_POTION', 'green potion', 50, 0, 100, 0, 0, 0),
                ('BLUE_POTION', 'blue potion', 50, 0, 0, 100, 0, 0),
                ('PURPLE_POTION', 'purple potion', 60, 50, 0, 50, 0, 0)
            """
        )
    )


def downgrade():
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("potions")