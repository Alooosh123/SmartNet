from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from pathlib import Path
from typing import Optional
import uuid
from io import BytesIO
from PIL import Image

from api.dependencies import get_current_cards_user
from database import models, schemas, database
from services.mikrotik_service import mikrotik_service
from services.pdf_service import pdf_service

router = APIRouter(prefix="/cards", tags=["cards"])

class CardGenerateRequest(BaseModel):
    count: int
    profile: str
    length: int = 6
    hide_password: bool = False
    card_image: Optional[str] = None

class CustomCardItem(BaseModel):
    username: str
    password: str | None = None

class CustomCardsRequest(BaseModel):
    profile: str = "1 Day"
    hide_password: bool = False
    card_image: Optional[str] = None
    cards: list[CustomCardItem]

@router.post("/upload-image")
async def upload_card_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_cards_user)
):
    """Upload validated image content for a custom card design."""
    allowed_types = {
        "image/jpeg": (".jpg", "JPEG"),
        "image/jpg": (".jpg", "JPEG"),
        "image/png": (".png", "PNG"),
        "image/webp": (".webp", "WEBP"),
    }
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="نوع الصورة غير مدعوم. يرجى رفع ملف JPG أو PNG أو WEBP.")

    contents = await file.read()
    if not contents or len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة يجب ألا يتجاوز 5 ميجابايت")
    expected_extension, expected_format = allowed_types[file.content_type]
    try:
        image = Image.open(BytesIO(contents))
        image.verify()
        if image.format != expected_format:
            raise ValueError("Image format does not match declared content type")
    except Exception:
        raise HTTPException(status_code=400, detail="الملف المرفوع ليس صورة سليمة أو لا يطابق نوع المحتوى")

    cards_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    unique_filename = f"card_{uuid.uuid4().hex}{expected_extension}"
    target_path = cards_dir / unique_filename

    with open(target_path, "wb") as output:
        output.write(contents)

    return {
        "ok": True,
        "url": f"/uploads/cards/{unique_filename}",
        "filename": unique_filename,
    }

@router.post("/generate", response_model=schemas.CardBatchResponse)
async def generate_cards(
    req: CardGenerateRequest,
    current_user: dict = Depends(get_current_cards_user),
    db: AsyncSession = Depends(database.get_db)
):
    role = current_user.get("role")
    client_obj = current_user.get("obj")
    plan = getattr(client_obj, "plan", "monthly") or "monthly"

    if role != "admin" and plan == "semi_annual" and req.count > 100:
        raise HTTPException(status_code=400, detail="الحد الأقصى لتوليد الكروت في الباقة النصف سنوية هو 100 كرت للدفعة الواحدة.")

    if req.count < 1 or req.count > 1000:
        raise HTTPException(status_code=400, detail="عدد الكروت يجب أن يكون بين 1 و 1000")
    if req.length < 4 or req.length > 16:
        raise HTTPException(status_code=400, detail="طول اسم المستخدم يجب أن يكون بين 4 و 16")

    try:
        cards = mikrotik_service.generate_cards(req.count, req.profile, req.length)
        batch = models.CardBatch(
            profile=req.profile,
            count=req.count,
            owner_username=current_user.get("username"),
        )
        db.add(batch)
        await db.flush()

        pdf_path = pdf_service.generate_cards_pdf(
            batch.id,
            cards,
            hide_password=req.hide_password,
            profile=req.profile,
            card_image=req.card_image,
        )
        batch.pdf_path = pdf_path

        for card_data in cards:
            db_card = models.Card(
                batch_id=batch.id,
                username=card_data['username'],
                password=card_data['password']
            )
            db.add(db_card)

        performed_by = current_user.get("username", "admin")
        db.add(models.AuditLog(
            action="generate_cards",
            performed_by=performed_by,
            details=f"Generated {req.count} cards for profile {req.profile} (batch #{batch.id})"
        ))
        await db.commit()
        await db.refresh(batch)
        return batch
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/custom", response_model=schemas.CardBatchResponse)
async def generate_custom_cards(
    req: CustomCardsRequest,
    current_user: dict = Depends(get_current_cards_user),
    db: AsyncSession = Depends(database.get_db)
):
    if not req.cards or len(req.cards) == 0:
        raise HTTPException(status_code=400, detail="يجب إدخال كرت واحد على الأقل")
    if len(req.cards) > 1000:
        raise HTTPException(status_code=400, detail="الحد الأقصى للدفعة الواحدة هو 1000 كرت")

    # Clean and prepare card list
    cleaned_cards = []
    seen_usernames = set()
    for item in req.cards:
        u = item.username.strip()
        if not u:
            continue
        if u in seen_usernames:
            continue
        seen_usernames.add(u)
        p = (item.password or "").strip() or u  # default password to username if omitted
        cleaned_cards.append({
            "username": u,
            "password": p,
            "profile": req.profile
        })

    if not cleaned_cards:
        raise HTTPException(status_code=400, detail="لم يتم العثور على كروت صالحة")

    try:
        # Add to router
        mikrotik_service.add_custom_cards(cleaned_cards, req.profile)

        # Save batch
        batch = models.CardBatch(
            profile=req.profile,
            count=len(cleaned_cards),
            owner_username=current_user.get("username"),
        )
        db.add(batch)
        await db.flush()

        # Generate styled PDF with optional custom card image
        pdf_path = pdf_service.generate_cards_pdf(
            batch.id,
            cleaned_cards,
            hide_password=req.hide_password,
            profile=req.profile,
            card_image=req.card_image,
        )
        batch.pdf_path = pdf_path

        # Save to database
        for card_data in cleaned_cards:
            existing = await db.execute(select(models.Card).where(models.Card.username == card_data['username']))
            if not existing.scalars().first():
                db_card = models.Card(
                    batch_id=batch.id,
                    username=card_data['username'],
                    password=card_data['password']
                )
                db.add(db_card)

        performed_by = current_user.get("username", "admin")
        db.add(models.AuditLog(
            action="custom_cards",
            performed_by=performed_by,
            details=f"Created custom batch #{batch.id} with {len(cleaned_cards)} cards (profile: {req.profile})"
        ))
        await db.commit()
        await db.refresh(batch)
        return batch
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batches", response_model=list[schemas.CardBatchResponse])
async def get_batches(
    current_user: dict = Depends(get_current_cards_user),
    db: AsyncSession = Depends(database.get_db)
):
    query = select(models.CardBatch)
    if current_user.get("role") != "admin":
        query = query.where(models.CardBatch.owner_username == current_user.get("username"))
    result = await db.execute(query.order_by(models.CardBatch.id.desc()))
    return result.scalars().all()

@router.get("/{batch_id}/pdf")
async def download_batch_pdf(
    batch_id: int,
    current_user: dict = Depends(get_current_cards_user),
    db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(select(models.CardBatch).where(models.CardBatch.id == batch_id))
    batch = result.scalars().first()
    if batch is None or not batch.pdf_path:
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")
    if (
        current_user.get("role") != "admin"
        and batch.owner_username != current_user.get("username")
    ):
        # Do not disclose whether another subscriber's batch exists.
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")

    private_pdf_root = (
        Path(__file__).resolve().parent.parent.parent / "uploads" / "pdfs"
    ).resolve()
    pdf_file = Path(batch.pdf_path).resolve()
    if private_pdf_root not in pdf_file.parents:
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود")
    if not pdf_file.is_file():
        raise HTTPException(status_code=404, detail="ملف PDF غير موجود على الخادم")

    if pdf_file.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="نوع الملف غير صالح")

    return FileResponse(
        str(pdf_file),
        media_type="application/pdf",
        filename=f"smartnet_batch_{batch_id}.pdf"
    )


