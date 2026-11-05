import io
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from PIL import Image as PILImage
from typing import List, Dict, Any


# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_CYAN = HexColor("#00d4aa")
BRAND_DARK = HexColor("#1a2332")
BRAND_LIGHT = HexColor("#e8f8f5")
BORDER_GREY = HexColor("#cccccc")
TEXT_DARK = HexColor("#2c3e50")
TEXT_MUTED = HexColor("#7f8c8d")

# ── Card geometry ──────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4                  # 595.27 x 841.89 pts
MARGIN = 15 * mm
CARD_COLS = 2
CARD_ROWS = 3
CARD_GAP = 5 * mm
CARD_W = (PAGE_W - 2 * MARGIN - (CARD_COLS - 1) * CARD_GAP) / CARD_COLS
CARD_H = (PAGE_H - 2 * MARGIN - (CARD_ROWS - 1) * CARD_GAP) / CARD_ROWS
CORNER_R = 6


def _profile_label(profile: str, duration_hours: int = 0) -> str:
    if not profile:
        return "افتراضي"
    mapping = {
        "1h": "1 ساعة",
        "2h": "2 ساعة",
        "6h": "6 ساعات",
        "12h": "12 ساعة",
        "24h": "24 ساعة",
        "1day": "يوم كامل",
        "1week": "أسبوع",
        "1month": "شهر",
        "1 day": "يوم كامل",
        "1 week": "أسبوع",
        "1 month": "شهر",
        "100": "فئة 100 ريال",
        "200": "فئة 200 ريال",
        "300": "فئة 300 ريال",
        "500": "فئة 500 ريال",
        "1000": "فئة 1000 ريال",
        "3000": "اشتراك شهري 3000 ريال",
    }
    p_strip = str(profile).strip()
    p_lower = p_strip.lower()
    if p_lower in mapping:
        return mapping[p_lower]
    return p_strip


def _load_card_image(img_val: str):
    """Safely load user-provided custom card logo/image."""
    if not img_val:
        return None
    try:
        import base64
        from pathlib import Path
        if img_val.startswith("data:image"):
            parts = img_val.split(",", 1)
            if len(parts) == 2:
                raw = base64.b64decode(parts[1])
                return PILImage.open(io.BytesIO(raw))
        p = Path(img_val)
        if p.exists() and p.is_file():
            return PILImage.open(p)
        if img_val.startswith("/uploads/"):
            alt = Path(__file__).resolve().parent.parent / img_val.lstrip("/")
            if alt.exists() and alt.is_file():
                return PILImage.open(alt)
    except Exception:
        return None
    return None



def _make_qr_image(data: str, size_px: int = 120) -> PILImage.Image:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size_px, size_px), PILImage.LANCZOS)
    return img


def _pil_to_reportlab(pil_img: PILImage.Image) -> io.BytesIO:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _draw_rounded_rect(c: canvas.Canvas, x: float, y: float, w: float, h: float, r: float):
    """Draw a filled rounded rectangle (lower-left origin)."""
    c.roundRect(x, y, w, h, r, stroke=1, fill=1)


def _draw_card(
    c: canvas.Canvas,
    x: float,
    y: float,
    card: Dict[str, Any],
    batch_info: Dict[str, Any],
):
    """Draw a single voucher card at position (x, y) — lower-left corner."""
    w, h = CARD_W, CARD_H

    # ── Background ────────────────────────────────────────────────────────────
    c.setFillColor(colors.white)
    c.setStrokeColor(BORDER_GREY)
    c.setLineWidth(0.5)
    _draw_rounded_rect(c, x, y, w, h, CORNER_R)

    # ── Header strip ─────────────────────────────────────────────────────────
    header_h = h * 0.22
    c.setFillColor(BRAND_CYAN)
    c.setStrokeColor(BRAND_CYAN)
    c.roundRect(x, y + h - header_h, w, header_h, CORNER_R, stroke=0, fill=1)
    # square off the bottom of the header
    c.rect(x, y + h - header_h, w, header_h / 2, stroke=0, fill=1)

    # ── Optional custom card logo / image ───────────────────────────────────
    card_img_buf = batch_info.get("_card_image_buf")
    has_custom_img = False
    if card_img_buf:
        try:
            c.drawImage(
                card_img_buf,
                x + 8,
                y + h - header_h + 4,
                width=header_h - 8,
                height=header_h - 8,
                preserveAspectRatio=True,
                mask="auto",
            )
            has_custom_img = True
        except Exception:
            has_custom_img = False

    # ── Logo / title ─────────────────────────────────────────────────────────
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    title = batch_info.get("network_name") or "SmartNet"
    title_x = x + w / 2 + (12 if has_custom_img else 0)
    c.drawCentredString(title_x, y + h - header_h * 0.45, title)

    c.setFont("Helvetica", 7)
    ssid = batch_info.get("ssid", "SmartNet-WiFi")
    c.drawCentredString(title_x, y + h - header_h * 0.75, ssid)

    # ── QR code ───────────────────────────────────────────────────────────────
    qr_size = min(w * 0.30, h * 0.25)
    qr_x = x + w - qr_size - 5
    qr_y = y + h - header_h - qr_size - 8

    hide_pass = batch_info.get("hide_password", False)
    if hide_pass:
        qr_data = f"SSID:{ssid}\nUSER:{card['username']}"
    else:
        qr_data = f"SSID:{ssid}\nUSER:{card['username']}\nPASS:{card['password']}"
    try:
        qr_img = _make_qr_image(qr_data, size_px=int(qr_size * 2.5))
        qr_buf = _pil_to_reportlab(qr_img)
        c.drawImage(
            qr_buf,
            qr_x,
            qr_y,
            width=qr_size,
            height=qr_size,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        pass  # skip QR if it fails

    # ── Body text ─────────────────────────────────────────────────────────────
    body_x = x + 8
    line_h = h * 0.11
    body_top = y + h - header_h - 14

    def label_value(label_en: str, label_ar: str, value: str, cy: float):
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(TEXT_MUTED)
        c.drawString(body_x, cy + 2, label_en)

        c.setFont("Helvetica", 7)
        c.setFillColor(TEXT_MUTED)
        c.drawRightString(x + w - qr_size - 12, cy + 2, label_ar)

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(TEXT_DARK)
        c.drawString(body_x, cy - 8, value)

    pass_display = "****** (مخفية)" if hide_pass else card["password"]
    label_value("Username", "اسم المستخدم", card["username"], body_top)
    label_value("Password", "كلمة المرور", pass_display, body_top - line_h)

    duration_label = _profile_label(
        card.get("profile") or batch_info.get("profile", ""), card.get("duration_hours", 0)
    )
    cat_label = "الفئة / الباقة" if ("ريال" in duration_label or "yer" in duration_label.lower()) else "مدة الاشتراك"
    label_value("Category / Duration", cat_label, duration_label, body_top - line_h * 2)

    # ── Footer divider ────────────────────────────────────────────────────────
    footer_y = y + h * 0.10
    c.setStrokeColor(BRAND_CYAN)
    c.setLineWidth(0.8)
    c.line(x + 8, footer_y, x + w - 8, footer_y)

    c.setFont("Helvetica", 6)
    c.setFillColor(TEXT_MUTED)
    c.drawCentredString(
        x + w / 2,
        footer_y - 8,
        "Powered by SmartNet  •  smartnet.local",
    )

    # ── Outer border ─────────────────────────────────────────────────────────
    c.setStrokeColor(BRAND_CYAN)
    c.setLineWidth(1.2)
    c.setFillColor(colors.transparent)
    c.roundRect(x, y, w, h, CORNER_R, stroke=1, fill=0)


def generate_cards_pdf(cards: List[Dict[str, Any]], batch_info: Dict[str, Any]) -> bytes:
    """
    Generate a PDF voucher sheet.

    :param cards: list of dicts with keys: username, password, profile, duration_hours
    :param batch_info: dict with optional keys: ssid, profile, duration_hours, notes, batch_id
    :returns: PDF as bytes
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("SmartNet Hotspot Cards")
    c.setAuthor("SmartNet System")
    c.setSubject(f"Batch #{batch_info.get('batch_id', 'N/A')} — {len(cards)} cards")

    # Preload custom card image if provided
    card_img_val = batch_info.get("card_image")
    if card_img_val and "_card_image_buf" not in batch_info:
        pil_card = _load_card_image(card_img_val)
        if pil_card:
            batch_info["_card_image_buf"] = _pil_to_reportlab(pil_card)

    for page_start in range(0, len(cards), CARD_COLS * CARD_ROWS):
        page_cards = cards[page_start: page_start + CARD_COLS * CARD_ROWS]

        # ── Page header ───────────────────────────────────────────────────────
        c.setFillColor(BRAND_DARK)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGIN, PAGE_H - MARGIN + 6, "SmartNet  —  Hotspot Voucher Cards")
        c.setFont("Helvetica", 8)
        c.setFillColor(TEXT_MUTED)
        page_num = page_start // (CARD_COLS * CARD_ROWS) + 1
        c.drawRightString(
            PAGE_W - MARGIN,
            PAGE_H - MARGIN + 6,
            f"Batch #{batch_info.get('batch_id', 'N/A')}  •  Page {page_num}",
        )

        # ── Draw cards ────────────────────────────────────────────────────────
        for idx, card in enumerate(page_cards):
            col = idx % CARD_COLS
            row = idx // CARD_COLS

            card_x = MARGIN + col * (CARD_W + CARD_GAP)
            card_y = (
                PAGE_H
                - MARGIN
                - (row + 1) * CARD_H
                - row * CARD_GAP
                - 8  # space for page header
            )

            _draw_card(c, card_x, card_y, card, batch_info)

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()
