from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Numeric,
    UniqueConstraint, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)


class CardBatch(Base):
    __tablename__ = "card_batches"
    id = Column(Integer, primary_key=True, index=True)
    profile = Column(String(120), nullable=False)
    count = Column(Integer, nullable=False)
    owner_username = Column(String(120), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    pdf_path = Column(String(500), nullable=True)


class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("card_batches.id"))
    username = Column(String(120), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    is_printed = Column(Boolean, default=False)
    batch = relationship("CardBatch", backref="cards")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    __table_args__ = (UniqueConstraint("payment_ref", name="uq_registration_payment_ref"),)
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(40), default="monthly", nullable=True)
    price = Column(Integer, default=20, nullable=True)
    currency = Column(String(3), default="USD", nullable=False)
    paid = Column(Boolean, default=False)
    payment_ref = Column(String(160), nullable=True, index=True)
    payment_verified_amount = Column(Numeric(12, 2), nullable=True)
    payment_verified_currency = Column(String(3), nullable=True)
    payment_verified_by = Column(String(120), nullable=True)
    payment_verified_at = Column(DateTime(timezone=True), nullable=True)
    payment_verification_note = Column(String(500), nullable=True)
    registration_token_hash = Column(String(64), nullable=True)
    receipt_image = Column(String(500), nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(40), default="monthly", nullable=True)
    can_reboot_network = Column(Boolean, default=False, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), index=True, nullable=False)
    sender = Column(String(20), nullable=False)
    message = Column(String(2000), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(120), nullable=False)
    performed_by = Column(String(120), nullable=False)
    details = Column(String(2000), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String(120), primary_key=True, index=True)
    value = Column(String(2000), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NetworkObservation(Base):
    __tablename__ = "network_observations"
    id = Column(Integer, primary_key=True, index=True)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    status = Column(String(24), nullable=False)
    router_board = Column(String(160), nullable=True)
    router_version = Column(String(80), nullable=True)
    cpu_load = Column(Integer, nullable=True)
    free_memory_mb = Column(Integer, nullable=True)
    active_users_count = Column(Integer, nullable=True)
    warning = Column(String(500), nullable=True)
    detail = Column(String(1000), nullable=True)


class NetworkActionRequest(Base):
    __tablename__ = "network_action_requests"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(40), nullable=False)
    target = Column(String(160), nullable=True)
    requested_by = Column(String(120), nullable=False)
    reason = Column(String(500), nullable=False)
    status = Column(String(24), default="pending", nullable=False, index=True)
    reviewed_by = Column(String(120), nullable=True)
    review_note = Column(String(500), nullable=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    result = Column(String(1000), nullable=True)


class WalletProvider(Base):
    __tablename__ = "wallet_providers"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    display_name = Column(String(120), nullable=False)
    package_allowlist = Column(Text, nullable=False)
    parser_version = Column(String(64), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)
    auto_verification_enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WalletMonitorDevice(Base):
    __tablename__ = "wallet_monitor_devices"
    id = Column(Integer, primary_key=True, index=True)
    device_uuid = Column(String(64), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    token_hash = Column(String(64), nullable=False)
    status = Column(String(24), default="active", nullable=False, index=True)
    app_version = Column(String(40), nullable=True)
    notification_access_granted = Column(Boolean, default=False, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReceivingWalletAccount(Base):
    __tablename__ = "receiving_wallet_accounts"
    __table_args__ = (
        UniqueConstraint("provider_id", "account_fingerprint", name="uq_receiving_wallet_fingerprint"),
    )
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("wallet_providers.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("wallet_monitor_devices.id"), nullable=False, index=True)
    account_label = Column(String(120), nullable=False)
    account_fingerprint = Column(String(64), nullable=False)
    masked_identifier = Column(String(32), nullable=False)
    currency = Column(String(3), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PayerWalletIdentity(Base):
    __tablename__ = "payer_wallet_identities"
    __table_args__ = (
        UniqueConstraint("provider_id", "phone_fingerprint", name="uq_payer_wallet_fingerprint"),
    )
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    registration_id = Column(Integer, ForeignKey("registration_requests.id"), nullable=True, index=True)
    provider_id = Column(Integer, ForeignKey("wallet_providers.id"), nullable=False, index=True)
    phone_fingerprint = Column(String(64), nullable=False)
    masked_phone = Column(String(32), nullable=False)
    owner_name = Column(String(160), nullable=False)
    status = Column(String(24), default="pending_approval", nullable=False, index=True)
    approved_by = Column(String(120), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WalletPaymentIntent(Base):
    __tablename__ = "wallet_payment_intents"
    __table_args__ = (
        UniqueConstraint("reference_token", name="uq_wallet_payment_intent_reference"),
    )
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    registration_id = Column(Integer, ForeignKey("registration_requests.id"), nullable=True, index=True)
    payer_wallet_id = Column(Integer, ForeignKey("payer_wallet_identities.id"), nullable=False)
    receiving_wallet_id = Column(Integer, ForeignKey("receiving_wallet_accounts.id"), nullable=False)
    intent_type = Column(String(24), nullable=False)
    plan = Column(String(40), nullable=False)
    duration_days = Column(Integer, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    reference_token = Column(String(80), nullable=False)
    status = Column(String(24), default="open", nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WalletNotificationEvent(Base):
    __tablename__ = "wallet_notification_events"
    __table_args__ = (
        UniqueConstraint("device_id", "event_uuid", name="uq_wallet_device_event"),
    )
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("wallet_monitor_devices.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("wallet_providers.id"), nullable=True, index=True)
    event_uuid = Column(String(64), nullable=False)
    package_name = Column(String(200), nullable=False)
    payload_sha256 = Column(String(64), nullable=False)
    parse_status = Column(String(32), default="awaiting_provider_adapter", nullable=False, index=True)
    reason_code = Column(String(64), nullable=True)
    provider_transaction_id = Column(String(160), nullable=True)
    provider_reference = Column(String(160), nullable=True)
    sender_fingerprint = Column(String(64), nullable=True)
    recipient_fingerprint = Column(String(64), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), nullable=True)
    provider_status = Column(String(24), nullable=True)
    intent_id = Column(Integer, ForeignKey("wallet_payment_intents.id"), nullable=True)
    notification_posted_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "receiving_wallet_id", "provider_transaction_id",
            name="uq_wallet_provider_transaction",
        ),
        UniqueConstraint(
            "provider_id", "receiving_wallet_id", "provider_reference",
            name="uq_wallet_provider_reference",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("wallet_providers.id"), nullable=False, index=True)
    receiving_wallet_id = Column(Integer, ForeignKey("receiving_wallet_accounts.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("wallet_notification_events.id"), nullable=True, unique=True)
    intent_id = Column(Integer, ForeignKey("wallet_payment_intents.id"), nullable=True, index=True)
    provider_transaction_id = Column(String(160), nullable=True)
    provider_reference = Column(String(160), nullable=True)
    sender_fingerprint = Column(String(64), nullable=True)
    recipient_fingerprint = Column(String(64), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    provider_status = Column(String(24), nullable=False)
    verification_status = Column(String(32), default="pending_review", nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WalletPaymentReview(Base):
    __tablename__ = "wallet_payment_reviews"
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("wallet_notification_events.id"), nullable=True, unique=True)
    transaction_id = Column(Integer, ForeignKey("wallet_transactions.id"), nullable=True, unique=True)
    reason_code = Column(String(64), nullable=False)
    status = Column(String(24), default="open", nullable=False, index=True)
    decision = Column(String(24), nullable=True)
    reviewed_by = Column(String(120), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    note = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class WalletSubscriptionFulfillment(Base):
    __tablename__ = "wallet_subscription_fulfillments"
    __table_args__ = (
        UniqueConstraint("intent_id", name="uq_wallet_fulfillment_intent"),
        UniqueConstraint("transaction_id", name="uq_wallet_fulfillment_transaction"),
    )
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    intent_id = Column(Integer, ForeignKey("wallet_payment_intents.id"), nullable=False)
    transaction_id = Column(Integer, ForeignKey("wallet_transactions.id"), nullable=False)
    plan = Column(String(40), nullable=False)
    days = Column(Integer, nullable=False)
    previous_expiry = Column(DateTime(timezone=True), nullable=True)
    new_expiry = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(24), default="completed", nullable=False)
    fulfilled_at = Column(DateTime(timezone=True), server_default=func.now())
