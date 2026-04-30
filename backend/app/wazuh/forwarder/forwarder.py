"""
Wazuh NDJSON Forwarder — appends structured fraud log records to the
NDJSON file that the Wazuh agent monitors for rule evaluation.

This module ONLY writes to the file. Wazuh is configured externally
to watch the target path (e.g. via ossec.conf localfile stanza).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default log file path — overridable via WAZUH_FORWARDER_PATH env var
# ---------------------------------------------------------------------------
DEFAULT_LOG_PATH: str = str(
    Path(__file__).parent / "fraud_logs.json"
)

# Thread lock guards concurrent writes from multiple Celery workers
_write_lock = threading.Lock()


class WazuhForwarder:
    """
    Appends one JSON object per line (NDJSON format) to a file that
    the locally-installed Wazuh agent is configured to monitor.

    The file is opened in append mode per write to be safe across
    multi-process Celery workers on the same host.
    """

    def __init__(self, log_path: str | None = None) -> None:
        self._log_path = Path(
            log_path
            or os.getenv("WAZUH_FORWARDER_PATH", DEFAULT_LOG_PATH)
        )
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        """
        Append a single structured log record to the NDJSON file.

        Parameters
        ----------
        record:
            Serialisable dict. Keys should follow the Wazuh log schema
            defined in the system design (see log_builder.py).
        """
        try:
            line = json.dumps(record, default=str) + "\n"
            with _write_lock:
                with open(self._log_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception as exc:
            logger.error(
                "WazuhForwarder: failed to write record to %s — %s",
                self._log_path,
                exc,
            )

    def get_log_path(self) -> str:
        """Return the absolute path of the monitored log file."""
        return str(self._log_path.resolve())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_default_forwarder: WazuhForwarder | None = None


def get_forwarder() -> WazuhForwarder:
    """Return the module-level WazuhForwarder singleton."""
    global _default_forwarder
    if _default_forwarder is None:
        _default_forwarder = WazuhForwarder()
    return _default_forwarder
