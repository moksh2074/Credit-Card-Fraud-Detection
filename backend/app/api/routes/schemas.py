from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID

from app.db.models.user import UserRole
from app.db.models.transaction import (
    ChannelEnum,
    RiskLevelEnum,
    PredictedClassEnum,
    ProcessingStatusEnum,
    TransactionDataSourceEnum,
)
from app.db.models.alert import AlertSeverityEnum, AlertStatusEnum, AlertOutcomeEnum

# -- Auth Schemas --
class UserCreate(BaseModel):
    email: str
    password: str
    role: UserRole
    org_id: Optional[str] = None

class UserResponse(BaseModel):
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class LoginRequest(BaseModel):
    email: str
    password: str

# -- Transaction Schemas --
class TransactionIngestRequest(BaseModel):
    transaction_id: str
    card_id_hash: str
    merchant_id: str
    merchant_name: Optional[str] = None
    mcc: str
    amount: float
    currency: str
    channel: ChannelEnum
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    is_new_device: Optional[bool] = False
    ip_address: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    geo_country: Optional[str] = None
    geo_city: Optional[str] = None
    timestamp: datetime
    fraud_scenario: Optional[str] = Field(default=None, alias="_fraud_scenario")
    data_source: TransactionDataSourceEnum = TransactionDataSourceEnum.SYNTHETIC_GENERATOR

class TransactionResponse(BaseModel):
    id: UUID
    card_id_hash: str
    merchant_id: str
    merchant_name: Optional[str] = None
    mcc: str
    amount: float
    currency: str
    channel: ChannelEnum
    velocity_1h: Optional[int] = None
    velocity_24h: Optional[int] = None
    geo_distance_km: Optional[float] = None
    implied_speed_kmh: Optional[float] = None
    impossible_travel_flag: bool = False
    fraud_score: Optional[float] = None
    risk_level: Optional[RiskLevelEnum] = None
    predicted_class: Optional[PredictedClassEnum] = None
    shap_features: Optional[List[Dict[str, Any]] | Dict[str, float]] = None
    data_source: Optional[TransactionDataSourceEnum] = None
    processing_status: ProcessingStatusEnum
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class PaginatedTransactionResponse(BaseModel):
    total: int
    page: int
    size: int
    flagged_count: int = 0
    approved_count: int = 0
    items: List[TransactionResponse]

# -- Alert Schemas --
class AlertResponse(BaseModel):
    id: UUID
    transaction_id: UUID
    card_id_hash: str
    severity: AlertSeverityEnum
    rule_triggers: Optional[Dict[str, Any]] = None
    status: AlertStatusEnum
    outcome: Optional[AlertOutcomeEnum] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AlertUpdateStatusRequest(BaseModel):
    status: AlertStatusEnum
    outcome: Optional[AlertOutcomeEnum] = None

# -- Generator Schemas --
class GeneratorConfigUpdateRequest(BaseModel):
    tps: Optional[float] = Field(default=None, ge=0.1, le=200.0)
    fraud_injection_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    active_scenarios: Optional[List[str]] = None

class GeneratorStatusResponse(BaseModel):
    is_running: bool
    current_tps: float
    fraud_rate: float
    queue_depth: int
    active_scenarios: List[str]
