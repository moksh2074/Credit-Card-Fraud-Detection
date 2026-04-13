from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_DIR = _BACKEND_DIR.parent
load_dotenv(_REPO_DIR / ".env", override=False)
load_dotenv(_BACKEND_DIR / ".env", override=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    from app.db.models.base import Base # ensure it imports all models
    from app.db.models.user import User
    from app.db.models.transaction import Transaction
    from app.db.models.alert import FraudAlert
    from app.db.models.audit_log import AuditLog
    from app.db.session import engine
    from app.ml.inference.scorer import get_scorer

    def _ensure_transaction_source_column(sync_conn) -> None:
        inspector = inspect(sync_conn)
        if "transactions" not in inspector.get_table_names():
            return

        dialect_name = sync_conn.dialect.name
        columns = {col["name"] for col in inspector.get_columns("transactions")}
        if "data_source" not in columns:
            sync_conn.execute(text("ALTER TABLE transactions ADD COLUMN data_source VARCHAR(32)"))
            logger.info("Added transactions.data_source column.")
        sync_conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_transactions_data_source ON transactions (data_source)")
        )

        synthetic_pattern_predicate = (
            "card_id_hash ~ '^card_[0-9]{6}$'"
            if dialect_name == "postgresql"
            else "card_id_hash GLOB 'card_[0-9][0-9][0-9][0-9][0-9][0-9]'"
        )

        # Backfill older synthetic rows so previously generated data remains visible
        # under synthetic-only frontend filters.
        sync_conn.execute(
            text(
                f"""
                UPDATE transactions
                SET data_source = 'SYNTHETIC_GENERATOR'
                WHERE (data_source IS NULL OR CAST(data_source AS TEXT) = '' OR CAST(data_source AS TEXT) = 'LEGACY_UNKNOWN')
                  AND {synthetic_pattern_predicate}
                """
            )
        )

        sync_conn.execute(
            text(
                """
                UPDATE transactions
                SET data_source = 'LEGACY_UNKNOWN'
                WHERE data_source IS NULL OR CAST(data_source AS TEXT) = ''
                """
            )
        )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_transaction_source_column)
    # Load the persisted model artifact once during startup (no training on boot).
    get_scorer()
    yield
    # Shutdown actions

app = FastAPI(
    title="Credit Card Fraud Detection Platform",
    description="API for the Real-time Fraud Detection System",
    version="1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
try:
    from app.api.routes import auth, transactions, alerts, analytics, generator, stream
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["Transactions"])
    app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
    app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
    app.include_router(generator.router, prefix="/api/v1/generator", tags=["Generator (Admin)"])
    app.include_router(stream.router, prefix="/api/v1/stream", tags=["Real-time Stream"])
except ImportError as e:
    import logging
    logging.warning(f"Waiting for route modules to be implemented: {e}")

@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "API is running"}
