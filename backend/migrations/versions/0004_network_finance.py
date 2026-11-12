"""Add payment verification, network monitoring and operation approval tables.

Revision ID: 0004_network_finance
Revises: 0003_card_batch_owner
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_network_finance"
down_revision = "0003_card_batch_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "registration_requests" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("registration_requests")}
        if "currency" not in columns:
            op.add_column("registration_requests", sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"))

    tables = set(sa.inspect(bind).get_table_names())
    if "payment_verifications" not in tables:
        op.create_table(
            "payment_verifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=False, unique=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("external_reference", sa.String(length=160), nullable=False, unique=True),
            sa.Column("verified_by", sa.String(length=120), nullable=False),
            sa.Column("notes", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_payment_verifications_external_reference", "payment_verifications", ["external_reference"], unique=True)

    if "network_snapshots" not in tables:
        op.create_table(
            "network_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cpu_load", sa.Integer(), nullable=True),
            sa.Column("free_memory", sa.BigInteger(), nullable=True),
            sa.Column("total_memory", sa.BigInteger(), nullable=True),
            sa.Column("active_users", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("router_uptime", sa.String(length=80), nullable=True),
            sa.Column("router_version", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_network_snapshots_created_at", "network_snapshots", ["created_at"])

    if "network_alerts" not in tables:
        op.create_table(
            "network_alerts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("message", sa.String(length=500), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_network_alerts_code", "network_alerts", ["code"])
        op.create_index("ix_network_alerts_active", "network_alerts", ["active"])
        op.create_index("ix_network_alerts_active_created", "network_alerts", ["active", "created_at"])

    if "network_operations" not in tables:
        op.create_table(
            "network_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column("target", sa.String(length=160), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("requested_by", sa.String(length=120), nullable=False),
            sa.Column("reviewed_by", sa.String(length=120), nullable=True),
            sa.Column("executed_by", sa.String(length=120), nullable=True),
            sa.Column("idempotency_key", sa.String(length=80), nullable=False, unique=True),
            sa.Column("review_note", sa.String(length=500), nullable=True),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_network_operations_status", "network_operations", ["status"])
        op.create_index("ix_network_operations_requested_by", "network_operations", ["requested_by"])
        op.create_index("ix_network_operations_idempotency_key", "network_operations", ["idempotency_key"], unique=True)


def downgrade() -> None:
    op.drop_table("network_operations")
    op.drop_table("network_alerts")
    op.drop_table("network_snapshots")
    op.drop_table("payment_verifications")
    with op.batch_alter_table("registration_requests") as batch:
        batch.drop_column("currency")
