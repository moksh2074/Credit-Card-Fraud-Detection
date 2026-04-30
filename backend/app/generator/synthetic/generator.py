"""
SyntheticTransactionGenerator — The sole source of transaction data
for the Fraud Detection Platform.

Generates realistic transaction streams using asyncio background tasks
and posts each transaction to the backend ingestion API endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cardholder & Merchant profile pools
# ---------------------------------------------------------------------------

_MCC_POOL = [
    ("5411", "grocery_stores"),
    ("5812", "restaurants"),
    ("7011", "hotels"),
    ("5912", "drug_stores"),
    ("4111", "transportation"),
    ("5999", "misc_retail"),
    ("7995", "gambling"),
    ("6011", "cash_dispensing"),
    ("5045", "electronics_wholesale"),
    ("5311", "department_stores"),
]

_DEVICE_TYPES = ["mobile", "desktop", "pos", "atm"]
_CHANNELS = ["ONLINE", "POS", "ATM"]
_CURRENCIES = ["USD", "EUR", "GBP", "INR", "AUD"]
_COUNTRIES = [
    ("US", 37.09, -95.71),
    ("GB", 55.37, -3.43),
    ("IN", 20.59, 78.96),
    ("AU", -25.27, 133.77),
    ("DE", 51.13, 10.01),
]


# ---------------------------------------------------------------------------
# Fraud scenario injectors
# ---------------------------------------------------------------------------

def _inject_velocity_burst(payload: dict[str, Any]) -> dict[str, Any]:
    """Simulate rapid successive transactions — same card, many in short time."""
    payload["_fraud_scenario"] = "velocity_burst"
    # Amount is kept small (card testing style)
    payload["amount"] = round(random.uniform(0.50, 5.00), 2)
    return payload


def _inject_impossible_travel(
    payload: dict[str, Any], profiles: list[dict[str, Any]]
) -> dict[str, Any]:
    """Place transaction far from cardholder's home country."""
    profile = random.choice(profiles)
    home_country, home_lat, home_lon = random.choice(_COUNTRIES)
    # Pick a country far away
    away = [c for c in _COUNTRIES if c[0] != home_country]
    _, far_lat, far_lon = random.choice(away)
    payload["geo_lat"] = far_lat + random.uniform(-2, 2)
    payload["geo_lon"] = far_lon + random.uniform(-2, 2)
    payload["geo_country"] = random.choice([c[0] for c in away])
    payload["_fraud_scenario"] = "impossible_travel"
    return payload


def _inject_card_testing(payload: dict[str, Any]) -> dict[str, Any]:
    """Micro-transactions used to verify card validity."""
    payload["amount"] = round(random.uniform(0.01, 1.00), 2)
    payload["_fraud_scenario"] = "card_testing"
    return payload


def _inject_high_value_cnp(payload: dict[str, Any]) -> dict[str, Any]:
    """High-value card-not-present transaction."""
    payload["amount"] = round(random.uniform(2000, 15000), 2)
    payload["channel"] = "ONLINE"
    payload["device_type"] = "desktop"
    payload["_fraud_scenario"] = "high_value_cnp"
    return payload


def _inject_new_device_fraud(payload: dict[str, Any]) -> dict[str, Any]:
    """Fraud using an unrecognised device."""
    payload["is_new_device"] = True
    payload["device_id"] = f"new-{uuid.uuid4().hex[:8]}"
    payload["amount"] = round(random.uniform(500, 3000), 2)
    payload["_fraud_scenario"] = "new_device_fraud"
    return payload


SCENARIO_INJECTORS: dict[str, Any] = {
    "velocity_burst": _inject_velocity_burst,
    "impossible_travel": _inject_impossible_travel,
    "card_testing": _inject_card_testing,
    "high_value_cnp": _inject_high_value_cnp,
    "new_device_fraud": _inject_new_device_fraud,
}


# ---------------------------------------------------------------------------
# Status tracking
# ---------------------------------------------------------------------------

@dataclass
class GeneratorStatus:
    is_running: bool = False
    current_tps: float = 0.0
    fraud_events_last_minute: int = 0
    queue_depth: int = 0
    total_generated: int = 0
    total_fraud_injected: int = 0
    started_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------

class SyntheticTransactionGenerator:
    """
    Generates a continuous stream of synthetic credit card transactions
    and posts them to the backend ingestion API.

    Parameters
    ----------
    tps:
        Target transactions per second (float, e.g. 2.5).
    fraud_injection_rate:
        Fraction of transactions that are injected with a fraud scenario (0–1).
    active_scenarios:
        List of fraud scenario names to use. Defaults to all 5.
    cardholder_profile_count:
        Number of synthetic cardholder profiles to simulate.
    api_base_url:
        Base URL of the backend API (e.g. "http://localhost:8000").
    """

    def __init__(
        self,
        tps: float = 1.0,
        fraud_injection_rate: float = 0.05,
        active_scenarios: Optional[list[str]] = None,
        cardholder_profile_count: int = 100,
        api_base_url: str = "",
    ) -> None:
        self.tps = max(0.01, tps)
        self.fraud_injection_rate = max(0.0, min(1.0, fraud_injection_rate))
        self.active_scenarios: list[str] = active_scenarios or list(SCENARIO_INJECTORS.keys())
        self.cardholder_profile_count = max(1, cardholder_profile_count)
        self.api_base_url = api_base_url or os.getenv(
            "API_BASE_URL", "http://localhost:8000"
        )

        self._status = GeneratorStatus()
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        # Ring buffer storing timestamps (epoch) of fraud events for last-minute count
        self._fraud_timestamps: Deque[float] = deque()
        # Pre-generate cardholder profiles
        self._profiles = self._build_profiles()

    # ------------------------------------------------------------------
    # Profile generation
    # ------------------------------------------------------------------

    def _build_profiles(self) -> list[dict[str, Any]]:
        profiles = []
        for i in range(self.cardholder_profile_count):
            country_name, lat, lon = random.choice(_COUNTRIES)
            profiles.append(
                {
                    "card_id": f"card_{i:06d}",
                    "home_country": country_name,
                    "home_lat": lat + random.uniform(-5, 5),
                    "home_lon": lon + random.uniform(-5, 5),
                    "avg_amount": random.uniform(20, 500),
                    "preferred_channel": random.choice(_CHANNELS),
                    "registered_devices": [f"dev_{uuid.uuid4().hex[:8]}" for _ in range(random.randint(1, 3))],
                }
            )
        return profiles

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin generating transactions at the configured TPS using asyncio."""
        if self._task is not None and self._task.done():
            self._task = None

        if self._task is not None and not self._task.done():
            logger.warning("SyntheticTransactionGenerator: already running")
            return

        self._status.is_running = True
        self._status.started_at = datetime.now(timezone.utc)
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._generation_loop())
        logger.info(
            "SyntheticTransactionGenerator started: tps=%.2f fraud_rate=%.2f",
            self.tps,
            self.fraud_injection_rate,
        )

    def stop(self) -> None:
        """Stop the generation loop."""
        self._status.is_running = False
        current_task = self._task
        if current_task is not None and not current_task.done():
            current_task.cancel()
        logger.info("SyntheticTransactionGenerator stopped after %d transactions",
                    self._status.total_generated)

    def status(self) -> GeneratorStatus:
        """Return current generator metrics."""
        self._status.current_tps = self.tps
        self._status.queue_depth = 0  # httpx is async; no internal queue
        now = time.time()
        # Fraud events in the last 60 seconds
        while self._fraud_timestamps and self._fraud_timestamps[0] < now - 60:
            self._fraud_timestamps.popleft()
        self._status.fraud_events_last_minute = len(self._fraud_timestamps)
        return self._status

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _generation_loop(self) -> None:
        """Main async generation loop — runs until stop() is called."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            while self._status.is_running:
                t_start = asyncio.get_event_loop().time()
                try:
                    payload = await self._generate_one()
                    await self._post_transaction(client, payload)
                    self._status.total_generated += 1
                    if payload.get("_fraud_scenario"):
                        self._status.total_fraud_injected += 1
                        self._fraud_timestamps.append(time.time())
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("SyntheticTransactionGenerator: generation error — %s", exc)

                interval = 1.0 / max(0.01, self.tps)
                elapsed = asyncio.get_event_loop().time() - t_start
                sleep_for = max(0.0, interval - elapsed)
                await asyncio.sleep(sleep_for)

        self._status.is_running = False
        self._task = None

    async def _generate_one(self) -> dict[str, Any]:
        """
        Produce a single synthetic transaction payload dict.

        If random() < fraud_injection_rate, one of the active fraud
        scenarios is applied to the payload.
        """
        profile = random.choice(self._profiles)
        now = datetime.now(timezone.utc)
        mcc_code, mcc_name = random.choice(_MCC_POOL)
        channel = profile["preferred_channel"]
        device_id = random.choice(profile["registered_devices"])
        is_new_device = False

        # 5% chance of a genuinely new device (not fraud per se)
        if random.random() < 0.05:
            device_id = f"new-{uuid.uuid4().hex[:8]}"
            is_new_device = True

        # Amount with log-normal distribution around profile mean
        amount = float(np.random.lognormal(
            mean=math.log(profile["avg_amount"]),
            sigma=0.8,
        )) if _numpy_available() else round(
            profile["avg_amount"] * random.uniform(0.2, 3.0), 2
        )
        amount = round(amount, 2)

        lat = profile["home_lat"] + random.uniform(-0.5, 0.5)
        lon = profile["home_lon"] + random.uniform(-0.5, 0.5)

        payload: dict[str, Any] = {
            "transaction_id": str(uuid.uuid4()),
            "card_id_hash": profile["card_id"],
            "merchant_id": f"merch_{random.randint(1000, 9999)}",
            "merchant_name": f"Merchant {random.randint(1000, 9999)}",
            "mcc": mcc_code,
            "amount": amount,
            "currency": random.choice(_CURRENCIES),
            "channel": channel,
            "device_id": device_id,
            "device_type": random.choice(_DEVICE_TYPES),
            "is_new_device": is_new_device,
            "ip_address": f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "geo_lat": round(lat, 6),
            "geo_lon": round(lon, 6),
            "geo_country": profile["home_country"],
            "geo_city": "Simulated",
            "timestamp": now.isoformat(),
            "data_source": "SYNTHETIC_GENERATOR",
        }

        # Fraud injection
        if random.random() < self.fraud_injection_rate and self.active_scenarios:
            scenario = random.choice(self.active_scenarios)
            injector = SCENARIO_INJECTORS.get(scenario)
            if injector:
                if scenario == "impossible_travel":
                    payload = injector(payload, self._profiles)
                else:
                    payload = injector(payload)

        return payload

    async def _post_transaction(
        self, client: httpx.AsyncClient, payload: dict[str, Any]
    ) -> None:
        """POST the transaction payload to the ingestion API endpoint."""
        url = f"{self.api_base_url}/api/v1/transactions/ingest"
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code not in (200, 201, 202):
                logger.warning(
                    "Generator: ingest returned %d — %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except httpx.RequestError as exc:
            logger.warning("Generator: http error posting to %s — %s", url, exc)

    # ------------------------------------------------------------------
    # Configuration hot-update
    # ------------------------------------------------------------------

    def update_config(
        self,
        tps: Optional[float] = None,
        fraud_injection_rate: Optional[float] = None,
        active_scenarios: Optional[list[str]] = None,
        cardholder_profile_count: Optional[int] = None,
    ) -> None:
        """Update generator config at runtime without restarting."""
        if tps is not None:
            self.tps = max(0.01, tps)
        if fraud_injection_rate is not None:
            self.fraud_injection_rate = max(0.0, min(1.0, fraud_injection_rate))
        if active_scenarios is not None:
            self.active_scenarios = active_scenarios
        if cardholder_profile_count is not None and cardholder_profile_count != self.cardholder_profile_count:
            self.cardholder_profile_count = max(1, cardholder_profile_count)
            self._profiles = self._build_profiles()


def _numpy_available() -> bool:
    """Check numpy availability without import error."""
    try:
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


# Import numpy at module-level if available (used in lognormal sampling)
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]
