import json
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.alert import FraudAlert, AlertSeverityEnum, AlertStatusEnum
from app.services.notifications.ibm_notifier import get_notifier
import os

logger = logging.getLogger(__name__)

class AlertService:
    def __init__(self, redis_client: Any):
        self.redis = redis_client
        self.notifier = get_notifier()
        self.dedup_ttl = 300  # 5 minutes

    async def create_alert(
        self, 
        db: AsyncSession, 
        transaction: dict[str, Any], 
        inference_result: Any, 
        wazuh_rule_triggers: list[dict[str, Any]]
    ) -> FraudAlert | None:
        """
        Deduplicates, classifies severity, inserts alert, and notifies.
        """
        card_id_hash = transaction.get("card_id_hash", "")
        tx_id = transaction.get("id")
        
        # 1. Deduplication using Redis
        dedup_key = f"alert_dedup:{card_id_hash}"
        if self.redis:
            is_duplicate = await self.redis.get(dedup_key)
            if is_duplicate:
                logger.info(f"Alert skipped for card {card_id_hash} - deduplication active.")
                return None
            
            await self.redis.setex(dedup_key, self.dedup_ttl, "locked")

        # 2. Classify Severity
        severity = self._classify_severity(inference_result, wazuh_rule_triggers)

        # 3. Database Insert
        alert = FraudAlert(
            transaction_id=tx_id,
            card_id_hash=card_id_hash,
            severity=severity,
            rule_triggers=wazuh_rule_triggers,
            status=AlertStatusEnum.NEW
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
        logger.info(f"Created {severity.value} alert for transaction {tx_id}")

        # 4. Dispatch Notification
        alert_record = {
            "id": str(alert.id),
            "transaction_id": str(alert.transaction_id),
            "card_id_hash": alert.card_id_hash,
            "severity": alert.severity.value,
            "rule_triggers": alert.rule_triggers,
            "status": alert.status.value
        }
        self.notifier.send_fraud_alert(alert_record)

        return alert

    def _classify_severity(self, inference_result: Any, wazuh_rule_triggers: list[dict[str, Any]]) -> AlertSeverityEnum:
        """
        P0: CRITICAL ML Risk or High-composite rule triggers
        P1: HIGH ML Risk or Velocity/Amount triggers
        P2: MEDIUM ML Risk or general alerts
        P3: LOW (info only)
        """
        risk_level = getattr(inference_result, "risk_level", "LOW")
        
        has_critical_rules = any(r.get("level", 0) >= 12 for r in wazuh_rule_triggers)
        has_high_rules = any(r.get("level", 0) >= 10 for r in wazuh_rule_triggers)

        if risk_level == "CRITICAL" or has_critical_rules:
            return AlertSeverityEnum.P0
        if risk_level == "HIGH" or has_high_rules:
            return AlertSeverityEnum.P1
        if risk_level == "MEDIUM":
            return AlertSeverityEnum.P2
        
        return AlertSeverityEnum.P3

def get_alert_service(redis_client: Any) -> AlertService:
    return AlertService(redis_client)
