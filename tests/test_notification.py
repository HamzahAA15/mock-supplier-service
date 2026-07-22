"""Wallet Notification API (POST /notification) — partner-side receiver.

Payloads mirror the JSON examples in the wallet-payment integration wiki
(section 4.7); at-least-once delivery is deduplicated on referenceId.
"""


def payment_success_body(reference_id="WALLET_YEEPAY-FL-partner-105445301-PO12345-00"):
    return {
        "eventType": "payment.success",
        "referenceId": reference_id,
        "providerOrderId": "PO12345",
        "amount": "150000.00",
        "currency": "USD",
        "receiverAccount": "120180123",
        "paidAt": "2026-06-29T08:30:00Z",
        "timestamp": "2026-06-29T08:30:05Z",
    }


def refund_success_body(reference_id="WALLET_ANTOM-FC-partner-9411124-PO12345-01"):
    return {
        "eventType": "refund.success",
        "referenceId": reference_id,
        "providerOrderId": "PO12345",
        "amount": "70000.00",
        "currency": "USD",
        "receiverAccount": "120180999",
        "originPaymentId": "202001021234567890",
        "refundedAt": "2026-06-29T08:30:00Z",
        "timestamp": "2026-06-29T08:30:05Z",
    }


def test_payment_success_acknowledged(client):
    body = payment_success_body()
    res = client.post("/notification", json=body)
    assert res.status_code == 200
    assert res.json() == {"referenceId": body["referenceId"], "status": "ACKNOWLEDGED"}


def test_refund_success_acknowledged(client):
    body = refund_success_body()
    res = client.post("/notification", json=body)
    assert res.status_code == 200
    assert res.json() == {"referenceId": body["referenceId"], "status": "ACKNOWLEDGED"}


def test_replayed_reference_id_is_duplicate_not_error(client):
    body = payment_success_body()
    first = client.post("/notification", json=body)
    second = client.post("/notification", json=body)
    assert first.json()["status"] == "ACKNOWLEDGED"
    assert second.status_code == 200
    assert second.json() == {"referenceId": body["referenceId"], "status": "DUPLICATE"}


def test_distinct_reference_ids_both_acknowledged(client):
    first = client.post("/notification", json=payment_success_body("WALLET_ANTOM-A-00"))
    second = client.post("/notification", json=payment_success_body("WALLET_ANTOM-A-01"))
    assert first.json()["status"] == "ACKNOWLEDGED"
    assert second.json()["status"] == "ACKNOWLEDGED"


def test_missing_required_field_is_permanent_400(client):
    body = payment_success_body()
    del body["receiverAccount"]
    res = client.post("/notification", json=body)
    assert res.status_code == 400
    assert "receiverAccount" in res.json()["error"]


def test_unknown_event_type_is_permanent_400(client):
    body = payment_success_body()
    body["eventType"] = "payment.pending"
    res = client.post("/notification", json=body)
    assert res.status_code == 400
    assert "payment.pending" in res.json()["error"]


def test_optional_fields_are_optional(client):
    body = payment_success_body()
    del body["paidAt"]
    res = client.post("/notification", json=body)
    assert res.status_code == 200
    assert res.json()["status"] == "ACKNOWLEDGED"


def test_inspection_endpoint_lists_received(client):
    client.post("/notification", json=payment_success_body())
    client.post("/notification", json=payment_success_body())  # duplicate
    client.post("/notification", json=refund_success_body())
    res = client.get("/notifications")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 3
    statuses = [n["status"] for n in data["notifications"]]
    assert statuses == ["ACKNOWLEDGED", "DUPLICATE", "ACKNOWLEDGED"]
    assert data["notifications"][2]["payload"]["eventType"] == "refund.success"
    assert data["notifications"][2]["payload"]["originPaymentId"] == "202001021234567890"


def test_store_resets_between_tests(client):
    res = client.get("/notifications")
    assert res.json()["count"] == 0
