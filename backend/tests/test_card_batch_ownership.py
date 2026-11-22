from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.routes.cards import download_batch_pdf, get_batches
from database.database import Base
from database.models import CardBatch
from services.pdf_service import pdf_service


@pytest.mark.asyncio
async def test_card_batches_are_visible_only_to_their_owner(tmp_path: Path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    pdf_file = pdf_service.output_dir / f"test-{tmp_path.name}.pdf"
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    pdf_file.write_bytes(b"%PDF-1.4 test")
    async with Session() as session:
        alice_batch = CardBatch(
            profile="1 Day",
            count=2,
            owner_username="alice",
            pdf_path=str(pdf_file),
        )
        bob_batch = CardBatch(
            profile="1 Day",
            count=3,
            owner_username="bob",
            pdf_path=str(pdf_file),
        )
        session.add_all([alice_batch, bob_batch])
        await session.commit()
        await session.refresh(alice_batch)
        await session.refresh(bob_batch)

        alice_batches = await get_batches(
            current_user={"role": "client", "username": "alice"},
            db=session,
        )
        assert [batch.id for batch in alice_batches] == [alice_batch.id]

        admin_batches = await get_batches(
            current_user={"role": "admin", "username": "owner"},
            db=session,
        )
        assert {batch.id for batch in admin_batches} == {alice_batch.id, bob_batch.id}

        with pytest.raises(HTTPException) as denied:
            await download_batch_pdf(
                batch_id=bob_batch.id,
                current_user={"role": "client", "username": "alice"},
                db=session,
            )
        assert denied.value.status_code == 404

        owner_response = await download_batch_pdf(
            batch_id=alice_batch.id,
            current_user={"role": "client", "username": "alice"},
            db=session,
        )
        assert isinstance(owner_response, FileResponse)

    pdf_file.unlink(missing_ok=True)
    await engine.dispose()


def test_generated_card_pdfs_are_not_in_public_static_directory():
    backend_root = Path(__file__).resolve().parents[1]
    public_static = (backend_root / "static").resolve()
    private_pdf_dir = pdf_service.output_dir.resolve()
    assert private_pdf_dir.name == "pdfs"
    assert private_pdf_dir.parent.name == "uploads"
    assert not private_pdf_dir.is_relative_to(public_static)
