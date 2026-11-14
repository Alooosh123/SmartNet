"""Deterministic primitives for the Android wallet notification collector.

Provider-specific parsers are intentionally not registered until real notification
samples and package identifiers have been accepted for that wallet.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Optional

from config.settings import settings


@dataclass(frozen=True)
class ParsedWalletTransfer:
    provider_transaction_id: Optional[str]
    provider_reference: Optional[str]
    sender_identifier: str
    recipient_identifier: str
    amount: Decimal
    currency: str
    provider_status: str
    occurred_at: Optional[object] = None


Parser = Callable[[str, str], Optional[ParsedWalletTransfer]]
_PARSERS: dict[str, Parser] = {}


def normalize_wallet_identifier(value: str) -> str:
    """Normalize Arabic/Latin digits and separators without guessing country codes."""
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    digits = []
    for char in normalized:
        try:
            digits.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            if char == "+" and not digits:
                digits.append(char)
    result = "".join(digits)
    if not re.fullmatch(r"\+?\d{6,24}", result):
        raise ValueError("Wallet identifier must contain 6 to 24 digits.")
    return result


def wallet_fingerprint(value: str) -> str:
    secret = settings.WALLET_IDENTITY_HMAC_SECRET
    if not secret or len(secret) < 32:
        raise RuntimeError("WALLET_IDENTITY_HMAC_SECRET is not configured.")
    normalized = normalize_wallet_identifier(value)
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_wallet_identifier(value: str) -> str:
    normalized = normalize_wallet_identifier(value)
    return f"***{normalized[-4:]}"


def register_notification_parser(provider_code: str, parser: Parser) -> None:
    """Register a reviewed provider parser from trusted application code only."""
    code = provider_code.strip().lower()
    if not code:
        raise ValueError("Provider code is required.")
    _PARSERS[code] = parser


def parse_wallet_notification(
    provider_code: str,
    title: str,
    body: str,
) -> Optional[ParsedWalletTransfer]:
    parser = _PARSERS.get(provider_code.strip().lower())
    if parser is None:
        return None
    return parser(title[:500], body[:4000])


def can_auto_verify(provider, parsed: ParsedWalletTransfer) -> bool:
    """Fail closed unless the provider and global switch are explicitly accepted."""
    if not settings.WALLET_MONITORING_ENABLED:
        return False
    if not settings.WALLET_AUTO_ACTIVATION_ENABLED:
        return False
    if not provider.enabled or not provider.auto_verification_enabled or not provider.parser_version:
        return False
    if not parsed.provider_transaction_id and not parsed.provider_reference:
        return False
    return parsed.provider_status.strip().lower() in {"settled", "completed", "successful", "success"}
