import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_SQLITE_ASYNC_PREFIX = "sqlite+aiosqlite:///"
_POSTGRES_PREFIX = "postgresql+asyncpg://"
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_DIR = _BACKEND_DIR.parent
_FALLBACK_RUNTIME_DB = (_BACKEND_DIR / "runtime" / "fraud_runtime.db").resolve()

logger = logging.getLogger(__name__)


def _is_sqlite_path_writable(path: Path) -> bool:
    connection: Optional[sqlite3.Connection] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path.as_posix(), timeout=5.0)
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("CREATE TABLE IF NOT EXISTS __fd_db_healthcheck (id INTEGER PRIMARY KEY, touched_at TEXT)")
        cursor.execute("INSERT INTO __fd_db_healthcheck (touched_at) VALUES (datetime('now'))")
        cursor.execute(
            "DELETE FROM __fd_db_healthcheck WHERE id = "
            "(SELECT id FROM __fd_db_healthcheck ORDER BY id DESC LIMIT 1)"
        )
        connection.commit()
        return True
    except sqlite3.Error as exc:
        logger.warning("SQLite path failed health check (%s): %s", path, exc)
        return False
    finally:
        if connection is not None:
            connection.close()


def _resolve_sqlite_path(raw_sqlite_path: str) -> Path:
    sqlite_path = Path(raw_sqlite_path)
    if not sqlite_path.is_absolute():
        sqlite_path = (_BACKEND_DIR / sqlite_path).resolve()
    return sqlite_path


def _pick_default_sqlite_path() -> Path:
    env_path = os.getenv("SQLITE_DB_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path).expanduser().resolve())
    candidates.extend(
        [
            (_BACKEND_DIR / "fraud.db").resolve(),
            (_REPO_DIR / "fraud.db").resolve(),
            _FALLBACK_RUNTIME_DB,
        ]
    )

    for candidate in candidates:
        if _is_sqlite_path_writable(candidate):
            logger.info("Using SQLite database file: %s", candidate)
            return candidate

    raise RuntimeError("Unable to find a writable SQLite database path.")


def _resolve_database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        sqlite_path = _pick_default_sqlite_path()
        return f"{_SQLITE_ASYNC_PREFIX}{sqlite_path.as_posix()}"

    if configured_url == "sqlite+aiosqlite:///:memory:":
        return configured_url

    if configured_url.startswith(_SQLITE_ASYNC_PREFIX):
        sqlite_path = _resolve_sqlite_path(configured_url[len(_SQLITE_ASYNC_PREFIX):])
        if not _is_sqlite_path_writable(sqlite_path):
            logger.warning(
                "Configured SQLite path is not writable (%s). Falling back to runtime DB.",
                sqlite_path,
            )
            sqlite_path = _FALLBACK_RUNTIME_DB
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"{_SQLITE_ASYNC_PREFIX}{sqlite_path.as_posix()}"

    # Normalize common PostgreSQL URL variants to asyncpg driver so local setup
    # with pgAdmin tutorials (often postgresql://) works without hidden breakage.
    normalized = configured_url.strip()
    if normalized.startswith("postgres://"):
        normalized = f"postgresql://{normalized[len('postgres://'):]}"
    if normalized.startswith("postgresql://"):
        normalized = f"{_POSTGRES_PREFIX}{normalized[len('postgresql://'):]}"
    if normalized.startswith("postgresql+psycopg://"):
        normalized = f"{_POSTGRES_PREFIX}{normalized[len('postgresql+psycopg://'):]}"
    if normalized.startswith("postgresql+psycopg2://"):
        normalized = f"{_POSTGRES_PREFIX}{normalized[len('postgresql+psycopg2://'):]}"

    return normalized


DATABASE_URL = _resolve_database_url()
IS_SQLITE = DATABASE_URL.startswith(_SQLITE_ASYNC_PREFIX)
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() == "true"

engine = create_async_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    pool_pre_ping=True,
    connect_args={"timeout": 30} if IS_SQLITE else {},
)

if IS_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
