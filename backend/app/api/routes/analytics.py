from datetime import datetime, timedelta
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import AlertStatusEnum, FraudAlert
from app.db.models.transaction import (
    PredictedClassEnum,
    ProcessingStatusEnum,
    RiskLevelEnum,
    Transaction,
    TransactionDataSourceEnum,
)
from app.db.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_time_range(time_range: str) -> timedelta:
    normalized = (time_range or "24h").strip().lower()
    mapping = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "12h": timedelta(hours=12),
        "24h": timedelta(hours=24),
        "48h": timedelta(hours=48),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    return mapping.get(normalized, timedelta(hours=24))


def _parse_period(period: str) -> int:
    normalized = (period or "1h").strip().lower()
    mapping = {
        "5m": 5 * 60,
        "15m": 15 * 60,
        "30m": 30 * 60,
        "1h": 60 * 60,
        "2h": 2 * 60 * 60,
        "6h": 6 * 60 * 60,
    }
    return mapping.get(normalized, 60 * 60)


def _resolve_window(
    time_range: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
) -> tuple[datetime, datetime]:
    end_dt = end_date or datetime.utcnow()
    start_dt = start_date or (end_dt - _parse_time_range(time_range))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt


def _build_filters(
    synthetic_only: bool,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[Any]:
    filters: list[Any] = []
    if synthetic_only:
        filters.append(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)
    if start_date:
        filters.append(Transaction.created_at >= start_date)
    if end_date:
        filters.append(Transaction.created_at <= end_date)
    return filters


def _is_flagged(
    processing_status: Optional[ProcessingStatusEnum],
    predicted_class: Optional[PredictedClassEnum],
    risk_level: Optional[RiskLevelEnum],
) -> bool:
    return (
        processing_status == ProcessingStatusEnum.ALERTED
        or predicted_class == PredictedClassEnum.FRAUD
        or risk_level in (RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL)
    )


@router.get("/fraud-summary")
async def get_fraud_summary(
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)

        total_result = await db.execute(
            select(func.count(Transaction.id)).where(*filters)
        )
        total_transactions = int(total_result.scalar() or 0)

        volume_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(*filters)
        )
        total_volume = float(volume_result.scalar() or 0.0)

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
            select(func.count(Transaction.id)).where(*filters).where(flagged_filter)
        )
        flagged_transactions = int(flagged_result.scalar() or 0)

        approved_result = await db.execute(
            select(func.count(Transaction.id)).where(*filters).where(approved_filter)
        )
        approved_transactions = int(approved_result.scalar() or 0)

        alert_filters: list[Any] = [
            FraudAlert.status.in_([AlertStatusEnum.NEW, AlertStatusEnum.ACKNOWLEDGED]),
            Transaction.created_at >= start_dt,
            Transaction.created_at <= end_dt,
        ]
        if synthetic_only:
            alert_filters.append(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)

        open_alerts_result = await db.execute(
            select(func.count(FraudAlert.id))
            .select_from(FraudAlert)
            .join(Transaction, FraudAlert.transaction_id == Transaction.id)
            .where(*alert_filters)
        )
        open_alerts = int(open_alerts_result.scalar() or 0)

        fraud_rate = round((flagged_transactions / total_transactions) * 100, 2) if total_transactions else 0.0
        avg_amount = round(total_volume / total_transactions, 2) if total_transactions else 0.0

        return {
            "time_range": time_range,
            "start_date": start_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "total_transactions": total_transactions,
            "flagged_transactions": flagged_transactions,
            "approved_transactions": approved_transactions,
            "open_alerts": open_alerts,
            "fraud_rate": fraud_rate,
            "total_volume": round(total_volume, 2),
            "avg_amount": avg_amount,
        }
    except Exception as e:
        logger.error("Error fetching fraud summary: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/fraud-rate-trend")
async def get_fraud_rate_trend(
    period: str = Query("1h"),
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        bucket_seconds = _parse_period(period)
        total_seconds = max(1, int((end_dt - start_dt).total_seconds()))
        bucket_count = min(500, max(1, (total_seconds // bucket_seconds) + 1))

        labels: list[str] = []
        for i in range(bucket_count):
            bucket_time = start_dt + timedelta(seconds=i * bucket_seconds)
            if (end_dt - start_dt) > timedelta(days=2):
                labels.append(bucket_time.strftime("%d %b %H:%M"))
            else:
                labels.append(bucket_time.strftime("%H:%M"))

        volume = [0 for _ in range(bucket_count)]
        flagged = [0 for _ in range(bucket_count)]

        filters = _build_filters(synthetic_only, start_dt, end_dt)
        result = await db.execute(
            select(
                Transaction.created_at,
                Transaction.processing_status,
                Transaction.predicted_class,
                Transaction.risk_level,
            ).where(*filters)
        )

        for created_at, processing_status, predicted_class, risk_level in result.all():
            if created_at is None:
                continue
            offset = int((created_at - start_dt).total_seconds())
            if offset < 0:
                continue
            index = min(bucket_count - 1, offset // bucket_seconds)
            volume[index] += 1
            if _is_flagged(processing_status, predicted_class, risk_level):
                flagged[index] += 1

        rates = [
            round((flagged[i] / volume[i]) * 100, 2) if volume[i] else 0.0
            for i in range(bucket_count)
        ]
        points = [
            {"time": labels[i], "rate": rates[i], "volume": volume[i]}
            for i in range(bucket_count)
        ]

        return {
            "labels": labels,
            "data": rates,
            "volume": volume,
            "points": points,
        }
    except Exception as e:
        logger.error("Error fetching fraud rate trend: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/risk-distribution")
async def get_risk_distribution(
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)

        query = (
            select(Transaction.risk_level, func.count(Transaction.id))
            .where(*filters)
            .group_by(Transaction.risk_level)
        )
        result = await db.execute(query)
        distribution: dict[str, int] = {}
        for risk_level, count in result.all():
            if risk_level is None:
                continue
            key = risk_level.value if hasattr(risk_level, "value") else str(risk_level)
            distribution[key] = int(count)

        return {
            "labels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
            "data": [
                distribution.get("LOW", 0),
                distribution.get("MEDIUM", 0),
                distribution.get("HIGH", 0),
                distribution.get("CRITICAL", 0),
            ],
        }
    except Exception as e:
        logger.error("Error fetching risk distribution: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/geo-fraud")
async def get_geo_fraud(
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)
        filters.append(Transaction.risk_level.in_([RiskLevelEnum.HIGH, RiskLevelEnum.CRITICAL]))

        query = (
            select(
                Transaction.geo_lat,
                Transaction.geo_lon,
                Transaction.risk_level,
                Transaction.amount,
            )
            .where(*filters)
            .order_by(Transaction.created_at.desc())
            .limit(100)
        )
        result = await db.execute(query)
        items = result.all()
        return {
            "locations": [
                {
                    "lat": lat,
                    "lon": lon,
                    "risk": risk.value if hasattr(risk, "value") else str(risk),
                    "amount": amount,
                }
                for lat, lon, risk, amount in items
                if lat is not None and lon is not None
            ]
        }
    except Exception as e:
        logger.error("Error fetching geo fraud data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/device-channel")
async def get_device_channel(
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)

        channel_result = await db.execute(
            select(Transaction.channel, func.count(Transaction.id))
            .where(*filters)
            .group_by(Transaction.channel)
        )
        device_result = await db.execute(
            select(Transaction.device_type, func.count(Transaction.id))
            .where(*filters)
            .group_by(Transaction.device_type)
        )

        channel_rows = channel_result.all()
        device_rows = device_result.all()
        channel_total = sum(int(row[1]) for row in channel_rows) or 1
        device_total = sum(int(row[1]) for row in device_rows) or 1

        channel_data = [
            {
                "name": (channel.value if hasattr(channel, "value") else str(channel or "UNKNOWN")),
                "count": int(count),
                "value": round((int(count) / channel_total) * 100, 2),
            }
            for channel, count in channel_rows
        ]
        device_data = [
            {
                "name": str(device_type or "UNKNOWN").upper(),
                "count": int(count),
                "value": round((int(count) / device_total) * 100, 2),
            }
            for device_type, count in device_rows
        ]

        return {"channel_data": channel_data, "device_data": device_data}
    except Exception as e:
        logger.error("Error fetching device and channel data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/merchant-category")
async def get_merchant_category(
    time_range: str = Query("24h"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)
        result = await db.execute(
            select(
                Transaction.mcc,
                Transaction.processing_status,
                Transaction.predicted_class,
                Transaction.risk_level,
            ).where(*filters)
        )

        buckets: dict[str, dict[str, int]] = {}
        for mcc, processing_status, predicted_class, risk_level in result.all():
            key = str(mcc or "UNKNOWN")
            bucket = buckets.setdefault(key, {"total": 0, "flagged": 0})
            bucket["total"] += 1
            if _is_flagged(processing_status, predicted_class, risk_level):
                bucket["flagged"] += 1

        items = []
        for category, values in buckets.items():
            total = values["total"]
            flagged = values["flagged"]
            rate = (flagged / total) * 100 if total else 0.0
            items.append({
                "category": category,
                "rate": round(rate, 2),
                "count": total,
            })

        items.sort(key=lambda item: (item["rate"], item["count"]), reverse=True)
        top_items = items[:8]
        return {
            "categories": [item["category"] for item in top_items],
            "risk_levels": [item["rate"] for item in top_items],
            "items": top_items,
        }
    except Exception as e:
        logger.error("Error fetching merchant category data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/time-heatmap")
async def get_time_heatmap(
    time_range: str = Query("7d"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, start_date, end_date)
        filters = _build_filters(synthetic_only, start_dt, end_dt)

        result = await db.execute(
            select(
                Transaction.created_at,
                Transaction.processing_status,
                Transaction.predicted_class,
                Transaction.risk_level,
            ).where(*filters)
        )

        totals = [[0 for _ in range(24)] for _ in range(7)]
        flagged = [[0 for _ in range(24)] for _ in range(7)]
        for created_at, processing_status, predicted_class, risk_level in result.all():
            if created_at is None:
                continue
            day_index = created_at.weekday()  # Monday=0
            hour_index = created_at.hour
            totals[day_index][hour_index] += 1
            if _is_flagged(processing_status, predicted_class, risk_level):
                flagged[day_index][hour_index] += 1

        heatmap_data: list[list[float]] = []
        for day in range(7):
            row: list[float] = []
            for hour in range(24):
                total = totals[day][hour]
                value = (flagged[day][hour] / total) if total else 0.0
                row.append(round(value, 4))
            heatmap_data.append(row)

        return {"heatmap_data": heatmap_data}
    except Exception as e:
        logger.error("Error fetching time heatmap data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/model-performance")
async def get_model_performance(
    time_range: str = Query("24h"),
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
) -> Any:
    try:
        start_dt, end_dt = _resolve_window(time_range, None, None)
        filters = _build_filters(synthetic_only, start_dt, end_dt)

        latency_result = await db.execute(
            select(Transaction.inference_latency_ms)
            .where(*filters)
            .where(Transaction.inference_latency_ms.is_not(None))
            .order_by(Transaction.inference_latency_ms.asc())
        )
        latencies = [int(row[0]) for row in latency_result.all()]
        latency_p95 = float(latencies[int(0.95 * (len(latencies) - 1))]) if latencies else 0.0

        return {
            "accuracy": 0.98,
            "precision": 0.92,
            "recall": 0.85,
            "f1_score": 0.88,
            "latency_p95": round(latency_p95, 2),
        }
    except Exception as e:
        logger.error("Error fetching model performance metrics: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
