from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Any, List, Optional
from uuid import UUID
import logging

from .schemas import AlertResponse, AlertUpdateStatusRequest
from app.db.models.alert import FraudAlert, AlertStatusEnum, AlertSeverityEnum, AlertOutcomeEnum
from app.db.models.transaction import (
    Transaction,
    ProcessingStatusEnum,
    PredictedClassEnum,
    RiskLevelEnum,
    TransactionDataSourceEnum,
)
from app.db.models.audit_log import AuditLog
from app.db.session import get_db
from app.core.broadcaster import broadcaster

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[AlertResponse])
async def get_alerts(
    status: Optional[AlertStatusEnum] = None,
    severity: Optional[AlertSeverityEnum] = None,
    synthetic_only: bool = Query(True),
    db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        query = select(FraudAlert)
        if status:
            query = query.where(FraudAlert.status == status)
        if severity:
            query = query.where(FraudAlert.severity == severity)
        if synthetic_only:
            query = (
                query.join(Transaction, FraudAlert.transaction_id == Transaction.id)
                .where(Transaction.data_source == TransactionDataSourceEnum.SYNTHETIC_GENERATOR)
            )
        
        query = query.order_by(desc(FraudAlert.created_at))
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{id}/status", response_model=AlertResponse)
async def update_alert_status(
    id: UUID,
    update_req: AlertUpdateStatusRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        result = await db.execute(select(FraudAlert).where(FraudAlert.id == id))
        alert = result.scalars().first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        tx_result = await db.execute(select(Transaction).where(Transaction.id == alert.transaction_id))
        transaction = tx_result.scalars().first()

        if update_req.status == AlertStatusEnum.RESOLVED and update_req.outcome is None:
            raise HTTPException(status_code=422, detail="Outcome is required when resolving an alert.")

        final_outcome = update_req.outcome
        if update_req.status == AlertStatusEnum.FALSE_POSITIVE:
            final_outcome = AlertOutcomeEnum.FALSE_POSITIVE

        alert.status = update_req.status
        alert.outcome = final_outcome

        # Keep transaction state aligned with alert lifecycle for accurate approval/flagging.
        if transaction:
            if update_req.status == AlertStatusEnum.ACKNOWLEDGED:
                transaction.processing_status = ProcessingStatusEnum.ALERTED
            elif update_req.status == AlertStatusEnum.FALSE_POSITIVE or final_outcome == AlertOutcomeEnum.FALSE_POSITIVE:
                transaction.processing_status = ProcessingStatusEnum.RESOLVED
                transaction.predicted_class = PredictedClassEnum.LEGITIMATE
                transaction.risk_level = RiskLevelEnum.LOW
            elif update_req.status == AlertStatusEnum.RESOLVED:
                if final_outcome == AlertOutcomeEnum.CONFIRMED_FRAUD:
                    transaction.processing_status = ProcessingStatusEnum.RESOLVED
                    transaction.predicted_class = PredictedClassEnum.FRAUD
                    transaction.risk_level = RiskLevelEnum.CRITICAL
                elif final_outcome == AlertOutcomeEnum.ESCALATED:
                    transaction.processing_status = ProcessingStatusEnum.ALERTED
                    transaction.predicted_class = PredictedClassEnum.FRAUD
                    if transaction.risk_level in (RiskLevelEnum.LOW, RiskLevelEnum.MEDIUM):
                        transaction.risk_level = RiskLevelEnum.HIGH

        db.add(AuditLog(
            action_type="alert_status_updated",
            resource_type="fraud_alert",
            resource_id=str(alert.id),
        ))

        await db.commit()
        await db.refresh(alert)
        await broadcaster.broadcast(
            {
                "event_type": "alert_updated",
                "alert_id": str(alert.id),
                "transaction_id": str(alert.transaction_id),
                "status": alert.status.value,
                "outcome": alert.outcome.value if alert.outcome else None,
                "severity": alert.severity.value if alert.severity else None,
            }
        )
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert status {id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
