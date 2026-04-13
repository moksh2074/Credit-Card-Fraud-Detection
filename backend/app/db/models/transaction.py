import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, Enum, JSON, Uuid
from app.db.models.base import Base
import enum

class ChannelEnum(str, enum.Enum):
    ONLINE = "ONLINE"
    POS = "POS"
    ATM = "ATM"

class RiskLevelEnum(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class PredictedClassEnum(str, enum.Enum):
    LEGITIMATE = "LEGITIMATE"
    FRAUD = "FRAUD"

class ProcessingStatusEnum(str, enum.Enum):
    RECEIVED = "RECEIVED"
    ENRICHED = "ENRICHED"
    SCORED = "SCORED"
    LOGGED = "LOGGED"
    ALERTED = "ALERTED"
    RESOLVED = "RESOLVED"


class TransactionDataSourceEnum(str, enum.Enum):
    SYNTHETIC_GENERATOR = "SYNTHETIC_GENERATOR"
    KAGGLE_IMPORT = "KAGGLE_IMPORT"
    MANUAL = "MANUAL"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    card_id_hash = Column(String, index=True, nullable=False)
    merchant_id = Column(String, index=True, nullable=False)
    merchant_name = Column(String, nullable=True)
    mcc = Column(String, nullable=False)
    mcc_risk_class = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    channel = Column(Enum(ChannelEnum), nullable=False)
    
    device_id = Column(String, nullable=True)
    device_type = Column(String, nullable=True)
    is_new_device = Column(Boolean, nullable=True)
    ip_address = Column(String, nullable=True)
    
    geo_lat = Column(Float, nullable=True)
    geo_lon = Column(Float, nullable=True)
    geo_country = Column(String, nullable=True)
    geo_city = Column(String, nullable=True)
    
    velocity_1h = Column(Integer, nullable=True)
    velocity_24h = Column(Integer, nullable=True)
    geo_distance_km = Column(Float, nullable=True)
    implied_speed_kmh = Column(Float, nullable=True)
    impossible_travel_flag = Column(Boolean, default=False)
    
    fraud_score = Column(Float, nullable=True)
    risk_level = Column(Enum(RiskLevelEnum), nullable=True)
    predicted_class = Column(Enum(PredictedClassEnum), nullable=True)
    shap_features = Column(JSON, nullable=True)
    model_version = Column(String, nullable=True)
    inference_latency_ms = Column(Integer, nullable=True)
    data_source = Column(
        Enum(TransactionDataSourceEnum),
        nullable=False,
        default=TransactionDataSourceEnum.SYNTHETIC_GENERATOR,
        index=True,
    )
    
    processing_status = Column(Enum(ProcessingStatusEnum), default=ProcessingStatusEnum.RECEIVED)
    created_at = Column(DateTime, default=datetime.utcnow)
