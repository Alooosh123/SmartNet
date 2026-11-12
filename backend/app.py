from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.future import select
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config.settings import settings
from database.database import engine, Base, AsyncSessionLocal
from database import models
from services.auth_service import auth_service
from services.subscription_agent import subscription_agent_loop
from services.network_observer import network_monitor_loop
from api.routes import auth, mikrotik, cards, client, agents

logger = logging.getLogger(__name__)


async def run_sqlite_migrations(conn) -> None:
    if conn.dialect.name != "sqlite":
        return
    migrations = {
        "registration_requests": {
            "plan": "VARCHAR DEFAULT 'monthly'", "price": "INTEGER DEFAULT 20",
            "receipt_image": "VARCHAR", "registration_token_hash": "VARCHAR",
        },
        "clients": {"plan": "VARCHAR DEFAULT 'monthly'", "can_reboot_network": "BOOLEAN DEFAULT 0"},
        "card_batches": {"owner_username": "VARCHAR"},
    }
    for table, columns in migrations.items():
        rows = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in rows.fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


async def migrate_legacy_public_pdfs(session) -> None:
    backend_root = Path(__file__).resolve().parent
    public_pdf_dir = (backend_root / "static" / "pdfs").resolve()
    private_pdf_dir = (backend_root / "uploads" / "pdfs").resolve()
    public_pdf_dir.mkdir(parents=True, exist_ok=True)
    private_pdf_dir.mkdir(parents=True, exist_ok=True)
    moved_by_name = {}
    for source in public_pdf_dir.glob("*.pdf"):
        destination = private_pdf_dir / source.name
        try:
            if destination.exists():
                source.unlink()
            else:
                shutil.move(str(source), str(destination))
            moved_by_name[source.name] = destination
        except OSError:
            logger.exception("Could not secure legacy public PDF: %s", source)
            raise
    if not moved_by_name:
        return
    result = await session.execute(select(models.CardBatch))
    changed = False
    for batch in result.scalars().all():
        if not batch.pdf_path:
            continue
        stored = str(batch.pdf_path).replace("\\", "/")
        filename = Path(stored).name
        if filename in moved_by_name and ("/static/pdfs/" in f"/{stored.strip('/')}" or "/pdfs/" in f"/{stored.strip('/')}"):
            batch.pdf_path = str(moved_by_name[filename])
            changed = True
    if changed:
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_sqlite_migrations(conn)

    async with AsyncSessionLocal() as session:
        await migrate_legacy_public_pdfs(session)
        result = await session.execute(select(models.Admin).limit(1))
        if result.scalars().first() is None:
            hashed = auth_service.get_password_hash(settings.DASHBOARD_PASSWORD)
            session.add(models.Admin(username=settings.DASHBOARD_USERNAME.strip(), hashed_password=hashed, is_active=True))
            session.add(models.AuditLog(action="bootstrap_admin", performed_by="system", details="Created initial administrator from protected environment configuration"))
            await session.commit()
            logger.warning("Initial SmartNet administrator created from environment configuration.")

    stop_event = asyncio.Event()
    tasks = [asyncio.create_task(subscription_agent_loop(stop_event))]
    if settings.NETWORK_MONITOR_ENABLED:
        tasks.append(asyncio.create_task(network_monitor_loop(stop_event)))
    try:
        yield
    finally:
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="SmartNet API", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^http://(localhost|127\.0.0.1)(:\d+)?$" if settings.ENVIRONMENT.lower() != "production" else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Webhook-Secret", "X-Registration-Token"],
)

@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

uploads_dir = Path(__file__).resolve().parent / "uploads"
cards_uploads_dir = uploads_dir / "cards"
cards_uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "receipts").mkdir(parents=True, exist_ok=True)
app.mount("/uploads/cards", StaticFiles(directory=str(cards_uploads_dir)), name="card-uploads")

app.include_router(auth.router)
app.include_router(mikrotik.router)
app.include_router(cards.router)
app.include_router(client.router)
app.include_router(agents.router)


@app.get("/")
def read_root():
    return {"message": "مرحباً بك في واجهة برمجة تطبيقات SmartNet", "status": "online"}


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "SmartNet", "version": "1.2.0"}


@app.get("/api/health/ready")
async def readiness_check():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        db_dialect = conn.dialect.name
    return {
        "status": "ready", "database": "connected", "database_engine": db_dialect,
        "environment": settings.ENVIRONMENT,
        "mikrotik_demo_mode": settings.MIKROTIK_DEMO_MODE,
        "payment_demo_mode": settings.PAYMENT_DEMO_MODE,
        "network_monitor_enabled": settings.NETWORK_MONITOR_ENABLED,
    }
