from database.database import engine, AsyncSessionLocal, Base, get_db

async def init_db() -> None:
    from database.models import Admin, CardBatch, Card, RegistrationRequest, Client, ChatMessage, AuditLog  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

