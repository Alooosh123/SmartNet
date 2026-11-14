"""Deterministic wallet receipt parsers and secure identity helpers.

The shared Arabic receipt parser extracts candidate fields only. It never treats a
receipt by itself as proof of settlement: absent an explicit provider success status,
the result is marked receipt_only and requires an operator to check the real wallet app.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
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

KNOWN_WALLET_CODES = (
    "jaib",
    "flousak",
    "jawali",
    "cash",
    "one_cash",
    "alkuraimi_jawwal",
    "mobile_money",
)

# A receipt in Sana'a/Yemen uses the local UTC+03:00 clock.
YEMEN_RECEIPT_TIMEZONE = timezone(timedelta(hours=3))

REFERENCE_LABELS = (
    "رقم مرجع العملية",
    "رقم المرجع",
    "مرجع العملية",
    "رقم العملية",
    "رقم الحوالة",
    "الرقم المرجعي",
)
SENDER_LABELS = ("المودع", "المرسل", "مصدر الحوالة", "صاحب التحويل")
RECIPIENT_LABELS = ("المستفيد", "المستلم", "المحول اليه", "المحول إليه")
SECTION_LABELS = REFERENCE_LABELS + SENDER_LABELS + RECIPIENT_LABELS + (
    "العملية",
    "نوع العملية",
    "تاريخ العملية",
    "المبلغ",
)


def _ascii_digits(value: str) -> str:
    result = []
    for char in unicodedata.normalize("NFKC", value or ""):
        try:
            result.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            result.append(char)
    return "".join(result)


def _fold_arabic(value: str) -> str:
    text = unicodedata.normalize("NFKC", _ascii_digits(value or ""))
    text = text.replace("ـ", "")
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_wallet_identifier(value: str) -> str:
    """Normalize Arabic/Latin digits and safe separators; reject ambiguous input."""
    normalized = unicodedata.normalize("NFKC", value or "").strip()
    digits = []
    for char in normalized:
        if char.isspace() or char in "-().":
            continue
        if char == "+":
            if digits:
                raise ValueError("Plus sign is allowed only at the start of a wallet identifier.")
            digits.append("+")
            continue
        try:
            digits.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Wallet identifier contains an unsupported character.") from exc
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


def _is_section_heading(line: str) -> bool:
    folded = _fold_arabic(line)
    return any(label in folded for label in SECTION_LABELS)


def _section_value(text: str, labels: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        folded = _fold_arabic(line)
        for label in labels:
            if label not in folded:
                continue
            # In the sample receipt the value is displayed to the left of the
            # right-aligned label; notifications may put it after the label.
            label_position = folded.find(label)
            before = line[:label_position].strip(" :：-\t")
            after = line[label_position + len(label):].strip(" :：-\t")
            current = " ".join(part for part in (before, after) if part).strip()
            if current:
                return current
            if index + 1 < len(lines) and not _is_section_heading(lines[index + 1]):
                return lines[index + 1]
    return ""


def _section_block(text: str, labels: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        folded = _fold_arabic(line)
        matched = next((label for label in labels if label in folded), None)
        if not matched:
            continue
        position = folded.find(matched)
        before = line[:position].strip(" :：-\t")
        after = line[position + len(matched):].strip(" :：-\t")
        collected = [part for part in (before, after) if part]
        for next_line in lines[index + 1:]:
            if _is_section_heading(next_line):
                break
            collected.append(next_line)
            if len(collected) >= 4:
                break
        return " ".join(collected)
    return ""


def _extract_phone(section: str) -> Optional[str]:
    normalized = _ascii_digits(section)
    candidates = re.findall(r"(?<!\d)\+?\d[\d\s().-]{5,24}", normalized)
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if 7 <= len(digits) <= 15:
            try:
                return normalize_wallet_identifier(candidate)
            except ValueError:
                continue
    return None


def _extract_reference(text: str) -> Optional[str]:
    value = _section_value(text, REFERENCE_LABELS)
    match = re.search(r"(?<!\d)\d{6,40}(?!\d)", _ascii_digits(value))
    if match:
        return match.group(0)
    return None


def _extract_amount_currency(text: str) -> Optional[tuple[Decimal, str]]:
    normalized = _ascii_digits(text).replace("٬", ",").replace("٫", ".")
    pattern = re.compile(
        r"(?P<amount>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        r"\s*(?P<currency>ريال\s*يمني|ر\.ي|ريال\s*سعودي|دولار\s*(?:امريكي|أمريكي)?|YER|SAR|USD)",
        re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        return None
    try:
        amount = Decimal(match.group("amount").replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    currency_text = _fold_arabic(match.group("currency"))
    if "سعودي" in currency_text or currency_text == "sar":
        currency = "SAR"
    elif "دولار" in currency_text or currency_text == "usd":
        currency = "USD"
    else:
        currency = "YER"
    if amount <= 0:
        return None
    return amount, currency


def _extract_receipt_time(text: str) -> Optional[datetime]:
    value = _section_value(text, ("تاريخ العملية", "تاريخ الحوالة", "التاريخ"))
    normalized = _ascii_digits(value or text)
    match = re.search(
        r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*(?:\((?P<time>\d{1,2}:\d{2})\))?",
        normalized,
    )
    if not match:
        return None
    try:
        parsed_date = datetime.strptime(match.group("date"), "%d/%m/%Y").date()
        parsed_time = datetime.strptime(match.group("time") or "00:00", "%H:%M").time()
        return datetime.combine(parsed_date, parsed_time, tzinfo=YEMEN_RECEIPT_TIMEZONE).astimezone(timezone.utc)
    except ValueError:
        return None


def _receipt_status(text: str) -> str:
    folded = _fold_arabic(text)
    if any(term in folded for term in ("مرفوض", "فشل التحويل", "فشلت العملية", "ملغى", "ملغاة", "معكوس", "reversed", "failed", "declined")):
        return "failed"
    if any(term in folded for term in ("قيد الانتظار", "قيد المعالجة", "pending", "processing")):
        return "pending"
    if any(term in folded for term in ("تمت العملية بنجاح", "تم التحويل بنجاح", "عملية ناجحة", "مكتملة", "ناجحة", "successful", "completed", "settled")):
        return "settled"
    # A receipt heading and reference are not, by themselves, a settlement signal.
    return "receipt_only"


def parse_arabic_wallet_receipt(title: str, body: str) -> Optional[ParsedWalletTransfer]:
    """Parse the shared Arabic transfer-receipt fields; missing fields stay untrusted."""
    text = "\n".join(part for part in (title, body) if part)
    if not text.strip():
        return None

    reference = _extract_reference(text)
    amount_and_currency = _extract_amount_currency(text)
    sender = _extract_phone(_section_block(text, SENDER_LABELS))
    recipient = _extract_phone(_section_block(text, RECIPIENT_LABELS))
    if not reference or not amount_and_currency or not sender or not recipient:
        return None

    amount, currency = amount_and_currency
    return ParsedWalletTransfer(
        provider_transaction_id=None,
        provider_reference=reference,
        sender_identifier=sender,
        recipient_identifier=recipient,
        amount=amount,
        currency=currency,
        provider_status=_receipt_status(text),
        occurred_at=_extract_receipt_time(text),
    )


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


for _wallet_code in KNOWN_WALLET_CODES:
    register_notification_parser(_wallet_code, parse_arabic_wallet_receipt)
