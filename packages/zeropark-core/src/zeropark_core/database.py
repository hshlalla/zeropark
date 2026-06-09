import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Default to async sqlite for local development
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./zeropark.db")

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    """Create all tables (Used for dev/testing, production should use Alembic)."""
    from zeropark_core.models_db import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db_session():
    """Dependency for FastAPI"""
    async with AsyncSessionLocal() as session:
        yield session
