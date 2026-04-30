"""
VelocityStore — Redis-backed sorted set store for transaction velocity tracking.

Each card has multiple sorted sets keyed by card_id_hash, storing transaction
timestamps as scores so range queries by time window are O(log N).
"""
from __future__ import annotations

import time
from typing import Any

import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REDIS_URL: str = "redis://localhost:6379/0"

# Time windows in seconds
WINDOW_1H: int = 3600
WINDOW_6H: int = 21600
WINDOW_24H: int = 86400


class VelocityStore:
    """
    Manages per-card transaction velocity counters in Redis sorted sets.

    Redis key schema
    ----------------
    velocity:{card_id_hash}:tx        — member=tx_id, score=epoch_ms
    velocity:{card_id_hash}:amount    — member=tx_id, score=amount (for sum)
    velocity:{card_id_hash}:merchant  — member=tx_id|merchant_id, score=epoch
    velocity:{card_id_hash}:geo       — member=tx_id|geo_cluster, score=epoch
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def increment_velocity(
        self,
        card_id: str,
        transaction_id: str,
        timestamp: float,
        amount: float = 0.0,
        merchant_id: str = "",
        geo_cluster: str = "",
    ) -> None:
        """
        Record a new transaction event for the card.

        Parameters
        ----------
        card_id:
            Hashed card identifier.
        transaction_id:
            Unique transaction UUID string.
        timestamp:
            Unix epoch in seconds for the transaction.
        amount:
            Transaction amount (used for amount_sum_1h).
        merchant_id:
            Merchant identifier (used for unique merchant count).
        geo_cluster:
            Geo cluster label (e.g. rounded lat/lon) for unique geo count.
        """
        epoch_ms = int(timestamp * 1000)
        pipe = self._redis.pipeline(transaction=True)

        tx_key = f"velocity:{card_id}:tx"
        amount_key = f"velocity:{card_id}:amount"
        merchant_key = f"velocity:{card_id}:merchant"
        geo_key = f"velocity:{card_id}:geo"

        # Add to tx sorted set (score = epoch_ms for time-range queries)
        pipe.zadd(tx_key, {transaction_id: epoch_ms})

        # Add amount entry — member includes tx_id for uniqueness
        if amount > 0:
            pipe.zadd(amount_key, {f"{transaction_id}": amount})
            # Set expiry on amount key separately (not sorted-set range)
            pipe.expire(amount_key, WINDOW_24H + 3600)

        # Merchant uniqueness (member = merchant_id|epoch for dedup by time)
        if merchant_id:
            pipe.zadd(merchant_key, {f"{merchant_id}|{transaction_id}": epoch_ms})
            pipe.expire(merchant_key, WINDOW_24H + 3600)

        # Geo cluster uniqueness
        if geo_cluster:
            pipe.zadd(geo_key, {f"{geo_cluster}|{transaction_id}": epoch_ms})
            pipe.expire(geo_key, WINDOW_24H + 3600)

        # Expire tx key after 25h to auto-clean
        pipe.expire(tx_key, WINDOW_24H + 3600)

        await pipe.execute()

    async def get_velocity_counts(self, card_id: str) -> dict[str, Any]:
        """
        Return velocity aggregates for the card across multiple time windows.

        Returns
        -------
        dict with keys:
            1h, 6h, 24h            — transaction counts
            amount_sum_1h          — sum of amounts in last 1h
            unique_merchants_24h   — distinct merchants in last 24h
            unique_geo_clusters_24h — distinct geo clusters in last 24h
        """
        now_ms = int(time.time() * 1000)
        cutoff_1h = now_ms - WINDOW_1H * 1000
        cutoff_6h = now_ms - WINDOW_6H * 1000
        cutoff_24h = now_ms - WINDOW_24H * 1000

        tx_key = f"velocity:{card_id}:tx"
        amount_key = f"velocity:{card_id}:amount"
        merchant_key = f"velocity:{card_id}:merchant"
        geo_key = f"velocity:{card_id}:geo"

        pipe = self._redis.pipeline(transaction=False)
        pipe.zcount(tx_key, cutoff_1h, now_ms)
        pipe.zcount(tx_key, cutoff_6h, now_ms)
        pipe.zcount(tx_key, cutoff_24h, now_ms)
        # For amount_sum_1h we fetch members in range and sum (members = tx_ids)
        pipe.zrangebyscore(tx_key, cutoff_1h, now_ms)
        # Unique merchants / geo in 24h
        pipe.zcount(merchant_key, cutoff_24h, now_ms)
        pipe.zcount(geo_key, cutoff_24h, now_ms)
        results = await pipe.execute()

        count_1h: int = int(results[0] or 0)
        count_6h: int = int(results[1] or 0)
        count_24h: int = int(results[2] or 0)
        tx_ids_1h: list[bytes] = results[3] or []
        unique_merchants: int = int(results[4] or 0)
        unique_geo: int = int(results[5] or 0)

        # Compute amount_sum_1h: lookup amounts for tx_ids returned
        amount_sum_1h: float = 0.0
        if tx_ids_1h:
            amount_pipe = self._redis.pipeline(transaction=False)
            for tx_id in tx_ids_1h:
                tx_str = tx_id.decode() if isinstance(tx_id, bytes) else tx_id
                amount_pipe.zscore(amount_key, tx_str)
            scores = await amount_pipe.execute()
            amount_sum_1h = sum(float(s) for s in scores if s is not None)

        return {
            "1h": count_1h,
            "6h": count_6h,
            "24h": count_24h,
            "amount_sum_1h": amount_sum_1h,
            "unique_merchants_24h": unique_merchants,
            "unique_geo_clusters_24h": unique_geo,
        }

    async def trim_old_entries(self, card_id: str) -> None:
        """
        Remove entries older than 24h from all velocity sorted sets for a card.
        Called periodically or after each write to keep memory usage bounded.
        """
        cutoff_24h_ms = int((time.time() - WINDOW_24H) * 1000)

        tx_key = f"velocity:{card_id}:tx"
        merchant_key = f"velocity:{card_id}:merchant"
        geo_key = f"velocity:{card_id}:geo"

        pipe = self._redis.pipeline(transaction=True)
        pipe.zremrangebyscore(tx_key, "-inf", cutoff_24h_ms)
        pipe.zremrangebyscore(merchant_key, "-inf", cutoff_24h_ms)
        pipe.zremrangebyscore(geo_key, "-inf", cutoff_24h_ms)
        await pipe.execute()


async def get_velocity_store() -> VelocityStore:
    """Factory: create a VelocityStore connected to the configured Redis instance."""
    import os
    redis_url = os.getenv("REDIS_URL", REDIS_URL)
    client = aioredis.from_url(redis_url, decode_responses=False)
    return VelocityStore(client)
