import os
from pathlib import Path
from typing import List, Dict, Any
from config.settings import settings
from services.pdf_generator import generate_cards_pdf as generate_styled_pdf

class PDFService:
    def __init__(self):
        # Backend static directory
        self.output_dir = Path(__file__).resolve().parent.parent / 'static' / 'pdfs'
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_cards_pdf(self, batch_id: int, cards: list, hide_password: bool = False, profile: str = "1day", card_image: str = None) -> str:
        filename = self.output_dir / f"batch_{batch_id}.pdf"
        
        batch_info = {
            "batch_id": batch_id,
            "ssid": settings.SSID,
            "profile": profile,
            "hide_password": hide_password,
            "card_image": card_image,
        }

        try:
            pdf_bytes = generate_styled_pdf(cards, batch_info)
            with open(filename, "wb") as f:
                f.write(pdf_bytes)
            return str(filename)
        except Exception as e:
            # Fallback simple generator if needed
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm

            c = canvas.Canvas(str(filename), pagesize=A4)
            width, height = A4
            card_width, card_height = 8 * cm, 5 * cm
            x_margin, y_margin = 2 * cm, 2 * cm
            x, y = x_margin, height - y_margin - card_height

            for card in cards:
                c.rect(x, y, card_width, card_height)
                c.setFont("Helvetica-Bold", 14)
                c.drawString(x + 1 * cm, y + 3.8 * cm, "SmartNet Hotspot")
                c.setFont("Helvetica", 10)
                c.drawString(x + 1 * cm, y + 3.0 * cm, f"SSID: {settings.SSID}")
                c.setFont("Helvetica", 12)
                c.drawString(x + 1 * cm, y + 2 * cm, f"User: {card['username']}")
                pass_text = "Pass: ******" if hide_password else f"Pass: {card['password']}"
                c.drawString(x + 1 * cm, y + 1 * cm, pass_text)

                x += card_width + 1 * cm
                if x + card_width > width - x_margin:
                    x = x_margin
                    y -= (card_height + 1 * cm)
                if y < y_margin:
                    c.showPage()
                    x = x_margin
                    y = height - y_margin - card_height

            c.save()
            return str(filename)

pdf_service = PDFService()

