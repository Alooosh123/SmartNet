from typing import AsyncGenerator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from config.settings import settings


def get_database_url() -> str:
    """Resolve a SQLAlchemy URL without interpolating passwords into a URL string."""
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    if settings.DATABASE_BACKEND == "mariadb":
        return URL.create(
            "mysql+asyncmy",
            username=settings.MARIADB_USER,
            password=settings.MARIADB_PASSWORD,
            host=settings.MARIADB_HOST,
            port=settings.MARIADB_PORT,
            database=settings.MARIADB_DATABASE,
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)
    return "sqlite+aiosqlite:///./smartnet.db"


DATABASE_URL = get_database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=not DATABASE_URL.startswith("sqlite"),
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
