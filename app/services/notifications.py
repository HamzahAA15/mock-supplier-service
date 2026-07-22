"""In-memory store for received wallet notifications (payment/refund events).

Implements the partner side of the "Notification API" wiki: Traveloka delivers
``payment.success`` / ``refund.success`` events at least once, and the partner
deduplicates on ``referenceId`` — a replayed referenceId is acknowledged with
status ``DUPLICATE`` instead of being processed twice.
"""
from typing import Dict, List

STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
STATUS_DUPLICATE = "DUPLICATE"

EVENT_TYPES = ("payment.success", "refund.success")


class NotificationStore:
    def __init__(self):
        self._received: List[dict] = []
        self._reference_ids: set = set()

    def record(self, payload: dict) -> str:
        """Store the notification and return the ack status for its referenceId."""
        reference_id = payload.get("referenceId")
        status = STATUS_DUPLICATE if reference_id in self._reference_ids else STATUS_ACKNOWLEDGED
        self._reference_ids.add(reference_id)
        self._received.append({"payload": payload, "status": status})
        return status

    def list(self) -> List[Dict]:
        return list(self._received)

    def clear(self) -> None:
        self._received.clear()
        self._reference_ids.clear()


store = NotificationStore()
