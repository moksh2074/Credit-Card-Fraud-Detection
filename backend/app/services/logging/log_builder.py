"""
LogBuilder Ã¢â‚¬â€ Constructs structured JSON audit records for each processed
transaction and dispatches them to:
1) Local Wazuh NDJSON file (always-on primary sink)
2) Optional IBM COS batch upload
3) Optional AWS S3 archival with durable local queueing
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IBM COS helpers Ã¢â‚¬â€ lazy-imported so the service starts without COS creds
# ---------------------------------------------------------------------------
_COS_AVAILABLE: bool = False
try:
    import ibm_boto3  # type: ignore
    from ibm_botocore.client import Config  # type: ignore
    _COS_AVAILABLE = True
except ImportError:
    logger.warning("LogBuilder: ibm-cos-sdk not available Ã¢â‚¬â€ COS upload disabled.")


# ---------------------------------------------------------------------------
# AWS S3 helpers Ã¢â‚¬â€ optional and fail-safe
# ---------------------------------------------------------------------------
_AWS_S3_AVAILABLE: bool = False
_S3_CLIENT_ERROR: Any = Exception
_S3_CONFIG_CLASS: Any = None
try:
    import boto3  # type: ignore
    from botocore.config import Config as BotoConfig  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore

    _AWS_S3_AVAILABLE = True
    _S3_CLIENT_ERROR = ClientError
    _S3_CONFIG_CLASS = BotoConfig
except ImportError:
    logger.warning("LogBuilder: boto3 not available Ã¢â‚¬â€ AWS S3 upload disabled.")


def _get_cos_client() -> Any:
    """Return a configured IBM COS S3-compatible client or None."""
    if not _COS_AVAILABLE:
        return None
    api_key = os.getenv("IBM_COS_API_KEY")
    service_instance_id = os.getenv("IBM_COS_SERVICE_INSTANCE_ID")
    endpoint = os.getenv("IBM_COS_ENDPOINT", "https://s3.us.cloud-object-storage.appdomain.cloud")
    if not api_key or not service_instance_id:
        return None
    try:
        return ibm_boto3.client(  # type: ignore
            "s3",
            ibm_api_key_id=api_key,
            ibm_service_instance_id=service_instance_id,
            config=Config(signature_version="oauth"),
            endpoint_url=endpoint,
        )
    except Exception as exc:
        logger.error("LogBuilder: COS client init failed Ã¢â‚¬â€ %s", exc)
        return None


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_aws_s3_client() -> Any:
    """Return configured boto3 S3 client, or None when unavailable."""
    if not _AWS_S3_AVAILABLE:
        return None

    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL")

    kwargs: dict[str, Any] = {
        "region_name": region,
    }
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if _as_bool(os.getenv("AWS_S3_DISABLE_PROXY"), default=False) and _S3_CONFIG_CLASS is not None:
        kwargs["config"] = _S3_CONFIG_CLASS(proxies={})

    try:
        return boto3.client("s3", **kwargs)  # type: ignore[name-defined]
    except Exception as exc:
        logger.error("LogBuilder: AWS S3 client init failed Ã¢â‚¬â€ %s", exc)
        return None


# ---------------------------------------------------------------------------
# LogBuilder
# ---------------------------------------------------------------------------

class LogBuilder:
    """
    Builds and dispatches the complete structured audit log record.

    The record is:
    1. Appended to an in-memory COS batch buffer (flushed to IBM COS)
    2. Written line-by-line to the local Wazuh forwarder NDJSON file

    Attributes
    ----------
    wazuh_log_path:
        Absolute path to the NDJSON file read by the Wazuh agent.
        Defaults to backend/app/wazuh/forwarder/fraud_logs.json.
    cos_bucket:
        IBM COS bucket name for log archival.
    cos_prefix:
        Key prefix for COS objects (e.g. "fraud-logs/2024/").
    """

    def __init__(
        self,
        wazuh_log_path: Optional[str] = None,
        cos_bucket: Optional[str] = None,
        cos_prefix: str = "fraud-logs/",
    ) -> None:
        from app.wazuh.forwarder.forwarder import get_forwarder

        self._forwarder = get_forwarder() if wazuh_log_path is None else None
        self._wazuh_path = wazuh_log_path
        self._cos_bucket = cos_bucket or os.getenv("IBM_COS_BUCKET", "fraud-platform-logs")
        self._cos_prefix = cos_prefix
        self._cos_client = _get_cos_client()
        self._cos_batch_size = 50
        self._cos_batch: list[dict[str, Any]] = []

        # AWS S3 archival (optional, durable queue-backed)
        self._aws_s3_enabled = _as_bool(os.getenv("AWS_S3_ENABLED"), default=False)
        self._aws_s3_bucket = os.getenv("AWS_S3_BUCKET", "")
        prefix = os.getenv("AWS_S3_PREFIX", "fraud-logs/").strip()
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"
        self._aws_s3_prefix = prefix
        ext = os.getenv("AWS_S3_OBJECT_EXTENSION", ".txt").strip()
        if not ext:
            ext = ".txt"
        if not ext.startswith("."):
            ext = f".{ext}"
        self._aws_object_extension = ext.lower()
        self._aws_single_file_key = os.getenv("AWS_S3_SINGLE_FILE_KEY", "fraud logs.txt").strip() or "fraud logs.txt"
        self._aws_s3_client = _get_aws_s3_client() if self._aws_s3_enabled else None

        pending_default = Path(__file__).resolve().parents[3] / "runtime" / "s3_pending_logs.ndjson"
        pending_override = os.getenv("AWS_S3_PENDING_PATH")
        if pending_override and pending_override.strip():
            self._aws_pending_path = Path(pending_override.strip())
        else:
            self._aws_pending_path = pending_default
        self._aws_pending_path.parent.mkdir(parents=True, exist_ok=True)

        sequence_default = Path(__file__).resolve().parents[3] / "runtime" / "s3_sequence_counter.txt"
        sequence_override = os.getenv("AWS_S3_SEQUENCE_PATH")
        if sequence_override and sequence_override.strip():
            self._aws_sequence_path = Path(sequence_override.strip())
        else:
            self._aws_sequence_path = sequence_default
        self._aws_sequence_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._aws_sequence_path.exists():
            self._aws_sequence_path.write_text("0", encoding="utf-8")

        self._aws_flush_every_n_records = max(1, int(os.getenv("AWS_S3_FLUSH_EVERY_N_RECORDS", "25")))
        self._aws_records_per_object = max(1, int(os.getenv("AWS_S3_RECORDS_PER_OBJECT", "200")))
        self._aws_max_objects_per_flush = max(1, int(os.getenv("AWS_S3_MAX_OBJECTS_PER_FLUSH", "3")))
        self._aws_records_since_flush = 0
        self._aws_last_flush_attempt_ts = 0.0
        self._aws_flush_min_interval_sec = max(0, int(os.getenv("AWS_S3_FLUSH_MIN_INTERVAL_SEC", "5")))
        self._aws_lock = threading.Lock()

        if self._aws_s3_enabled and not self._aws_s3_bucket:
            logger.warning("LogBuilder: AWS_S3_ENABLED=true but AWS_S3_BUCKET is empty. S3 archival is disabled until bucket is configured.")

        # Recovery-first behavior: if pending queue exists and S3 is available again,
        # try uploading immediately at startup (does not block primary flow on failure).
        if self._aws_s3_enabled and self._aws_s3_bucket:
            self._flush_aws_pending_if_due(force=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_and_dispatch(
        self,
        transaction: dict[str, Any],
        score_result: Any,  # FraudScoreResult dataclass
    ) -> dict[str, Any]:
        """
        Build the full audit log record and send it to COS + Wazuh.

        Parameters
        ----------
        transaction:
            Dict representation of the Transaction ORM object (or raw dict).
        score_result:
            FraudScoreResult dataclass instance from FraudScorer.

        Returns
        -------
        The structured log record dict that was persisted.
        """
        record = self._build_record(transaction, score_result)
        self._write_wazuh(record)
        self._write_cos(record)
        self._write_aws_s3(record)
        return record

    def flush_batch(self) -> None:
        """Force flush the current COS batch."""
        if not self._cos_batch or self._cos_client is None:
            return
            
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
            key = f"{self._cos_prefix}{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/batch_{timestamp}_{uuid.uuid4().hex[:8]}.ndjson"
            
            body = "".join(json.dumps(r, default=str) + "\n" for r in self._cos_batch)
            self._cos_client.put_object(
                Bucket=self._cos_bucket,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/x-ndjson",
            )
            logger.info("LogBuilder: Flushed batch of %d records to COS at %s", len(self._cos_batch), key)
        except Exception as exc:
            logger.error("LogBuilder: COS batch flush failed Ã¢â‚¬â€ %s", exc)
        finally:
            self._cos_batch.clear()

    def flush_aws_pending(self) -> None:
        """Force an attempt to flush queued AWS S3 logs."""
        self._flush_aws_pending_if_due(force=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_record(
        self,
        transaction: dict[str, Any],
        score_result: Any,
    ) -> dict[str, Any]:
        """Construct the canonical fraud log record."""
        tx_id = str(transaction.get("id", uuid.uuid4()))
        payload_str = json.dumps(transaction, default=str, sort_keys=True)
        integrity_hash = hashlib.sha256(payload_str.encode()).hexdigest()

        shap_features = []
        if hasattr(score_result, "top_5_shap_features"):
            for sf in score_result.top_5_shap_features:
                shap_features.append(
                    {
                        "feature_name": sf.feature_name,
                        "shap_value": sf.shap_value,
                        "feature_value": sf.feature_value,
                    }
                )

        return {
            # Event metadata
            "log_id": str(uuid.uuid4()),
            "event_type": "fraud_score_result",
            "platform": "fraud-detection-platform",
            "log_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Transaction identifiers
            "transaction_id": tx_id,
            "card_id_hash": transaction.get("card_id_hash", ""),
            "merchant_id": transaction.get("merchant_id", ""),
            "merchant_name": transaction.get("merchant_name", ""),
            "mcc": transaction.get("mcc", ""),
            # Transaction details
            "amount": transaction.get("amount", 0.0),
            "currency": transaction.get("currency", "USD"),
            "channel": transaction.get("channel", ""),
            "transaction_timestamp": str(transaction.get("created_at", "")),
            # Geo
            "geo_lat": transaction.get("geo_lat"),
            "geo_lon": transaction.get("geo_lon"),
            "geo_country": transaction.get("geo_country", ""),
            "geo_city": transaction.get("geo_city", ""),
            # Device
            "device_id": transaction.get("device_id", ""),
            "device_type": transaction.get("device_type", ""),
            "is_new_device": transaction.get("is_new_device", False),
            "ip_address": transaction.get("ip_address", ""),
            # Velocity
            "velocity_1h": transaction.get("velocity_1h", 0),
            "velocity_24h": transaction.get("velocity_24h", 0),
            # Geo risk
            "geo_distance_km": transaction.get("geo_distance_km"),
            "implied_speed_kmh": transaction.get("implied_speed_kmh"),
            "impossible_travel_flag": transaction.get("impossible_travel_flag", False),
            # ML inference results
            "fraud_score": getattr(score_result, "fraud_score", None),
            "risk_level": getattr(score_result, "risk_level", None),
            "predicted_class": getattr(score_result, "predicted_class", None),
            "model_version": getattr(score_result, "model_version", None),
            "inference_latency_ms": getattr(score_result, "inference_latency_ms", None),
            "top_shap_features": shap_features,
            # Integrity
            "payload_sha256": integrity_hash,
        }

    def _write_wazuh(self, record: dict[str, Any]) -> None:
        """Append record to Wazuh NDJSON file."""
        try:
            if self._forwarder:
                self._forwarder.append(record)
            elif self._wazuh_path:
                import json as _json
                with open(self._wazuh_path, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps(record, default=str) + "\n")
        except Exception as exc:
            logger.error("LogBuilder: Wazuh write failed Ã¢â‚¬â€ %s", exc)

    def _write_cos(self, record: dict[str, Any]) -> None:
        """Append record to local batch and flush if full."""
        if self._cos_client is None:
            return
            
        self._cos_batch.append(record)
        if len(self._cos_batch) >= self._cos_batch_size:
            self.flush_batch()

    def _write_aws_s3(self, record: dict[str, Any]) -> None:
        """
        Queue record locally for AWS S3 archival and opportunistically flush.
        Local queue guarantees no data loss when S3 is unavailable/deleted.
        """
        if not self._aws_s3_enabled:
            return

        self._append_aws_pending(record)
        self._aws_records_since_flush += 1
        self._flush_aws_pending_if_due(force=False)

    def _next_archive_sequence_locked(self) -> int:
        """Return next monotonically increasing archive sequence. Caller must hold AWS lock."""
        try:
            raw_value = self._aws_sequence_path.read_text(encoding="utf-8").strip()
            current_value = int(raw_value) if raw_value else 0
        except Exception:
            current_value = 0
        next_value = current_value + 1
        self._aws_sequence_path.write_text(str(next_value), encoding="utf-8")
        return next_value

    def _coerce_pending_record_locked(self, line: str) -> dict[str, Any]:
        """Parse one queued line and guarantee stable archive sequencing."""
        record: dict[str, Any]
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                record = parsed
            else:
                record = {"raw_payload": line}
        except Exception:
            record = {"raw_payload": line}

        try:
            sequence_value = int(record.get("archive_sequence"))
        except Exception:
            sequence_value = self._next_archive_sequence_locked()
        record["archive_sequence"] = sequence_value
        record.setdefault("archive_sequence_timestamp", datetime.now(timezone.utc).isoformat())
        return record

    def _build_aws_object_key(self, *, first_sequence: int, last_sequence: int) -> str:
        if self._aws_single_file_key:
            return self._aws_single_file_key
        ts = datetime.now(timezone.utc)
        return (
            f"{self._aws_s3_prefix}date={ts.strftime('%Y-%m-%d')}/hour={ts.strftime('%H')}/"
            f"seq_{first_sequence:012d}_{last_sequence:012d}{self._aws_object_extension}"
        )

    def _append_chunk_to_aws_single_file(self, *, key: str, chunk_body: str) -> None:
        existing_text = ""
        try:
            response = self._aws_s3_client.get_object(Bucket=self._aws_s3_bucket, Key=key)
            existing_bytes = response["Body"].read()
            if existing_bytes:
                existing_text = existing_bytes.decode("utf-8")
        except _S3_CLIENT_ERROR as exc:
            error_code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
            if error_code not in {"NoSuchKey", "404", "NotFound"}:
                raise

        if existing_text and not existing_text.endswith("\n"):
            existing_text = f"{existing_text}\n"
        combined = f"{existing_text}{chunk_body}"
        self._aws_s3_client.put_object(
            Bucket=self._aws_s3_bucket,
            Key=key,
            Body=combined.encode("utf-8"),
            ContentType="text/plain",
        )

    def _append_aws_pending(self, record: dict[str, Any]) -> None:
        try:
            with self._aws_lock:
                payload = dict(record)
                if payload.get("archive_sequence") is None:
                    payload["archive_sequence"] = self._next_archive_sequence_locked()
                payload.setdefault("archive_sequence_timestamp", datetime.now(timezone.utc).isoformat())
                line = json.dumps(payload, default=str) + "\n"
                with open(self._aws_pending_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception as exc:
            logger.error("LogBuilder: failed writing AWS pending queue at %s - %s", self._aws_pending_path, exc)
    def _flush_aws_pending_if_due(self, *, force: bool) -> None:
        if not self._aws_s3_enabled:
            return
        if not self._aws_s3_bucket:
            return
        now = time.time()
        if not force:
            if self._aws_records_since_flush < self._aws_flush_every_n_records:
                return
            if (now - self._aws_last_flush_attempt_ts) < self._aws_flush_min_interval_sec:
                return
        self._aws_last_flush_attempt_ts = now
        self._aws_records_since_flush = 0
        self._flush_aws_pending()
    def _flush_aws_pending(self) -> None:
        # Re-attempt client init each flush so recreated credentials/services recover automatically.
        if self._aws_s3_client is None:
            self._aws_s3_client = _get_aws_s3_client()
        if self._aws_s3_client is None:
            return
        with self._aws_lock:
            if not self._aws_pending_path.exists():
                return
            try:
                lines = self._aws_pending_path.read_text(encoding="utf-8").splitlines()
            except Exception as exc:
                logger.error("LogBuilder: failed reading AWS pending queue - %s", exc)
                return
            if not lines:
                return
            cursor = 0
            objects_uploaded = 0
            while cursor < len(lines) and objects_uploaded < self._aws_max_objects_per_flush:
                next_cursor = min(cursor + self._aws_records_per_object, len(lines))
                chunk_lines = lines[cursor:next_cursor]
                chunk_records = [self._coerce_pending_record_locked(line) for line in chunk_lines]
                chunk_records.sort(key=lambda item: int(item.get("archive_sequence", 0)))
                first_sequence = int(chunk_records[0].get("archive_sequence", 0))
                last_sequence = int(chunk_records[-1].get("archive_sequence", 0))
                chunk_body = "\n".join(json.dumps(record, default=str) for record in chunk_records) + "\n"
                key = self._build_aws_object_key(
                    first_sequence=first_sequence,
                    last_sequence=last_sequence,
                )
                try:
                    if self._aws_single_file_key:
                        self._append_chunk_to_aws_single_file(key=key, chunk_body=chunk_body)
                    else:
                        content_type = "text/plain" if self._aws_object_extension == ".txt" else "application/x-ndjson"
                        self._aws_s3_client.put_object(
                            Bucket=self._aws_s3_bucket,
                            Key=key,
                            Body=chunk_body.encode("utf-8"),
                            ContentType=content_type,
                        )
                    cursor = next_cursor
                    objects_uploaded += 1
                except _S3_CLIENT_ERROR as exc:
                    logger.warning(
                        "LogBuilder: AWS S3 put_object failed (bucket=%s key=%s seq=%s-%s). Queue retained for retry. Error: %s",
                        self._aws_s3_bucket,
                        key,
                        first_sequence,
                        last_sequence,
                        exc,
                    )
                    break
                except Exception as exc:
                    logger.warning(
                        "LogBuilder: AWS S3 upload error (key=%s seq=%s-%s); queue retained for retry - %s",
                        key,
                        first_sequence,
                        last_sequence,
                        exc,
                    )
                    break
            remaining = lines[cursor:]
            try:
                if remaining:
                    self._aws_pending_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
                else:
                    self._aws_pending_path.write_text("", encoding="utf-8")
                if objects_uploaded > 0:
                    logger.info(
                        "LogBuilder: uploaded %d AWS S3 log object(s); %d record(s) remaining in queue.",
                        objects_uploaded,
                        len(remaining),
                    )
            except Exception as exc:
                logger.error("LogBuilder: failed updating AWS pending queue after flush - %s", exc)

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_default_log_builder: Optional[LogBuilder] = None


def get_log_builder() -> LogBuilder:
    """Return the module-level LogBuilder singleton."""
    global _default_log_builder
    if _default_log_builder is None:
        _default_log_builder = LogBuilder()
    return _default_log_builder

