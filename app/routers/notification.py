"""Wallet Notification API — the partner-side receiver Traveloka calls.

POST /notification per the "Supplier Integration Guideline, Traveloka Wallet
Payment (Antom / YeePay)" wiki, section 4: Traveloka notifies the partner
whenever a wallet payment or refund completes. Delivery is at least once, so
the receiver deduplicates on ``referenceId`` (replay -> status DUPLICATE).

Contract semantics for failures: any non-2xx triggers Traveloka's retries with
exponential backoff, except 4xx (other than 408/429) which is permanent — so a
malformed body is rejected with HTTP 400 (retrying it would never succeed).

GET /notifications is a mock-only convenience (not part of the contract) so
testers can assert what was delivered.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.notification import NotificationRequest
from app.services.notifications import EVENT_TYPES, store

router = APIRouter()

_REQUIRED_FIELDS = (
    ("eventType", "event_type"),
    ("referenceId", "reference_id"),
    ("providerOrderId", "provider_order_id"),
    ("amount", "amount"),
    ("currency", "currency"),
    ("receiverAccount", "receiver_account"),
    ("timestamp", "timestamp"),
)


@router.post("/notification")
def notification(req: NotificationRequest):
    missing = [wire for wire, attr in _REQUIRED_FIELDS if not getattr(req, attr)]
    if missing:
        return JSONResponse(
            {"error": "missing required fields: {}".format(", ".join(missing))},
            status_code=400,
        )
    if req.event_type not in EVENT_TYPES:
        return JSONResponse(
            {"error": "unknown eventType: {}".format(req.event_type)},
            status_code=400,
        )

    payload = req.model_dump(by_alias=True, exclude_none=True)
    status = store.record(payload)
    return {"referenceId": req.reference_id, "status": status}


@router.get("/notifications")
def list_notifications():
    received = store.list()
    return {"count": len(received), "notifications": received}
