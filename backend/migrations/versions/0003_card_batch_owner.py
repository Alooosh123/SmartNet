"""Associate every generated Hotspot card batch with its creator.

Revision ID: 0003_card_batch_owner
Revises: 0002_registration_token
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_card_batch_owner"
down_revision = "0002_registration_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "card_batches" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("card_batches")}
    if "owner_username" not in columns:
        op.add_column("card_batches", sa.Column("owner_username", sa.String(length=120), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("card_batches")}
    if "ix_card_batches_owner_username" not in indexes:
        op.create_index("ix_card_batches_owner_username", "card_batches", ["owner_username"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "card_batches" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("card_batches")}
    if "ix_card_batches_owner_username" in indexes:
        op.drop_index("ix_card_batches_owner_username", table_name="card_batches")
    columns = {column["name"] for column in inspector.get_columns("card_batches")}
    if "owner_username" in columns:
        op.drop_column("card_batches", "owner_username")
