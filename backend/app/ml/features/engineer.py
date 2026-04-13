"""
TransactionFeatureEngineer — Feature engineering pipeline for the fraud detection ML model.

Computes all model-ready features from a raw transaction payload and Redis velocity data.
"""
from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

# ---------------------------------------------------------------------------
# High-risk MCC codes (ISO 18245)
# ---------------------------------------------------------------------------
HIGH_RISK_MCC_SET: set[str] = {
    "6011",  # Cash dispensing
    "6010",  # Manual cash disbursements
    "7995",  # Gambling / lottery
    "5912",  # Drug stores / pharmacies
    "5999",  # Misc retail
    "4829",  # Wire transfer money orders
    "6051",  # Non-financial institutions (crypto)
    "9222",  # Fines
    "5094",  # Precious stones / metals
    "5065",  # Electronic parts wholesale
}

# MCC risk encoding (0=low, 1=medium, 2=high)
MCC_RISK_MAP: dict[str, int] = {mcc: 2 for mcc in HIGH_RISK_MCC_SET}


@dataclass
class FeatureVector:
    """Ordered, model-ready feature vector for the Random Forest classifier."""

    # Amount features
    amount_log: float = 0.0
    amount_vs_30d_mean_ratio: float = 1.0
    amount_vs_90d_mean_ratio: float = 1.0
    is_round_amount: int = 0

    # Temporal features
    hour_sin: float = 0.0
    hour_cos: float = 0.0
    day_of_week_sin: float = 0.0
    day_of_week_cos: float = 0.0
    is_weekend: int = 0
    is_night: int = 0

    # Velocity features
    tx_count_1h: int = 0
    tx_count_6h: int = 0
    tx_count_24h: int = 0
    amount_sum_1h: float = 0.0
    unique_merchants_24h: int = 0
    unique_geo_clusters_24h: int = 0

    # Geo features
    geo_distance_from_last_km: float = 0.0
    implied_speed_kmh: float = 0.0
    impossible_travel: int = 0
    is_international: int = 0

    # Device features
    is_new_device: int = 0
    device_type_encoded: int = 0  # 0=unknown, 1=mobile, 2=desktop, 3=pos, 4=atm
    device_fraud_rate: float = 0.0

    # Merchant features
    merchant_fraud_rate: float = 0.0
    mcc_risk_encoded: int = 0
    is_high_risk_mcc: int = 0

    # Behavioral features
    days_since_last_legit_tx: float = 0.0
    card_age_days: float = 0.0
    account_standing_encoded: int = 0  # 0=good, 1=watch, 2=suspended

    def to_array(self) -> list[float]:
        """Return features as an ordered list for model input."""
        return [
            self.amount_log,
            self.amount_vs_30d_mean_ratio,
            self.amount_vs_90d_mean_ratio,
            float(self.is_round_amount),
            self.hour_sin,
            self.hour_cos,
            self.day_of_week_sin,
            self.day_of_week_cos,
            float(self.is_weekend),
            float(self.is_night),
            float(self.tx_count_1h),
            float(self.tx_count_6h),
            float(self.tx_count_24h),
            self.amount_sum_1h,
            float(self.unique_merchants_24h),
            float(self.unique_geo_clusters_24h),
            self.geo_distance_from_last_km,
            self.implied_speed_kmh,
            float(self.impossible_travel),
            float(self.is_international),
            float(self.is_new_device),
            float(self.device_type_encoded),
            self.device_fraud_rate,
            self.merchant_fraud_rate,
            float(self.mcc_risk_encoded),
            float(self.is_high_risk_mcc),
            self.days_since_last_legit_tx,
            self.card_age_days,
            float(self.account_standing_encoded),
        ]

    @property
    def feature_names(self) -> list[str]:
        """Ordered feature names matching to_array()."""
        return [
            "amount_log",
            "amount_vs_30d_mean_ratio",
            "amount_vs_90d_mean_ratio",
            "is_round_amount",
            "hour_sin",
            "hour_cos",
            "day_of_week_sin",
            "day_of_week_cos",
            "is_weekend",
            "is_night",
            "tx_count_1h",
            "tx_count_6h",
            "tx_count_24h",
            "amount_sum_1h",
            "unique_merchants_24h",
            "unique_geo_clusters_24h",
            "geo_distance_from_last_km",
            "implied_speed_kmh",
            "impossible_travel",
            "is_international",
            "is_new_device",
            "device_type_encoded",
            "device_fraud_rate",
            "merchant_fraud_rate",
            "mcc_risk_encoded",
            "is_high_risk_mcc",
            "days_since_last_legit_tx",
            "card_age_days",
            "account_standing_encoded",
        ]


# ---------------------------------------------------------------------------
# Helper: Haversine distance
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Device type encoding
# ---------------------------------------------------------------------------
DEVICE_TYPE_ENCODING: dict[str, int] = {
    "mobile": 1,
    "desktop": 2,
    "pos": 3,
    "atm": 4,
}

# ---------------------------------------------------------------------------
# Account standing encoding
# ---------------------------------------------------------------------------
ACCOUNT_STANDING_ENCODING: dict[str, int] = {
    "good": 0,
    "watch": 1,
    "suspended": 2,
}


class TransactionFeatureEngineer:
    """
    Transforms a raw transaction payload and its associated context data
    (velocity counts from Redis, merchant stats, card history) into a
    fully populated FeatureVector ready for ML inference.

    Usage
    -----
    engineer = TransactionFeatureEngineer()
    feature_vector = engineer.engineer(transaction_payload, velocity_data, context)
    """

    # Impossible travel threshold — if average speed between two consecutive
    # transactions using normal transportation exceeds this, flag it.
    IMPOSSIBLE_SPEED_THRESHOLD_KMPH: float = 900.0  # commercial aviation cap

    def engineer(
        self,
        transaction: dict[str, Any],
        velocity_data: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> FeatureVector:
        """
        Compute all features for a single transaction.

        Parameters
        ----------
        transaction:
            Raw transaction payload dict with keys:
              amount, timestamp, hour (int 0-23), day_of_week (int 0-6),
              geo_lat, geo_lon, geo_country, device_id, device_type,
              is_new_device, mcc, merchant_id, card_id_hash, channel.
        velocity_data:
            Output of VelocityStore.get_velocity_counts() plus optional
            amount_sum_1h, unique_merchants_24h, unique_geo_clusters_24h.
        context:
            Optional enrichment context:
              last_tx_lat, last_tx_lon, last_tx_timestamp,
              card_30d_mean, card_90d_mean,
              merchant_fraud_rate, device_fraud_rate,
              days_since_last_legit_tx, card_age_days,
              account_standing, home_country.
        """
        ctx = context or {}
        fv = FeatureVector()

        # ---- Amount features -----------------------------------------------
        amount: float = float(transaction.get("amount", 0.0))
        fv.amount_log = math.log1p(amount)

        card_30d_mean: float = float(ctx.get("card_30d_mean", amount) or amount)
        card_90d_mean: float = float(ctx.get("card_90d_mean", amount) or amount)
        fv.amount_vs_30d_mean_ratio = amount / card_30d_mean if card_30d_mean > 0 else 1.0
        fv.amount_vs_90d_mean_ratio = amount / card_90d_mean if card_90d_mean > 0 else 1.0
        fv.is_round_amount = 1 if amount % 1 == 0 and amount > 0 else 0

        # ---- Temporal features ---------------------------------------------
        hour: int = int(transaction.get("hour", 0))
        dow: int = int(transaction.get("day_of_week", 0))  # 0=Monday … 6=Sunday
        fv.hour_sin = math.sin(2 * math.pi * hour / 24)
        fv.hour_cos = math.cos(2 * math.pi * hour / 24)
        fv.day_of_week_sin = math.sin(2 * math.pi * dow / 7)
        fv.day_of_week_cos = math.cos(2 * math.pi * dow / 7)
        fv.is_weekend = 1 if dow >= 5 else 0
        fv.is_night = 1 if hour < 6 or hour >= 22 else 0

        # ---- Velocity features (from Redis VelocityStore) ------------------
        fv.tx_count_1h = int(velocity_data.get("1h", 0))
        fv.tx_count_6h = int(velocity_data.get("6h", 0))
        fv.tx_count_24h = int(velocity_data.get("24h", 0))
        fv.amount_sum_1h = float(velocity_data.get("amount_sum_1h", 0.0))
        fv.unique_merchants_24h = int(velocity_data.get("unique_merchants_24h", 0))
        fv.unique_geo_clusters_24h = int(velocity_data.get("unique_geo_clusters_24h", 0))

        # ---- Geo features --------------------------------------------------
        lat: Optional[float] = transaction.get("geo_lat")
        lon: Optional[float] = transaction.get("geo_lon")
        last_lat: Optional[float] = ctx.get("last_tx_lat")
        last_lon: Optional[float] = ctx.get("last_tx_lon")
        last_ts: Optional[float] = ctx.get("last_tx_timestamp")  # epoch seconds

        if lat is not None and lon is not None and last_lat is not None and last_lon is not None:
            dist_km = _haversine_km(last_lat, last_lon, lat, lon)
            fv.geo_distance_from_last_km = dist_km

            current_ts_raw = transaction.get("timestamp")
            if current_ts_raw is not None and last_ts is not None:
                current_epoch = (
                    current_ts_raw.timestamp()
                    if isinstance(current_ts_raw, datetime)
                    else float(current_ts_raw)
                )
                elapsed_hours = max((current_epoch - float(last_ts)) / 3600, 1e-6)
                speed = dist_km / elapsed_hours
                fv.implied_speed_kmh = speed
                fv.impossible_travel = 1 if speed > self.IMPOSSIBLE_SPEED_THRESHOLD_KMPH else 0
            else:
                fv.implied_speed_kmh = 0.0
                fv.impossible_travel = 0
        else:
            fv.geo_distance_from_last_km = 0.0
            fv.implied_speed_kmh = 0.0
            fv.impossible_travel = 0

        home_country: str = ctx.get("home_country", "")
        tx_country: str = transaction.get("geo_country", "")
        fv.is_international = 1 if home_country and tx_country and tx_country != home_country else 0

        # ---- Device features -----------------------------------------------
        fv.is_new_device = 1 if transaction.get("is_new_device") else 0
        device_type_raw: str = str(transaction.get("device_type", "")).lower()
        fv.device_type_encoded = DEVICE_TYPE_ENCODING.get(device_type_raw, 0)
        fv.device_fraud_rate = float(ctx.get("device_fraud_rate", 0.0))

        # ---- Merchant features ---------------------------------------------
        fv.merchant_fraud_rate = float(ctx.get("merchant_fraud_rate", 0.0))
        mcc: str = str(transaction.get("mcc", ""))
        fv.mcc_risk_encoded = MCC_RISK_MAP.get(mcc, 0)
        fv.is_high_risk_mcc = 1 if mcc in HIGH_RISK_MCC_SET else 0

        # ---- Behavioral features -------------------------------------------
        fv.days_since_last_legit_tx = float(ctx.get("days_since_last_legit_tx", 0.0))
        fv.card_age_days = float(ctx.get("card_age_days", 0.0))
        standing_raw: str = str(ctx.get("account_standing", "good")).lower()
        fv.account_standing_encoded = ACCOUNT_STANDING_ENCODING.get(standing_raw, 0)

        return fv
