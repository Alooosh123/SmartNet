from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)


class CardBatch(Base):
    __tablename__ = "card_batches"
    id = Column(Integer, primary_key=True, index=True)
    profile = Column(String, nullable=False)
    count = Column(Integer, nullable=False)
    owner_username = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    pdf_path = Column(String, nullable=True)


class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("card_batches.id"))
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    is_printed = Column(Boolean, default=False)
    batch = relationship("CardBatch", backref="cards")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    __table_args__ = (UniqueConstraint("payment_ref", name="uq_registration_payment_ref"),)
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    plan = Column(String, default="monthly", nullable=True)
    price = Column(Integer, default=20, nullable=True)
    currency = Column(String(3), default="USD", nullable=False)
    paid = Column(Boolean, default=False)
    payment_ref = Column(String, nullable=True, index=True)
    payment_verified_amount = Column(Numeric(12, 2), nullable=True)
    payment_verified_currency = Column(String(3), nullable=True)
    payment_verified_by = Column(String, nullable=True)
    payment_verified_at = Column(DateTime(timezone=True), nullable=True)
    payment_verification_note = Column(String(500), nullable=True)
    registration_token_hash = Column(String, nullable=True)
    receipt_image = Column(String, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    plan = Column(String, default="monthly", nullable=True)
    can_reboot_network = Column(Boolean, default=False, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    sender = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)
    performed_by = Column(String, nullable=False)
    details = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
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
