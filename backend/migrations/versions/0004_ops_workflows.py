"""Add monitoring, network approval and verified manual payment metadata.

Revision ID: 0004_ops_workflows
Revises: 0003_card_batch_owner
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_ops_workflows"
down_revision = "0003_card_batch_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "registration_requests" in tables:
        columns = {column["name"] for column in inspector.get_columns("registration_requests")}
        additions = [
            ("currency", sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD")),
            ("payment_verified_amount", sa.Column("payment_verified_amount", sa.Numeric(12, 2), nullable=True)),
            ("payment_verified_currency", sa.Column("payment_verified_currency", sa.String(length=3), nullable=True)),
            ("payment_verified_by", sa.Column("payment_verified_by", sa.String(length=120), nullable=True)),
            ("payment_verified_at", sa.Column("payment_verified_at", sa.DateTime(timezone=True), nullable=True)),
            ("payment_verification_note", sa.Column("payment_verification_note", sa.String(length=500), nullable=True)),
        ]
        for name, column in additions:
            if name not in columns:
                op.add_column("registration_requests", column)

        inspector = sa.inspect(bind)
        indexes = {item["name"] for item in inspector.get_indexes("registration_requests")}
        constraints = {
            item.get("name") for item in inspector.get_unique_constraints("registration_requests")
        }
        if "uq_registration_payment_ref" not in indexes | constraints:
            duplicates = bind.execute(
                sa.text(
                    "SELECT payment_ref, COUNT(*) AS total FROM registration_requests "
                    "WHERE payment_ref IS NOT NULL GROUP BY payment_ref HAVING COUNT(*) > 1 LIMIT 10"
                )
            ).fetchall()
            if duplicates:
                raise RuntimeError(
                    "Cannot enforce unique payment references. Resolve existing duplicate payment_ref "
                    f"values before continuing: {duplicates}"
                )
            op.create_index(
                "uq_registration_payment_ref",
                "registration_requests",
                ["payment_ref"],
                unique=True,
            )

    tables = set(sa.inspect(bind).get_table_names())
    if "network_observations" not in tables:
        op.create_table(
            "network_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("router_board", sa.String(length=160), nullable=True),
            sa.Column("router_version", sa.String(length=80), nullable=True),
            sa.Column("cpu_load", sa.Integer(), nullable=True),
            sa.Column("free_memory_mb", sa.Integer(), nullable=True),
            sa.Column("active_users_count", sa.Integer(), nullable=True),
            sa.Column("warning", sa.String(length=500), nullable=True),
            sa.Column("detail", sa.String(length=1000), nullable=True),
        )
        op.create_index("ix_network_observations_observed_at", "network_observations", ["observed_at"])

    tables = set(sa.inspect(bind).get_table_names())
    if "network_action_requests" not in tables:
        op.create_table(
            "network_action_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column("target", sa.String(length=160), nullable=True),
            sa.Column("requested_by", sa.String(length=120), nullable=False),
            sa.Column("reason", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.String(length=120), nullable=True),
            sa.Column("review_note", sa.String(length=500), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", sa.String(length=1000), nullable=True),
        )
        op.create_index("ix_network_action_requests_status", "network_action_requests", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "network_action_requests" in tables:
        op.drop_index("ix_network_action_requests_status", table_name="network_action_requests")
        op.drop_table("network_action_requests")
    if "network_observations" in tables:
        op.drop_index("ix_network_observations_observed_at", table_name="network_observations")
        op.drop_table("network_observations")
    if "registration_requests" in tables:
        inspector = sa.inspect(bind)
        indexes = {item["name"] for item in inspector.get_indexes("registration_requests")}
        constraints = {
            item.get("name") for item in inspector.get_unique_constraints("registration_requests")
        }
        if "uq_registration_payment_ref" in indexes | constraints:
            op.drop_index("uq_registration_payment_ref", table_name="registration_requests")
        columns = {column["name"] for column in sa.inspect(bind).get_columns("registration_requests")}
        for name in (
            "payment_verification_note",
            "payment_verified_at",
            "payment_verified_by",
            "payment_verified_currency",
            "payment_verified_amount",
            "currency",
        ):
            if name in columns:
                op.drop_column("registration_requests", name)
