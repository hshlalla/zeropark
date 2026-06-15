import os
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Default to async sqlite for local development
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{(_ROOT_DIR / 'zeropark.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Columns added after a table already shipped. create_all does NOT alter
# existing tables, so we apply best-effort ALTERs for dev sqlite databases.
# (Production should use Alembic migrations.)
_DEV_MIGRATIONS = [
    "ALTER TABLE chat_sessions ADD COLUMN user_id VARCHAR",
    "ALTER TABLE chat_sessions ADD COLUMN app_id VARCHAR",
    "ALTER TABLE chat_sessions ADD COLUMN updated_at DATETIME",
    "ALTER TABLE chat_sessions ADD COLUMN summary VARCHAR",
    "ALTER TABLE chat_sessions ADD COLUMN variables VARCHAR",
    "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0 NOT NULL",
]


async def init_db():
    """Create all tables (Used for dev/testing, production should use Alembic)."""
    from sqlalchemy import text
    from zeropark_core.models_db import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for statement in _DEV_MIGRATIONS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
        except Exception:
            pass  # column already exists

async def get_db_session():
    """Dependency for FastAPI"""
    async with AsyncSessionLocal() as session:
        yield session
