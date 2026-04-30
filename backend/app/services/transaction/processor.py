"""
Celery task: process_transaction
Fetches an enriched transaction from DB, runs feature engineering + ML inference,
writes results back to the DB, logs the record, and raises alerts for high-risk events.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from celery import Celery

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(
    "fraud_processor",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Alert severity mapping  (risk_level → AlertSeverity)
# ---------------------------------------------------------------------------
RISK_TO_SEVERITY: dict[str, str] = {
    "LOW": "P3",
    "MEDIUM": "P2",
    "HIGH": "P1",
    "CRITICAL": "P0",
}


# ---------------------------------------------------------------------------
# Helper: build a plain-dict snapshot of a Transaction ORM row
# ---------------------------------------------------------------------------

def _orm_to_dict(tx: Any) -> dict[str, Any]:
    """Convert SQLAlchemy ORM Transaction row to a serialisable dict."""
    return {
        "id": str(tx.id),
        "card_id_hash": tx.card_id_hash,
        "merchant_id": tx.merchant_id,
        "merchant_name": tx.merchant_name,
        "mcc": tx.mcc,
        "mcc_risk_class": tx.mcc_risk_class,
        "amount": tx.amount,
        "currency": tx.currency,
        "channel": str(tx.channel.value) if tx.channel else "",
        "device_id": tx.device_id,
        "device_type": tx.device_type,
        "is_new_device": tx.is_new_device,
        "ip_address": tx.ip_address,
        "geo_lat": tx.geo_lat,
        "geo_lon": tx.geo_lon,
        "geo_country": tx.geo_country,
        "geo_city": tx.geo_city,
        "velocity_1h": tx.velocity_1h,
        "velocity_24h": tx.velocity_24h,
        "geo_distance_km": tx.geo_distance_km,
        "implied_speed_kmh": tx.implied_speed_kmh,
        "impossible_travel_flag": tx.impossible_travel_flag,
        "created_at": tx.created_at,
        # hour / day_of_week derived here for feature engineer
        "hour": tx.created_at.hour if tx.created_at else 0,
        "day_of_week": tx.created_at.weekday() if tx.created_at else 0,
        "timestamp": tx.created_at,
    }


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="fraud_processor.process_transaction",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_transaction(self: Any, transaction_id: str) -> dict[str, Any]:
    """
    Main Celery task: full fraud-score pipeline for a single transaction.

    Steps
    -----
    1. Fetch transaction row from DB (sync SQLAlchemy in Celery context).
    2. Retrieve velocity data from Redis.
    3. Run feature engineering (TransactionFeatureEngineer).
    4. Run ML inference (FraudScorer).
    5. Write results back to the Transaction DB row.
    6. Build & dispatch structured log (LogBuilder).
    7. Create FraudAlert if risk_level is HIGH or CRITICAL.

    Parameters
    ----------
    transaction_id:
        UUID string of the transaction to process.

    Returns
    -------
    dict with fraud_score, risk_level, predicted_class.
    """
    import asyncio

    try:
        result = asyncio.run(_process_async(transaction_id))
        return result
    except Exception as exc:
        logger.error("process_transaction[%s] failed: %s", transaction_id, exc, exc_info=True)
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"error": str(exc), "transaction_id": transaction_id}


async def _process_async(transaction_id: str) -> dict[str, Any]:
    """Async implementation of the processing pipeline."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select

    from app.db.models.transaction import Transaction, ProcessingStatusEnum
    from app.ml.features.engineer import TransactionFeatureEngineer
    from app.ml.inference.scorer import get_scorer
    from app.services.logging.log_builder import get_log_builder
    from app.services.transaction.velocity import get_velocity_store

    from app.db.session import DATABASE_URL

    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_factory() as session:
            # ----------------------------------------------------------
            # Step 1: Fetch transaction
            # ----------------------------------------------------------
            result = await session.execute(
                select(Transaction).where(Transaction.id == UUID(transaction_id))
            )
            tx: Optional[Transaction] = result.scalar_one_or_none()
            if tx is None:
                logger.error("process_transaction: transaction %s not found", transaction_id)
                return {"error": "not_found", "transaction_id": transaction_id}

            tx_dict = _orm_to_dict(tx)

            # ----------------------------------------------------------
            # Step 2: Get velocity data from Redis
            # ----------------------------------------------------------
            velocity_store = await get_velocity_store()
            velocity_data: dict[str, Any] = {}
            try:
                velocity_data = await velocity_store.get_velocity_counts(tx.card_id_hash)
            except Exception as vel_exc:
                logger.warning("process_transaction: velocity lookup failed — %s", vel_exc)
                velocity_data = {"1h": 0, "6h": 0, "24h": 0, "amount_sum_1h": 0.0,
                                  "unique_merchants_24h": 0, "unique_geo_clusters_24h": 0}

            # ----------------------------------------------------------
            # Step 3: Feature engineering
            # ----------------------------------------------------------
            engineer = TransactionFeatureEngineer()
            context: dict[str, Any] = {}
            feature_vector_obj = engineer.engineer(tx_dict, velocity_data, context)
            feature_array = feature_vector_obj.to_array()
            feature_names = feature_vector_obj.feature_names

            # Update transaction status to ENRICHED
            tx.processing_status = ProcessingStatusEnum.ENRICHED
            await session.commit()

            # ----------------------------------------------------------
            # Step 4: ML Inference
            # ----------------------------------------------------------
            scorer = get_scorer()
            score_result = scorer.score(feature_array, feature_names)

            # ----------------------------------------------------------
            # Step 5: Write results back to DB
            # ----------------------------------------------------------
            tx.fraud_score = score_result.fraud_score
            tx.risk_level = score_result.risk_level  # type: ignore[assignment]
            tx.predicted_class = score_result.predicted_class  # type: ignore[assignment]
            tx.shap_features = [
                {
                    "feature_name": sf.feature_name,
                    "shap_value": sf.shap_value,
                    "feature_value": sf.feature_value,
                }
                for sf in score_result.top_5_shap_features
            ]
            tx.model_version = score_result.model_version
            tx.inference_latency_ms = int(score_result.inference_latency_ms)
            tx.processing_status = ProcessingStatusEnum.SCORED
            tx.velocity_1h = velocity_data.get("1h", 0)
            tx.velocity_24h = velocity_data.get("24h", 0)
            await session.commit()

            # ----------------------------------------------------------
            # Step 6: Structured logging
            # ----------------------------------------------------------
            log_builder = get_log_builder()
            log_record = log_builder.build_and_dispatch(tx_dict, score_result)
            tx.processing_status = ProcessingStatusEnum.LOGGED
            await session.commit()

            # ----------------------------------------------------------
            # Step 7: Alert if HIGH or CRITICAL
            # ----------------------------------------------------------
            if score_result.risk_level in ("HIGH", "CRITICAL"):
                await _create_alert(session, tx, score_result, log_record)
                tx.processing_status = ProcessingStatusEnum.ALERTED
                await session.commit()

            return {
                "transaction_id": transaction_id,
                "fraud_score": score_result.fraud_score,
                "risk_level": score_result.risk_level,
                "predicted_class": score_result.predicted_class,
            }

    finally:
        await engine.dispose()


async def _create_alert(
    session: Any,
    tx: Any,
    score_result: Any,
    log_record: dict[str, Any],
) -> None:
    """Create a FraudAlert row for HIGH / CRITICAL transactions."""
    from app.db.models.alert import FraudAlert, AlertSeverityEnum

    severity_str = RISK_TO_SEVERITY.get(score_result.risk_level, "P2")
    severity = AlertSeverityEnum(severity_str)

    rule_triggers: list[str] = []
    if tx.impossible_travel_flag:
        rule_triggers.append("impossible_travel")
    if score_result.fraud_score >= 0.85:
        rule_triggers.append("ml_critical_score")
    elif score_result.fraud_score >= 0.65:
        rule_triggers.append("ml_high_score")
    if tx.is_new_device:
        rule_triggers.append("new_device")

    alert = FraudAlert(
        transaction_id=tx.id,
        card_id_hash=tx.card_id_hash,
        severity=severity,
        rule_triggers=rule_triggers,
    )
    session.add(alert)
    await session.flush()
    logger.info(
        "FraudAlert created: tx=%s severity=%s score=%.4f",
        str(tx.id),
        severity_str,
        score_result.fraud_score,
    )
