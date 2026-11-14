"""Add Android wallet notification monitoring and payment intent records.

Revision ID: 0005_wallet_monitoring
Revises: 0004_ops_workflows
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_wallet_monitoring"
down_revision = "0004_ops_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("package_allowlist", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_verification_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_wallet_providers_code"),
    )
    op.create_index("ix_wallet_providers_id", "wallet_providers", ["id"])
    op.create_index("ix_wallet_providers_code", "wallet_providers", ["code"])

    op.create_table(
        "wallet_monitor_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_uuid", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("app_version", sa.String(length=40), nullable=True),
        sa.Column("notification_access_granted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("device_uuid", name="uq_wallet_monitor_device_uuid"),
    )
    op.create_index("ix_wallet_monitor_devices_id", "wallet_monitor_devices", ["id"])
    op.create_index("ix_wallet_monitor_devices_status", "wallet_monitor_devices", ["status"])

    op.create_table(
        "receiving_wallet_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("wallet_providers.id"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("wallet_monitor_devices.id"), nullable=False),
        sa.Column("account_label", sa.String(length=120), nullable=False),
        sa.Column("account_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("masked_identifier", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "account_fingerprint", name="uq_receiving_wallet_fingerprint"),
    )
    op.create_index("ix_receiving_wallet_accounts_id", "receiving_wallet_accounts", ["id"])
    op.create_index("ix_receiving_wallet_accounts_provider_id", "receiving_wallet_accounts", ["provider_id"])
    op.create_index("ix_receiving_wallet_accounts_device_id", "receiving_wallet_accounts", ["device_id"])

    op.create_table(
        "payer_wallet_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("wallet_providers.id"), nullable=False),
        sa.Column("phone_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("masked_phone", sa.String(length=32), nullable=False),
        sa.Column("owner_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_approval"),
        sa.Column("approved_by", sa.String(length=120), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "phone_fingerprint", name="uq_payer_wallet_fingerprint"),
    )
    op.create_index("ix_payer_wallet_identities_id", "payer_wallet_identities", ["id"])
    op.create_index("ix_payer_wallet_identities_client_id", "payer_wallet_identities", ["client_id"])
    op.create_index("ix_payer_wallet_identities_registration_id", "payer_wallet_identities", ["registration_id"])
    op.create_index("ix_payer_wallet_identities_provider_id", "payer_wallet_identities", ["provider_id"])
    op.create_index("ix_payer_wallet_identities_status", "payer_wallet_identities", ["status"])

    op.create_table(
        "wallet_payment_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=True),
        sa.Column("payer_wallet_id", sa.Integer(), sa.ForeignKey("payer_wallet_identities.id"), nullable=False),
        sa.Column("receiving_wallet_id", sa.Integer(), sa.ForeignKey("receiving_wallet_accounts.id"), nullable=False),
        sa.Column("intent_type", sa.String(length=24), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("reference_token", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("reference_token", name="uq_wallet_payment_intent_reference"),
    )
    op.create_index("ix_wallet_payment_intents_id", "wallet_payment_intents", ["id"])
    op.create_index("ix_wallet_payment_intents_client_id", "wallet_payment_intents", ["client_id"])
    op.create_index("ix_wallet_payment_intents_registration_id", "wallet_payment_intents", ["registration_id"])
    op.create_index("ix_wallet_payment_intents_status", "wallet_payment_intents", ["status"])

    op.create_table(
        "wallet_notification_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("wallet_monitor_devices.id"), nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("wallet_providers.id"), nullable=True),
        sa.Column("event_uuid", sa.String(length=64), nullable=False),
        sa.Column("package_name", sa.String(length=200), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="awaiting_provider_adapter"),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=160), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("sender_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("recipient_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("provider_status", sa.String(length=24), nullable=True),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("wallet_payment_intents.id"), nullable=True),
        sa.Column("notification_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("device_id", "event_uuid", name="uq_wallet_device_event"),
    )
    op.create_index("ix_wallet_notification_events_id", "wallet_notification_events", ["id"])
    op.create_index("ix_wallet_notification_events_device_id", "wallet_notification_events", ["device_id"])
    op.create_index("ix_wallet_notification_events_provider_id", "wallet_notification_events", ["provider_id"])
    op.create_index("ix_wallet_notification_events_parse_status", "wallet_notification_events", ["parse_status"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("wallet_providers.id"), nullable=False),
        sa.Column("receiving_wallet_id", sa.Integer(), sa.ForeignKey("receiving_wallet_accounts.id"), nullable=False),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("wallet_notification_events.id"), nullable=True),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("wallet_payment_intents.id"), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=160), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("sender_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("recipient_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider_status", sa.String(length=24), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider_id", "receiving_wallet_id", "provider_transaction_id", name="uq_wallet_provider_transaction"),
        sa.UniqueConstraint("provider_id", "receiving_wallet_id", "provider_reference", name="uq_wallet_provider_reference"),
        sa.UniqueConstraint("event_id", name="uq_wallet_transaction_event"),
    )
    op.create_index("ix_wallet_transactions_id", "wallet_transactions", ["id"])
    op.create_index("ix_wallet_transactions_provider_id", "wallet_transactions", ["provider_id"])
    op.create_index("ix_wallet_transactions_intent_id", "wallet_transactions", ["intent_id"])
    op.create_index("ix_wallet_transactions_verification_status", "wallet_transactions", ["verification_status"])

    op.create_table(
        "wallet_payment_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("wallet_notification_events.id"), nullable=True),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("wallet_transactions.id"), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("decision", sa.String(length=24), nullable=True),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", name="uq_wallet_review_event"),
        sa.UniqueConstraint("transaction_id", name="uq_wallet_review_transaction"),
    )
    op.create_index("ix_wallet_payment_reviews_id", "wallet_payment_reviews", ["id"])
    op.create_index("ix_wallet_payment_reviews_status", "wallet_payment_reviews", ["status"])

    op.create_table(
        "wallet_subscription_fulfillments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("wallet_payment_intents.id"), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("wallet_transactions.id"), nullable=False),
        sa.Column("plan", sa.String(length=40), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("previous_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="completed"),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("intent_id", name="uq_wallet_fulfillment_intent"),
        sa.UniqueConstraint("transaction_id", name="uq_wallet_fulfillment_transaction"),
    )
    op.create_index("ix_wallet_subscription_fulfillments_id", "wallet_subscription_fulfillments", ["id"])
    op.create_index("ix_wallet_subscription_fulfillments_client_id", "wallet_subscription_fulfillments", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_wallet_subscription_fulfillments_client_id", table_name="wallet_subscription_fulfillments")
    op.drop_index("ix_wallet_subscription_fulfillments_id", table_name="wallet_subscription_fulfillments")
    op.drop_table("wallet_subscription_fulfillments")
    op.drop_index("ix_wallet_payment_reviews_status", table_name="wallet_payment_reviews")
    op.drop_index("ix_wallet_payment_reviews_id", table_name="wallet_payment_reviews")
    op.drop_table("wallet_payment_reviews")
    op.drop_index("ix_wallet_transactions_verification_status", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_intent_id", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_provider_id", table_name="wallet_transactions")
    op.drop_index("ix_wallet_transactions_id", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
    op.drop_index("ix_wallet_notification_events_parse_status", table_name="wallet_notification_events")
    op.drop_index("ix_wallet_notification_events_provider_id", table_name="wallet_notification_events")
    op.drop_index("ix_wallet_notification_events_device_id", table_name="wallet_notification_events")
    op.drop_index("ix_wallet_notification_events_id", table_name="wallet_notification_events")
    op.drop_table("wallet_notification_events")
    op.drop_index("ix_wallet_payment_intents_status", table_name="wallet_payment_intents")
    op.drop_index("ix_wallet_payment_intents_registration_id", table_name="wallet_payment_intents")
    op.drop_index("ix_wallet_payment_intents_client_id", table_name="wallet_payment_intents")
    op.drop_index("ix_wallet_payment_intents_id", table_name="wallet_payment_intents")
    op.drop_table("wallet_payment_intents")
    op.drop_index("ix_payer_wallet_identities_status", table_name="payer_wallet_identities")
    op.drop_index("ix_payer_wallet_identities_provider_id", table_name="payer_wallet_identities")
    op.drop_index("ix_payer_wallet_identities_registration_id", table_name="payer_wallet_identities")
    op.drop_index("ix_payer_wallet_identities_client_id", table_name="payer_wallet_identities")
    op.drop_index("ix_payer_wallet_identities_id", table_name="payer_wallet_identities")
    op.drop_table("payer_wallet_identities")
    op.drop_index("ix_receiving_wallet_accounts_device_id", table_name="receiving_wallet_accounts")
    op.drop_index("ix_receiving_wallet_accounts_provider_id", table_name="receiving_wallet_accounts")
    op.drop_index("ix_receiving_wallet_accounts_id", table_name="receiving_wallet_accounts")
    op.drop_table("receiving_wallet_accounts")
    op.drop_index("ix_wallet_monitor_devices_status", table_name="wallet_monitor_devices")
    op.drop_index("ix_wallet_monitor_devices_id", table_name="wallet_monitor_devices")
    op.drop_table("wallet_monitor_devices")
    op.drop_index("ix_wallet_providers_code", table_name="wallet_providers")
    op.drop_index("ix_wallet_providers_id", table_name="wallet_providers")
    op.drop_table("wallet_providers")
