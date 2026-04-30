from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, and_, cast, String
from typing import Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
import logging
import csv
import io

from .schemas import TransactionIngestRequest, TransactionResponse, PaginatedTransactionResponse
from app.db.models.transaction import (
    Transaction,
    RiskLevelEnum,
    ChannelEnum,
    PredictedClassEnum,
    ProcessingStatusEnum,
    TransactionDataSourceEnum,
)
from app.db.models.alert import FraudAlert, AlertSeverityEnum, AlertStatusEnum
from app.db.session import get_db
from app.ml.features.engineer import TransactionFeatureEngineer
from app.ml.inference.scorer import get_scorer
from app.core.broadcaster import broadcaster
from app.core.services import service_manager
from app.services.logging.log_builder import get_log_builder

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize ML components
feature_engineer = TransactionFeatureEngineer()
scorer = get_scorer()


def _normalize_risk_level(value: Any) -> RiskLevelEnum:
    try:
        return RiskLevelEnum[str(value).upper()]
    except Exception:
        return RiskLevelEnum.LOW


def _normalize_predicted_class(value: Any) -> PredictedClassEnum:
    try:
        return PredictedClassEnum[str(value).upper()]
    except Exception:
        return PredictedClassEnum.LEGITIMATE


def _map_alert_severity(risk_level: RiskLevelEnum, fraud_score: float) -> Optional[AlertSeverityEnum]:
    if risk_level == RiskLevelEnum.CRITICAL:
        return AlertSeverityEnum.P0
    if risk_level == RiskLevelEnum.HIGH:
        return AlertSeverityEnum.P1
    if risk_level == RiskLevelEnum.MEDIUM and fraud_score >= 0.70:
        return AlertSeverityEnum.P2
    return None


def _map_scenario_severity(scenario: Optional[str]) -> Optional[AlertSeverityEnum]:
    if not scenario:
        return None

    normalized = scenario.strip().lower()
    scenario_map = {
        "high_value_cnp": AlertSeverityEnum.P0,
        "impossible_travel": AlertSeverityEnum.P1,
        "new_device_fraud": AlertSeverityEnum.P1,
        "velocity_burst": AlertSeverityEnum.P2,
        "card_testing": AlertSeverityEnum.P2,
    }
    return scenario_map.get(normalized)


def _normalize_data_source(value: Any) -> TransactionDataSourceEnum:
    if isinstance(value, TransactionDataSourceEnum):
        return value
    try:
        normalized = str(value).strip().upper()
        if normalized.startswith("TRANSACTIONDATASOURCEENUM."):
            normalized = normalized.split(".", 1)[1]
        return TransactionDataSourceEnum[normalized]
    except Exception:
        return TransactionDataSourceEnum.SYNTHETIC_GENERATOR


def _resolve_synthetic_card_index(card_id_hash: str) -> Optional[int]:
    if not isinstance(card_id_hash, str):
        return None
    normalized = card_id_hash.strip().lower()
    if not normalized.startswith("card_"):
        return None
    suffix = normalized.split("card_", 1)[1]
    if len(suffix) != 6 or not suffix.isdigit():
        return None
    return int(suffix)


async def _build_velocity_and_context(
    db: AsyncSession,
    *,
    card_id_hash: str,
    generated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    one_hour_ago = generated_at - timedelta(hours=1)
    six_hours_ago = generated_at - timedelta(hours=6)
    day_ago = generated_at - timedelta(hours=24)

    count_1h_result = await db.execute(
        select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0.0))
        .where(Transaction.card_id_hash == card_id_hash)
        .where(Transaction.created_at >= one_hour_ago)
        .where(Transaction.created_at <= generated_at)
    )
    tx_count_1h, amount_sum_1h = count_1h_result.one()

    count_6h_result = await db.execute(
        select(func.count(Transaction.id))
        .where(Transaction.card_id_hash == card_id_hash)
        .where(Transaction.created_at >= six_hours_ago)
        .where(Transaction.created_at <= generated_at)
    )
    tx_count_6h = count_6h_result.scalar() or 0

    count_24h_result = await db.execute(
        select(func.count(Transaction.id))
        .where(Transaction.card_id_hash == card_id_hash)
        .where(Transaction.created_at >= day_ago)
        .where(Transaction.created_at <= generated_at)
    )
    tx_count_24h = count_24h_result.scalar() or 0

    unique_merchants_result = await db.execute(
        select(func.count(func.distinct(Transaction.merchant_id)))
        .where(Transaction.card_id_hash == card_id_hash)
        .where(Transaction.created_at >= day_ago)
        .where(Transaction.created_at <= generated_at)
    )
    unique_merchants_24h = unique_merchants_result.scalar() or 0

    unique_geo_clusters_result = await db.execute(
        select(func.count(func.distinct(Transaction.geo_city)))
        .where(Transaction.card_id_hash == card_id_hash)
        .where(Transaction.created_at >= day_ago)
        .where(Transaction.created_at <= generated_at)
        .where(Transaction.geo_city.is_not(None))
    )
    unique_geo_clusters_24h = unique_geo_clusters_result.scalar() or 0

    last_tx_result = await db.execute(
        select(
            Transaction.geo_lat,
            Transaction.geo_lon,
            Transaction.created_at,
            Transaction.geo_country,
        )
        .where(Transaction.card_id_hash == card_id_hash)
        .order_by(desc(Transaction.created_at), desc(Transaction.id))
        .limit(1)
    )
    last_tx = last_tx_result.first()

    velocity = {
        "1h": int(tx_count_1h or 0),
        "6h": int(tx_count_6h or 0),
        "24h": int(tx_count_24h or 0),
        "amount_sum_1h": float(amount_sum_1h or 0.0),
        "unique_merchants_24h": int(unique_merchants_24h or 0),
        "unique_geo_clusters_24h": int(unique_geo_clusters_24h or 0),
    }

    context: dict[str, Any] = {}
    if last_tx:
        last_lat, last_lon, last_created_at, last_country = last_tx
        if last_lat is not None and last_lon is not None:
            context["last_tx_lat"] = float(last_lat)
            context["last_tx_lon"] = float(last_lon)
        if last_created_at is not None:
            context["last_tx_timestamp"] = float(last_created_at.timestamp())
        if last_country:
            context["home_country"] = str(last_country)

    return velocity, context

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_transaction(transaction_in: TransactionIngestRequest, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        generated_at = transaction_in.timestamp
        if generated_at.tzinfo is not None:
            generated_at = generated_at.astimezone(timezone.utc).replace(tzinfo=None)
        now_utc_naive = datetime.utcnow()
        if generated_at > now_utc_naive + timedelta(minutes=2):
            # Guard against client clock drift causing future-dated rows that pin the list order.
            generated_at = now_utc_naive

        incoming_data_source = _normalize_data_source(transaction_in.data_source)
        if incoming_data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR:
            card_index = _resolve_synthetic_card_index(transaction_in.card_id_hash)
            profile_count = service_manager.get_generator().cardholder_profile_count
            if card_index is None or card_index >= profile_count:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"card_id_hash must belong to generator pool [0..{profile_count - 1}] for synthetic source.",
                )

        velocity_context, feature_context = await _build_velocity_and_context(
            db,
            card_id_hash=transaction_in.card_id_hash,
            generated_at=generated_at,
        )

        # 1. Feature Engineering
        tx_payload = transaction_in.dict()
        tx_payload["timestamp"] = generated_at
        tx_payload["hour"] = generated_at.hour
        tx_payload["day_of_week"] = generated_at.weekday()
        fv = feature_engineer.engineer(tx_payload, velocity_context, feature_context)
        
        # 2. ML Scoring
        score_result = scorer.score(fv.to_array(), fv.feature_names)
        
        risk_level = _normalize_risk_level(score_result.risk_level)
        predicted_class = _normalize_predicted_class(score_result.predicted_class)
        should_flag = predicted_class == PredictedClassEnum.FRAUD or risk_level in (
            RiskLevelEnum.HIGH,
            RiskLevelEnum.CRITICAL,
        )
        alert_severity = _map_alert_severity(risk_level, float(score_result.fraud_score or 0.0)) if should_flag else None

        scenario_severity = _map_scenario_severity(transaction_in.fraud_scenario)
        if scenario_severity:
            should_flag = True
            alert_severity = scenario_severity
            if predicted_class != PredictedClassEnum.FRAUD:
                predicted_class = PredictedClassEnum.FRAUD
            if risk_level in (RiskLevelEnum.LOW, RiskLevelEnum.MEDIUM):
                risk_level = RiskLevelEnum.HIGH if scenario_severity in (AlertSeverityEnum.P0, AlertSeverityEnum.P1) else RiskLevelEnum.MEDIUM

        decision_reasons = []
        if predicted_class == PredictedClassEnum.FRAUD:
            decision_reasons.append("ml_predicted_fraud")
        if risk_level in (RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL):
            decision_reasons.append(f"risk_level_{risk_level.value.lower()}")
        if transaction_in.fraud_scenario:
            decision_reasons.append(f"scenario_{transaction_in.fraud_scenario}")

        # 3. Persistence
        new_tx = Transaction(
            id=uuid4(),
            card_id_hash=transaction_in.card_id_hash,
            merchant_id=transaction_in.merchant_id,
            merchant_name=transaction_in.merchant_name,
            mcc=transaction_in.mcc,
            amount=transaction_in.amount,
            currency=transaction_in.currency,
            channel=transaction_in.channel,
            device_id=transaction_in.device_id,
            device_type=transaction_in.device_type,
            is_new_device=transaction_in.is_new_device,
            ip_address=transaction_in.ip_address,
            geo_lat=transaction_in.geo_lat,
            geo_lon=transaction_in.geo_lon,
            geo_country=transaction_in.geo_country,
            geo_city=transaction_in.geo_city,
            velocity_1h=int(fv.tx_count_1h),
            velocity_24h=int(fv.tx_count_24h),
            geo_distance_km=float(fv.geo_distance_from_last_km),
            implied_speed_kmh=float(fv.implied_speed_kmh),
            impossible_travel_flag=bool(fv.impossible_travel),
            mcc_risk_class="HIGH" if int(fv.is_high_risk_mcc) == 1 else "LOW",
            
            fraud_score=score_result.fraud_score,
            risk_level=risk_level,
            predicted_class=predicted_class,
            shap_features=[
                {"name": f.feature_name, "value": f.shap_value} 
                for f in score_result.top_5_shap_features
            ] if hasattr(score_result, 'top_5_shap_features') else [],
            model_version=score_result.model_version,
            inference_latency_ms=int(score_result.inference_latency_ms),
            data_source=incoming_data_source,
            processing_status=ProcessingStatusEnum.ALERTED if alert_severity else ProcessingStatusEnum.SCORED,
            created_at=generated_at,
        )
        
        db.add(new_tx)
        await db.flush()
        
        # 4. Alert Generation (all actionable fraud outcomes)
        new_alert: Optional[FraudAlert] = None
        if alert_severity:
            new_alert = FraudAlert(
                transaction_id=new_tx.id,
                card_id_hash=new_tx.card_id_hash,
                severity=alert_severity,
                status=AlertStatusEnum.NEW,
                rule_triggers={
                    "ml_score": score_result.fraud_score,
                    "risk_level": risk_level.value,
                    "predicted_class": predicted_class.value,
                    "scenario": transaction_in.fraud_scenario,
                    "decision_reasons": decision_reasons,
                },
                created_at=generated_at,
                updated_at=generated_at,
            )
            db.add(new_alert)

        await db.commit()
        await db.refresh(new_tx)
        if new_alert:
            await db.refresh(new_alert)

        # 4.5 Structured fraud log dispatch for flagged outcomes.
        # Local sink remains primary; S3 archival is best-effort and never blocks ingestion.
        if new_alert:
            try:
                log_builder = get_log_builder()
                tx_snapshot = {
                    "id": str(new_tx.id),
                    "card_id_hash": new_tx.card_id_hash,
                    "merchant_id": new_tx.merchant_id,
                    "merchant_name": new_tx.merchant_name,
                    "mcc": new_tx.mcc,
                    "amount": new_tx.amount,
                    "currency": new_tx.currency,
                    "channel": new_tx.channel.value if new_tx.channel else "",
                    "created_at": new_tx.created_at,
                    "geo_lat": new_tx.geo_lat,
                    "geo_lon": new_tx.geo_lon,
                    "geo_country": new_tx.geo_country,
                    "geo_city": new_tx.geo_city,
                    "device_id": new_tx.device_id,
                    "device_type": new_tx.device_type,
                    "is_new_device": new_tx.is_new_device,
                    "ip_address": new_tx.ip_address,
                    "velocity_1h": new_tx.velocity_1h,
                    "velocity_24h": new_tx.velocity_24h,
                    "geo_distance_km": new_tx.geo_distance_km,
                    "implied_speed_kmh": new_tx.implied_speed_kmh,
                    "impossible_travel_flag": new_tx.impossible_travel_flag,
                }
                log_builder.build_and_dispatch(tx_snapshot, score_result)
            except Exception as log_exc:
                logger.warning("Structured log dispatch failed for tx=%s: %s", new_tx.id, log_exc)

        # 5. Broadcast to SSE
        broadcast_msg = {
            "event_type": "transaction_ingested",
            "transaction_id": str(new_tx.id),
            "amount": new_tx.amount,
            "currency": new_tx.currency,
            "risk_level": new_tx.risk_level.value if new_tx.risk_level else RiskLevelEnum.LOW.value,
            "fraud_score": new_tx.fraud_score,
            "merchant_name": new_tx.merchant_name,
            "timestamp": new_tx.created_at.isoformat(),
            "alert_generated": bool(new_alert),
            "alert_id": str(new_alert.id) if new_alert else None,
        }
        await broadcaster.broadcast(broadcast_msg)

        return {"message": "Transaction processed", "transaction_id": str(new_tx.id), "risk_level": risk_level.value}
    except Exception as e:
        logger.error(f"Error ingesting transaction: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {str(e)}")


@router.get("/customer-verification")
async def verify_synthetic_customer_pool(
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        generator = service_manager.get_generator()
        expected_count = int(generator.cardholder_profile_count)
        expected_cards = {f"card_{idx:06d}" for idx in range(expected_count)}

        result = await db.execute(
            select(Transaction.card_id_hash)
            .where(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)
            .distinct()
        )
        observed_cards = {
            str(row[0]).strip().lower()
            for row in result.all()
            if row[0] is not None and str(row[0]).strip()
        }

        unexpected_cards = sorted(observed_cards - expected_cards)
        missing_cards = sorted(expected_cards - observed_cards)
        return {
            "expected_customer_pool_size": expected_count,
            "observed_synthetic_customers": len(observed_cards),
            "unexpected_customer_count": len(unexpected_cards),
            "unexpected_customer_samples": unexpected_cards[:20],
            "missing_customer_count": len(missing_cards),
            "missing_customer_samples": missing_cards[:20],
            "is_pool_consistent": len(unexpected_cards) == 0,
        }
    except Exception as e:
        logger.error(f"Error verifying synthetic customer pool: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.get("/", response_model=PaginatedTransactionResponse)
async def get_transactions(
    risk_level: Optional[RiskLevelEnum] = None,
    channel: Optional[ChannelEnum] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
    synthetic_only: bool = Query(True),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        filters = []
        if risk_level:
            filters.append(Transaction.risk_level == risk_level)
        if channel:
            filters.append(Transaction.channel == channel)
        if start_date:
            filters.append(Transaction.created_at >= start_date)
        if end_date:
            filters.append(Transaction.created_at <= end_date)
        if search:
            search_pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Transaction.card_id_hash.ilike(search_pattern),
                    Transaction.merchant_name.ilike(search_pattern),
                    Transaction.merchant_id.ilike(search_pattern),
                    cast(Transaction.id, String).ilike(search_pattern),
                )
            )
        if synthetic_only:
            filters.append(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)
        
        query = select(Transaction).where(*filters)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        flagged_filter = or_(
            Transaction.processing_status == ProcessingStatusEnum.ALERTED,
            Transaction.predicted_class == PredictedClassEnum.FRAUD,
            Transaction.risk_level.in_([RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL]),
        )
        approved_filter = or_(
            and_(
                Transaction.processing_status == ProcessingStatusEnum.RESOLVED,
                Transaction.predicted_class != PredictedClassEnum.FRAUD,
            ),
            and_(
                Transaction.predicted_class != PredictedClassEnum.FRAUD,
                Transaction.risk_level.in_([RiskLevelEnum.LOW, RiskLevelEnum.MEDIUM]),
            ),
        )

        flagged_result = await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(*filters)
            .where(flagged_filter)
        )
        flagged_count = flagged_result.scalar() or 0

        approved_result = await db.execute(
            select(func.count())
            .select_from(Transaction)
            .where(*filters)
            .where(approved_filter)
        )
        approved_count = approved_result.scalar() or 0
        
        # Paginate and sort newest-first with deterministic tie-breaker.
        query = query.order_by(desc(Transaction.created_at), desc(Transaction.id)).offset((page - 1) * size).limit(size)
        result = await db.execute(query)
        items = result.scalars().all()
        
        return PaginatedTransactionResponse(
            total=total,
            page=page,
            size=size,
            flagged_count=flagged_count,
            approved_count=approved_count,
            items=items,
        )
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/export")
async def export_transactions_csv(
    risk_level: Optional[RiskLevelEnum] = None,
    channel: Optional[ChannelEnum] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        query = select(Transaction)

        if risk_level:
            query = query.where(Transaction.risk_level == risk_level)
        if channel:
            query = query.where(Transaction.channel == channel)
        if start_date:
            query = query.where(Transaction.created_at >= start_date)
        if end_date:
            query = query.where(Transaction.created_at <= end_date)
        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Transaction.card_id_hash.ilike(search_pattern),
                    Transaction.merchant_name.ilike(search_pattern),
                    Transaction.merchant_id.ilike(search_pattern),
                    cast(Transaction.id, String).ilike(search_pattern),
                )
            )
        if synthetic_only:
            query = query.where(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)

        query = query.order_by(desc(Transaction.created_at), desc(Transaction.id))
        result = await db.execute(query)
        transactions = result.scalars().all()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "transaction_id",
            "created_at",
            "amount",
            "currency",
            "merchant_name",
            "merchant_id",
            "mcc",
            "channel",
            "device_id",
            "risk_level",
            "fraud_score",
            "processing_status",
            "card_id_hash",
        ])

        for tx in transactions:
            writer.writerow([
                str(tx.id),
                tx.created_at.isoformat() if tx.created_at else "",
                tx.amount,
                tx.currency,
                tx.merchant_name or "",
                tx.merchant_id,
                tx.mcc,
                tx.channel.value if tx.channel else "",
                tx.device_id or "",
                tx.risk_level.value if tx.risk_level else "",
                tx.fraud_score if tx.fraud_score is not None else "",
                tx.processing_status.value if tx.processing_status else "",
                tx.card_id_hash,
            ])

        csv_content = buffer.getvalue()
        buffer.close()

        filename = f"transactions_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
        )
    except Exception as e:
        logger.error(f"Error exporting transactions CSV: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

@router.get("/{id}", response_model=TransactionResponse)
async def get_transaction(id: UUID, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        result = await db.execute(select(Transaction).where(Transaction.id == id))
        transaction = result.scalars().first()
        if not transaction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
        return transaction
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transaction {id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
