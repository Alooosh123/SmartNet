from pathlib import Path
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.future import select

from config.settings import settings
from database.database import engine, Base, AsyncSessionLocal
from database import models
from services.auth_service import auth_service
from api.routes import auth, mikrotik, cards, client
from services.subscription_agent import subscription_agent_loop

from sqlalchemy import text

async def run_sqlite_migrations(conn):
    try:
        res = await conn.execute(text("PRAGMA table_info(registration_requests)"))
        cols = [row[1] for row in res.fetchall()]
        if "plan" not in cols:
            await conn.execute(text("ALTER TABLE registration_requests ADD COLUMN plan VARCHAR DEFAULT 'monthly'"))
        if "price" not in cols:
            await conn.execute(text("ALTER TABLE registration_requests ADD COLUMN price INTEGER DEFAULT 20"))
        if "receipt_image" not in cols:
            await conn.execute(text("ALTER TABLE registration_requests ADD COLUMN receipt_image VARCHAR"))

        res_c = await conn.execute(text("PRAGMA table_info(clients)"))
        cols_c = [row[1] for row in res_c.fetchall()]
        if "plan" not in cols_c:
            await conn.execute(text("ALTER TABLE clients ADD COLUMN plan VARCHAR DEFAULT 'monthly'"))
        if "can_reboot_network" not in cols_c:
            await conn.execute(text("ALTER TABLE clients ADD COLUMN can_reboot_network BOOLEAN DEFAULT 0"))
    except Exception as exc:
        print(f"Migration note: {exc}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await run_sqlite_migrations(conn)

    # Ensure initial admin exists
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(models.Admin).limit(1))
        if not result.scalars().first():
            hashed = auth_service.get_password_hash(settings.DASHBOARD_PASSWORD)
            session.add(models.Admin(username=settings.DASHBOARD_USERNAME, hashed_password=hashed))
            session.add(models.AuditLog(action="seed", performed_by="system", details="Created default admin"))
            await session.commit()

    stop_event = asyncio.Event()
    agent_task = asyncio.create_task(subscription_agent_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        await agent_task

app = FastAPI(title="SmartNet API", version="1.0.0", lifespan=lifespan)

# Allow local origins with credentials securely
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mount
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Uploads directory mount (receipts and custom cards)
uploads_dir = Path(__file__).resolve().parent / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
(uploads_dir / "receipts").mkdir(parents=True, exist_ok=True)
(uploads_dir / "cards").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Routers
app.include_router(auth.router)
app.include_router(mikrotik.router)
app.include_router(cards.router)
app.include_router(client.router)

@app.get("/")
def read_root():
    return {"message": "مرحباً بك في واجهة برمجة تطبيقات SmartNet", "status": "online"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "SmartNet", "version": "1.0.0"}

