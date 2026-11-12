"""Operational workflow, telemetry and manual-payment audit tables."""
from alembic import op
import sqlalchemy as sa

revision = "0004_operations_agents"
down_revision = "0003_card_batch_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "manual_payments" not in tables:
        op.create_table(
            "manual_payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=False),
            sa.Column("payment_method", sa.String(length=32), nullable=False),
            sa.Column("reference", sa.String(length=128), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("verified_by", sa.String(length=128), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("registration_id", name="uq_manual_payment_registration"),
            sa.UniqueConstraint("reference", name="uq_manual_payment_reference"),
        )

    if "network_action_requests" not in tables:
        op.create_table(
            "network_action_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action_type", sa.String(length=24), nullable=False),
            sa.Column("target_user", sa.String(length=128), nullable=True),
            sa.Column("requested_by", sa.String(length=128), nullable=False),
            sa.Column("requested_role", sa.String(length=24), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("approved_by", sa.String(length=128), nullable=True),
            sa.Column("approval_note", sa.Text(), nullable=True),
            sa.Column("result_summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_network_action_requests_requested_by", "network_action_requests", ["requested_by"])
        op.create_index("ix_network_action_requests_status", "network_action_requests", ["status"])

    if "network_metrics" not in tables:
        op.create_table(
            "network_metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("board_name", sa.String(length=128), nullable=True),
            sa.Column("uptime", sa.String(length=128), nullable=True),
            sa.Column("cpu_load", sa.Integer(), nullable=True),
            sa.Column("free_memory_bytes", sa.BigInteger(), nullable=True),
            sa.Column("total_memory_bytes", sa.BigInteger(), nullable=True),
            sa.Column("active_users_count", sa.Integer(), nullable=True),
            sa.Column("alert_summary", sa.Text(), nullable=True),
        )
        op.create_index("ix_network_metrics_observed_at", "network_metrics", ["observed_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "network_metrics" in tables:
        indexes = {item["name"] for item in inspector.get_indexes("network_metrics")}
        if "ix_network_metrics_observed_at" in indexes:
            op.drop_index("ix_network_metrics_observed_at", table_name="network_metrics")
        op.drop_table("network_metrics")
    if "network_action_requests" in tables:
        indexes = {item["name"] for item in inspector.get_indexes("network_action_requests")}
        for index_name in ("ix_network_action_requests_status", "ix_network_action_requests_requested_by"):
            if index_name in indexes:
                op.drop_index(index_name, table_name="network_action_requests")
        op.drop_table("network_action_requests")
    if "manual_payments" in tables:
        op.drop_table("manual_payments")
