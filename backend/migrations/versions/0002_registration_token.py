"""Add private registration token hash to existing installations.

Revision ID: 0002_registration_token
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_registration_token"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "registration_requests" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("registration_requests")}
        if "registration_token_hash" not in columns:
            op.add_column("registration_requests", sa.Column("registration_token_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "registration_requests" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("registration_requests")}
        if "registration_token_hash" in columns:
            op.drop_column("registration_requests", "registration_token_hash")
