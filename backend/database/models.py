from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, Boolean, ForeignKey,
    Numeric, JSON, Text, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)


class CardBatch(Base):
    __tablename__ = "card_batches"
    id = Column(Integer, primary_key=True, index=True)
    profile = Column(String(255), nullable=False)
    count = Column(Integer, nullable=False)
    owner_username = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    pdf_path = Column(String(255), nullable=True)


class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("card_batches.id"))
    username = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    is_printed = Column(Boolean, default=False)
    batch = relationship("CardBatch", backref="cards")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(255), default="monthly", nullable=True)
    price = Column(Integer, default=20, nullable=True)
    currency = Column(String(3), default="USD", nullable=False)
    paid = Column(Boolean, default=False)
    payment_ref = Column(String(255), nullable=True, index=True)
    registration_token_hash = Column(String(255), nullable=True)
    receipt_image = Column(String(255), nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentVerification(Base):
    __tablename__ = "payment_verifications"
    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("registration_requests.id"), nullable=False, unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    external_reference = Column(String(160), nullable=False, unique=True, index=True)
    verified_by = Column(String(120), nullable=False)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(255), default="monthly", nullable=True)
    can_reboot_network = Column(Boolean, default=False, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), index=True, nullable=False)
    sender = Column(String(255), nullable=False)
    message = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(255), nullable=False)
    performed_by = Column(String(255), nullable=False)
    details = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String(255), primary_key=True, index=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NetworkSnapshot(Base):
    __tablename__ = "network_snapshots"
    id = Column(Integer, primary_key=True, index=True)
    cpu_load = Column(Integer, nullable=True)
    free_memory = Column(BigInteger, nullable=True)
    total_memory = Column(BigInteger, nullable=True)
    active_users = Column(Integer, nullable=False, default=0)
    router_uptime = Column(String(80), nullable=True)
    router_version = Column(String(80), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NetworkAlert(Base):
    __tablename__ = "network_alerts"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="warning")
    message = Column(String(500), nullable=False)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class NetworkOperation(Base):
    __tablename__ = "network_operations"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(40), nullable=False)
    target = Column(String(160), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), nullable=False, default="pending", index=True)
    requested_by = Column(String(120), nullable=False, index=True)
    reviewed_by = Column(String(120), nullable=True)
    executed_by = Column(String(120), nullable=True)
    idempotency_key = Column(String(80), nullable=False, unique=True, index=True)
    review_note = Column(String(500), nullable=True)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)


Index("ix_network_snapshots_created_at", NetworkSnapshot.created_at)
Index("ix_network_alerts_active_created", NetworkAlert.active, NetworkAlert.created_at)
