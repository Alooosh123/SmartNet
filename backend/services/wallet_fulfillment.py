"""Idempotent subscription fulfilment for reviewed wallet transactions.

The function is intentionally separate from notification intake. It accepts only a
transaction already marked provider_verified or manually_verified by a trusted path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database import models
from services.subscription_agent import PLANS


SETTLED_STATUSES = {"settled", "completed", "successful", "success"}


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def fulfill_wallet_payment_intent(
    db: AsyncSession,
    *,
    intent_id: int,
    transaction_id: int,
    actor: str,
    allow_automatic: bool = False,
    now: Optional[datetime] = None,
) -> dict:
    """Apply one verified wallet payment exactly once and extend from max(expiry, now)."""
    current_time = _as_utc(now or datetime.now(timezone.utc))

    intent_result = await db.execute(
        select(models.WalletPaymentIntent)
        .where(models.WalletPaymentIntent.id == intent_id)
        .with_for_update()
    )
    intent = intent_result.scalars().first()
    if not intent:
        raise ValueError("Payment intent does not exist.")

    existing_result = await db.execute(
        select(models.WalletSubscriptionFulfillment).where(
            models.WalletSubscriptionFulfillment.intent_id == intent.id
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        if existing.transaction_id != transaction_id:
            raise ValueError("This payment intent has already been fulfilled by another transaction.")
        return {
            "idempotent_replay": True,
            "fulfillment_id": existing.id,
            "client_id": existing.client_id,
            "new_expiry": existing.new_expiry,
            "plan": existing.plan,
        }

    transaction_result = await db.execute(
        select(models.WalletTransaction)
        .where(models.WalletTransaction.id == transaction_id)
        .with_for_update()
    )
    transaction = transaction_result.scalars().first()
    if not transaction:
        raise ValueError("Wallet transaction does not exist.")
    if transaction.intent_id != intent.id:
        raise ValueError("Wallet transaction is not linked to this payment intent.")
    if transaction.verification_status not in {"provider_verified", "manually_verified"}:
        raise ValueError("Wallet transaction has not passed trusted financial verification.")
    if transaction.provider_status not in SETTLED_STATUSES:
        raise ValueError("Wallet provider has not reported a final settled transaction.")
    if not transaction.provider_transaction_id and not transaction.provider_reference:
        raise ValueError("A stable provider transaction ID or reference is required.")
    if transaction.amount != intent.amount or transaction.currency != intent.currency:
        raise ValueError("Transaction amount/currency does not exactly match the payment intent.")
    if intent.status != "open":
        raise ValueError("Payment intent is not open.")
    if _as_utc(intent.expires_at) <= current_time:
        raise ValueError("Payment intent has expired.")

    provider = await db.get(models.WalletProvider, transaction.provider_id)
    receiving = await db.get(models.ReceivingWalletAccount, intent.receiving_wallet_id)
    payer = await db.get(models.PayerWalletIdentity, intent.payer_wallet_id)
    if not provider or not provider.enabled:
        raise ValueError("Wallet provider is disabled.")
    if not receiving or not receiving.is_active or receiving.id != transaction.receiving_wallet_id:
        raise ValueError("Receiving wallet account is disabled or does not match.")
    if receiving.provider_id != provider.id or receiving.currency != intent.currency:
        raise ValueError("Receiving wallet provider/currency does not match the payment intent.")
    if not payer or payer.status != "active" or payer.provider_id != provider.id:
        raise ValueError("Payer wallet identity is not approved and active.")

    if allow_automatic:
        if not settings.WALLET_AUTO_ACTIVATION_ENABLED:
            raise ValueError("Automatic wallet activation is disabled.")
        if not provider.auto_verification_enabled or not provider.parser_version:
            raise ValueError("Provider parser has not passed the automatic acceptance gate.")

    plan_info = PLANS.get(intent.plan)
    if not plan_info:
        raise ValueError("Payment intent references an unsupported subscription plan.")
    days = int(plan_info["days"])

    client = None
    registration = None
    previous_expiry = None
    if intent.intent_type == "renewal":
        if not intent.client_id or intent.registration_id is not None:
            raise ValueError("Renewal intent must target exactly one existing client.")
        if payer.client_id != intent.client_id:
            raise ValueError("Payer wallet identity does not belong to the renewal client.")
        client_result = await db.execute(
            select(models.Client).where(models.Client.id == intent.client_id).with_for_update()
        )
        client = client_result.scalars().first()
        if not client:
            raise ValueError("Renewal client does not exist.")
        if not client.is_active:
            raise ValueError("Administratively disabled clients cannot be reactivated by payment.")
        previous_expiry = _as_utc(client.subscription_expires)
        base_time = max(previous_expiry, current_time) if previous_expiry else current_time
        new_expiry = base_time + timedelta(days=days)
    elif intent.intent_type == "initial":
        if not intent.registration_id or intent.client_id is not None:
            raise ValueError("Initial intent must target exactly one registration request.")
        if payer.registration_id != intent.registration_id:
            raise ValueError("Payer wallet identity does not belong to the initial registration.")
        registration = await db.get(models.RegistrationRequest, intent.registration_id)
        if not registration or registration.processed:
            raise ValueError("Registration is missing or has already been processed.")
        if (registration.plan or "monthly") != intent.plan:
            raise ValueError("Payment intent plan no longer matches the registration.")
        if Decimal(str(registration.price or 0)).quantize(Decimal("0.01")) != intent.amount:
            raise ValueError("Payment intent amount no longer matches the registration.")
        if (registration.currency or "USD").upper() != intent.currency:
            raise ValueError("Payment intent currency no longer matches the registration.")
        existing_client = await db.execute(
            select(models.Client).where(models.Client.username == registration.username)
        )
        if existing_client.scalars().first():
            raise ValueError("Client account already exists for this registration.")
        new_expiry = current_time + timedelta(days=days)
    else:
        raise ValueError("Unsupported payment intent type.")

    if registration is not None:
        reference = transaction.provider_transaction_id or transaction.provider_reference
        duplicate_registration = await db.execute(
            select(models.RegistrationRequest).where(
                models.RegistrationRequest.payment_ref == reference,
                models.RegistrationRequest.id != registration.id,
            )
        )
        if duplicate_registration.scalars().first():
            raise ValueError("Provider reference is already assigned to another registration.")
        client = models.Client(
            username=registration.username,
            hashed_password=registration.hashed_password,
            plan=intent.plan,
            can_reboot_network=bool(plan_info["can_reboot_network"]),
            subscription_expires=new_expiry,
            is_active=True,
        )
        db.add(client)
        await db.flush()
        registration.paid = True
        registration.processed = True
        registration.payment_ref = reference
        registration.payment_verified_amount = intent.amount
        registration.payment_verified_currency = intent.currency
        registration.payment_verified_by = actor[:120]
        registration.payment_verified_at = current_time
        registration.payment_verification_note = f"Wallet transaction #{transaction.id} verified."
        payer.client_id = client.id
    else:
        client.plan = intent.plan
        client.can_reboot_network = bool(plan_info["can_reboot_network"])
        client.subscription_expires = new_expiry

    intent.status = "fulfilled"
    transaction.verification_status = "fulfilled"
    fulfillment = models.WalletSubscriptionFulfillment(
        client_id=client.id,
        intent_id=intent.id,
        transaction_id=transaction.id,
        plan=intent.plan,
        days=days,
        previous_expiry=previous_expiry,
        new_expiry=new_expiry,
        status="completed",
    )
    db.add(fulfillment)

    review_result = await db.execute(
        select(models.WalletPaymentReview).where(
            models.WalletPaymentReview.transaction_id == transaction.id,
            models.WalletPaymentReview.status == "open",
        )
    )
    review = review_result.scalars().first()
    if review:
        review.status = "closed"
        review.decision = "approved"
        review.reviewed_by = actor[:120]
        review.reviewed_at = current_time
        review.note = "Financial verification passed; subscription fulfilment completed."

    db.add(models.AuditLog(
        action="wallet_subscription_fulfilled",
        performed_by=actor[:120],
        details=(
            f"Fulfilled wallet intent #{intent.id} using transaction #{transaction.id}; "
            f"client_id={client.id}; plan={intent.plan}; expiry={new_expiry.isoformat()}."
        ),
    ))
    try:
        await db.commit()
        await db.refresh(fulfillment)
    except IntegrityError:
        await db.rollback()
        replay_result = await db.execute(
            select(models.WalletSubscriptionFulfillment).where(
                models.WalletSubscriptionFulfillment.intent_id == intent_id
            )
        )
        replay = replay_result.scalars().first()
        if replay and replay.transaction_id == transaction_id:
            return {
                "idempotent_replay": True,
                "fulfillment_id": replay.id,
                "client_id": replay.client_id,
                "new_expiry": replay.new_expiry,
                "plan": replay.plan,
            }
        raise ValueError("A conflicting payment fulfilment already exists.")

    return {
        "idempotent_replay": False,
        "fulfillment_id": fulfillment.id,
        "client_id": client.id,
        "new_expiry": new_expiry,
        "plan": intent.plan,
    }
