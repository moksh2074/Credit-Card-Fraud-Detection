import os
import requests
import logging
from typing import Any

logger = logging.getLogger(__name__)

class IBMNotifier:
    """
    Handles dispatching alerts to IBM Cloud Event Notifications or similar generic webhooks.
    """
    def __init__(self):
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL", "http://localhost:8000/api/v1/mock/webhook")
        self.email_endpoint = os.getenv("ALERT_EMAIL_ENDPOINT", "http://localhost:8000/api/v1/mock/email")
        self.api_key = os.getenv("IBM_NOTIFICATIONS_API_KEY", "")

    def send_fraud_alert(self, alert_record: dict[str, Any]) -> None:
        """
        Dispatches alerts based on severity.
        - P0/P1 go to Email.
        - P0/P1/P2 go to Webhook.
        """
        severity = alert_record.get("severity", "P3")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"} if self.api_key else {"Content-Type": "application/json"}

        # Webhook for P0, P1, P2
        if severity in ["P0", "P1", "P2"]:
            try:
                requests.post(self.webhook_url, json=alert_record, headers=headers, timeout=5)
                logger.info(f"Webhook dispatched for alert {alert_record.get('id')} with severity {severity}")
            except Exception as e:
                logger.error(f"Failed to send webhook for alert {alert_record.get('id')}: {e}")

        # Email for P0, P1
        if severity in ["P0", "P1"]:
            try:
                email_payload = {
                    "to": "fraud-analysts@example.com",
                    "subject": f"[{severity}] Fraud Alert: {alert_record.get('transaction_id')}",
                    "body": f"Fraud alert triggered. Details: {alert_record}"
                }
                requests.post(self.email_endpoint, json=email_payload, headers=headers, timeout=5)
                logger.info(f"Email dispatched for alert {alert_record.get('id')} with severity {severity}")
            except Exception as e:
                logger.error(f"Failed to send email for alert {alert_record.get('id')}: {e}")

_notifier = IBMNotifier()

def get_notifier() -> IBMNotifier:
    return _notifier
