"""Expand existing chat and audit detail columns to TEXT.

Revision ID: 0005_text_columns
Revises: 0004_network_finance
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_text_columns"
down_revision = "0004_network_finance"
branch_labels = None
depends_on = None


def _ensure_text(table: str, column: str, nullable: bool) -> None:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return
    columns = {item["name"]: item for item in inspector.get_columns(table)}
    existing = columns.get(column)
    if existing is None or isinstance(existing["type"], sa.Text):
        return
    with op.batch_alter_table(table) as batch:
        batch.alter_column(
            column,
            existing_type=existing["type"],
            type_=sa.Text(),
            existing_nullable=nullable,
        )


def upgrade() -> None:
    _ensure_text("chat_messages", "message", nullable=False)
    _ensure_text("audit_logs", "details", nullable=True)


def downgrade() -> None:
    # Do not truncate operational histories or customer messages on downgrade.
    pass
