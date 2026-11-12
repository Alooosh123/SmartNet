from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
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
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    plan = Column(String, default="monthly", nullable=True)  # 'monthly', 'semi_annual', 'annual'
    price = Column(Integer, default=20, nullable=True)       # 20, 60, 100
    paid = Column(Boolean, default=False)
    payment_ref = Column(String, nullable=True, index=True)
    registration_token_hash = Column(String, nullable=True)
    receipt_image = Column(String, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    plan = Column(String, default="monthly", nullable=True)  # 'monthly', 'semi_annual', 'annual'
    can_reboot_network = Column(Boolean, default=False, nullable=True)
    is_active = Column(Boolean, default=True)
    subscription_expires = Column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    sender = Column(String, nullable=False)  # 'client' or 'bot' or 'owner'
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

