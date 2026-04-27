"""add ledgers and idempotency for version 3

Revision ID: 77626a8a5d38
Revises: 332f8447c5b2
Create Date: 2026-04-26 17:22:09.511839

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77626a8a5d38'
down_revision: Union[str, None] = '332f8447c5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Transactions (high-level events)
    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.String, nullable=False),
        sa.Column("transaction_type", sa.String, nullable=False),
        sa.Column("description", sa.String),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now()),
    )

    # Ledger entries (actual balance changes)
    op.create_table(
        "inventory_ledger_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transaction_id", sa.Integer, sa.ForeignKey("inventory_transactions.id")),
        sa.Column("resource_type", sa.String, nullable=False),  # gold, red_ml, potion, etc
        sa.Column("resource_id", sa.Integer, nullable=True),    # for potions
        sa.Column("change", sa.Integer, nullable=False),
    )

    # Idempotency table
    op.create_table(
        "processed_requests",
        sa.Column("request_key", sa.String, primary_key=True),
        sa.Column("endpoint", sa.String),
        sa.Column("response", sa.JSON),
    )

    # Sales metadata (for V3 requirement)
    op.create_table(
        "sales",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cart_id", sa.Integer),
        sa.Column("customer_id", sa.String),
        sa.Column("customer_name", sa.String),
        sa.Column("character_class", sa.String),
        sa.Column("character_species", sa.String),
        sa.Column("level", sa.Integer),
        sa.Column("day", sa.String),
        sa.Column("hour", sa.Integer),
    )

    op.execute(
    sa.text(
        """
        INSERT INTO inventory_transactions (order_id, transaction_type, description)
        VALUES ('initial_state', 'initial_state', 'Starting inventory')
        """
    )
    )

    op.execute(
    sa.text(
        """
        INSERT INTO inventory_ledger_entries (transaction_id, resource_type, resource_id, change)
        SELECT id, 'gold', NULL, 100
        FROM inventory_transactions
        WHERE order_id = 'initial_state'
        """
    )
    )


def downgrade() -> None:
    op.drop_table("sales")
    op.drop_table("processed_requests")
    op.drop_table("inventory_ledger_entries")
    op.drop_table("inventory_transactions")
