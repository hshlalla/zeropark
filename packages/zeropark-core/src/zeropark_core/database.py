import os
from pathlib import Path
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Default to async sqlite for local development.
# Scaling note: this app is designed for SINGLE-INSTANCE deployment per client
# (see docs/02-progress/backlog.md). SQLite + WAL handles hundreds of concurrent
# users fine. To run MULTIPLE gateway instances behind a load balancer, set
# DATABASE_URL=postgresql+asyncpg://... — no code change needed — AND externalize
# the in-memory UsageTracker/JobManager to Redis.
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{(_ROOT_DIR / 'zeropark.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

if _IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        """Tune SQLite for concurrent single-instance use. WAL lets readers and
        a writer proceed at once; busy_timeout waits on a brief lock instead of
        raising 'database is locked'."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")       # concurrent readers + 1 writer
        cur.execute("PRAGMA busy_timeout=5000")      # wait up to 5s on lock contention
        cur.execute("PRAGMA synchronous=NORMAL")     # durable under WAL, much faster
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

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
