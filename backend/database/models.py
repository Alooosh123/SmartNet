from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, BigInteger, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)


class CardBatch(Base):
    __tablename__ = "card_batches"
    id = Column(Integer, primary_key=True, index=True)
    profile = Column(String(128), nullable=False)
    count = Column(Integer, nullable=False)
    owner_username = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    pdf_path = Column(String(512), nullable=True)


class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("card_batches.id"))
    username = Column(String(128), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    is_printed = Column(Boolean, default=False)
    batch = relationship("CardBatch", backref="cards")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(32), default="monthly", nullable=True)
    price = Column(Integer, default=20, nullable=True)
    paid = Column(Boolean, default=False)
    payment_ref = Column(String(128), nullable=True, index=True)
    registration_token_hash = Column(String(64), nullable=True)
    receipt_image = Column(String(512), nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    plan = Column(String(32), default="monthly", nullable=True)
    can_reboot_network = Column(Boolean, default=False, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(128), index=True, nullable=False)
    sender = Column(String(16), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(128), nullable=False)
    performed_by = Column(String(128), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String(255), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ManualPayment(Base):
    __tablename__ = "manual_payments"
    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("registration_requests.id"), nullable=False, unique=True)
    payment_method = Column(String(32), nullable=False)
    reference = Column(String(128), nullable=False, unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    notes = Column(Text, nullable=True)
    verified_by = Column(String(128), nullable=False)
    verified_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NetworkActionRequest(Base):
    __tablename__ = "network_action_requests"
    id = Column(Integer, primary_key=True, index=True)
    action_type = Column(String(24), nullable=False)
    target_user = Column(String(128), nullable=True)
    requested_by = Column(String(128), nullable=False, index=True)
    requested_role = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="pending", index=True)
    approved_by = Column(String(128), nullable=True)
    approval_note = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)


class NetworkMetric(Base):
    __tablename__ = "network_metrics"
    id = Column(Integer, primary_key=True, index=True)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    status = Column(String(24), nullable=False)
    board_name = Column(String(128), nullable=True)
    uptime = Column(String(128), nullable=True)
    cpu_load = Column(Integer, nullable=True)
    free_memory_bytes = Column(BigInteger, nullable=True)
    total_memory_bytes = Column(BigInteger, nullable=True)
    active_users_count = Column(Integer, nullable=True)
    alert_summary = Column(Text, nullable=True)
