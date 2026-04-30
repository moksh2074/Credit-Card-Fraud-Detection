import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, JSON, Uuid
from app.db.models.base import Base
import enum

class AlertSeverityEnum(str, enum.Enum):
    P0 = "P0" # CRITICAL
    P1 = "P1" # HIGH
    P2 = "P2" # MEDIUM
    P3 = "P3" # LOW

class AlertStatusEnum(str, enum.Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"

class AlertOutcomeEnum(str, enum.Enum):
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ESCALATED = "ESCALATED"

class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    transaction_id = Column(Uuid(as_uuid=True), ForeignKey("transactions.id"), index=True, nullable=False)
    card_id_hash = Column(String, index=True, nullable=False)
    severity = Column(Enum(AlertSeverityEnum), nullable=False)
    rule_triggers = Column(JSON, nullable=True)
    assignee_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(Enum(AlertStatusEnum), default=AlertStatusEnum.NEW, nullable=False)
    outcome = Column(Enum(AlertOutcomeEnum), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
