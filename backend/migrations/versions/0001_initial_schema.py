"""Historical SmartNet schema before registration tokens, card ownership and agents.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep this revision immutable in meaning: only the original tables/columns
    # belong here. Later revisions add registration_token_hash, owner_username,
    # currency and agent/finance tables in their proper order.
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_admins_username", "admins", ["username"], unique=True)

    op.create_table(
        "card_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile", sa.String(length=255), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("pdf_path", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("card_batches.id"), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("is_printed", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_cards_username", "cards", ["username"], unique=True)

    op.create_table(
        "registration_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=255), nullable=True, server_default="monthly"),
        sa.Column("price", sa.Integer(), nullable=True, server_default="20"),
        sa.Column("paid", sa.Boolean(), nullable=True),
        sa.Column("payment_ref", sa.String(length=255), nullable=True),
        sa.Column("receipt_image", sa.String(length=255), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_registration_requests_username", "registration_requests", ["username"], unique=True)
    op.create_index("ix_registration_requests_payment_ref", "registration_requests", ["payment_ref"], unique=False)

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=255), nullable=True, server_default="monthly"),
        sa.Column("can_reboot_network", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("subscription_expires", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clients_username", "clients", ["username"], unique=True)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("sender", sa.String(length=255), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_username", "chat_messages", ["username"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("performed_by", sa.String(length=255), nullable=False),
        sa.Column("details", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_table("audit_logs")
    op.drop_index("ix_chat_messages_username", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_clients_username", table_name="clients")
    op.drop_table("clients")
    op.drop_index("ix_registration_requests_payment_ref", table_name="registration_requests")
    op.drop_index("ix_registration_requests_username", table_name="registration_requests")
    op.drop_table("registration_requests")
    op.drop_index("ix_cards_username", table_name="cards")
    op.drop_table("cards")
    op.drop_table("card_batches")
    op.drop_index("ix_admins_username", table_name="admins")
    op.drop_table("admins")
