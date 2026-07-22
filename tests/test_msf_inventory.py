"""MODIFIED_SERVICE_FEE inventory sourcing — the 70% cap guideline (Lark doc,
Jul 17 2026), modeled as offer_override scenario presets on the search endpoint.

Three sourced inventory cases:
  1. msf_cap_violation  — serviceFeePerPax + highest airline penalty > 70% of
                          ADT total fare (Traveloka should reject/filter)
  2. msf_valid          — serviceFeePerPax + highest airline penalty == the 70%
                          cap (valid, fee at maximum allowed)
  3. basic_high_penalty — airline penalty alone > 70% of ADT total fare, BASIC
                          tag only (supplier not allowed to use MSF)

Canonical fixture GA (fare 7.00 + tax 2.00 = ADT total 9.00, cap 6.30),
KNO->CGK per TEST_CASES.md conventions.
"""
import pytest

from app import config
from app.services import inventory
from tests.conftest import order_body, search_body


MSF_PRODUCT = ["BASIC", "MODIFIED_SERVICE_FEE"]


def _put_rule(client, headers, preset, airline="GA", origin="KNO", destination="CGK",
              **extra):
    body = {"endpoint": "search", "airline": airline, "origin": origin,
            "destination": destination, "preset": preset}
    body.update(extra)
    return client.put("/admin/rules", json=body, headers=headers)


def _search(client, product=MSF_PRODUCT, **kwargs):
    kwargs.setdefault("ori", "KNO")
    kwargs.setdefault("dest", "CGK")
    rs = client.post("/flight/search/v3",
                     json=search_body(product=product, **kwargs)).json()
    assert rs["code"] == 0, rs
    return rs["data"]


def _all_penalty_amounts(flight):
    amounts = []
    for ref in flight["refundRefs"] + flight["changeRefs"]:
        assert ref["sourcePolicy"] == "AIRLINE_POLICY"  # eligibility never modified
        amounts.extend(p["amount"] for p in ref["periodAndFees"])
    return amounts


# ---------------------------------------------------------------------------
# Case 2 — valid: fee + highest penalty lands exactly on the 70% cap
# ---------------------------------------------------------------------------

def test_msf_valid_offer_at_cap(client, admin_headers):
    assert _put_rule(client, admin_headers, "msf_valid").status_code == 200
    data = _search(client, airlineIds=["GA"])
    offer, flight = data["offers"][0], data["flights"][0]

    assert offer["product"] == MSF_PRODUCT
    cap = round(0.70 * inventory.adt_total_fare("GA"), 2)  # 6.30
    highest = max(_all_penalty_amounts(flight))            # 4.50 (50% refund, <=48h)
    assert highest == 4.50
    assert offer["serviceFeePerPax"] == round(cap - highest, 2)  # 1.80
    assert round(highest + offer["serviceFeePerPax"], 2) <= cap

    # Both actions get the two guideline-style periods; refund is refundable.
    refund_periods = flight["refundRefs"][0]["periodAndFees"]
    assert [p["amount"] for p in refund_periods] == [2.25, 4.50]
    assert all(p["refundable"] for p in refund_periods)
    assert [p["amount"] for p in flight["changeRefs"][0]["periodAndFees"]] == [1.35, 2.70]


# ---------------------------------------------------------------------------
# Case 1 — violation: fee + highest penalty above the 70% cap
# ---------------------------------------------------------------------------

def test_msf_cap_violation_offer_above_cap(client, admin_headers):
    _put_rule(client, admin_headers, "msf_cap_violation")
    data = _search(client, airlineIds=["GA"])
    offer, flight = data["offers"][0], data["flights"][0]

    assert offer["product"] == MSF_PRODUCT
    assert offer["serviceFeePerPax"] == 2.70  # 30% of 9.00
    cap = round(0.70 * inventory.adt_total_fare("GA"), 2)
    highest = max(_all_penalty_amounts(flight))
    assert round(highest + offer["serviceFeePerPax"], 2) > cap  # 7.20 > 6.30


# ---------------------------------------------------------------------------
# Case 3 — penalty alone above 70%: BASIC tag only, no fee
# ---------------------------------------------------------------------------

def test_basic_high_penalty_offer_is_basic_only(client, admin_headers):
    _put_rule(client, admin_headers, "basic_high_penalty")
    # Even when the request asks for MSF, this inventory must stay BASIC-only.
    data = _search(client, airlineIds=["GA"])
    offer, flight = data["offers"][0], data["flights"][0]

    assert offer["product"] == ["BASIC"]
    assert offer["serviceFeePerPax"] is None
    cap = round(0.70 * inventory.adt_total_fare("GA"), 2)
    assert max(_all_penalty_amounts(flight)) > cap  # 6.75 (75%) > 6.30


# ---------------------------------------------------------------------------
# Cap math holds for every airline (percent-of-fare profiles)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("airline", config.AIRLINE_ORDER)
def test_cap_math_per_airline(airline):
    cap = round(0.70 * inventory.adt_total_fare(airline), 2)
    valid_fee = inventory.msf_fee_per_pax(airline, "msf_valid")
    assert round(inventory.msf_highest_penalty(airline, "msf_valid") + valid_fee, 2) <= cap
    bad_fee = inventory.msf_fee_per_pax(airline, "msf_cap_violation")
    assert round(inventory.msf_highest_penalty(airline, "msf_cap_violation") + bad_fee, 2) > cap
    assert inventory.msf_fee_per_pax(airline, "basic_high_penalty") is None
    assert inventory.msf_highest_penalty(airline, "basic_high_penalty") > cap


# ---------------------------------------------------------------------------
# Product tag rules (guideline: never standalone, only when requested)
# ---------------------------------------------------------------------------

def test_msf_not_returned_when_not_requested(client, admin_headers):
    _put_rule(client, admin_headers, "msf_valid")
    data = _search(client, product=["BASIC"], airlineIds=["GA"])
    offer, flight = data["offers"][0], data["flights"][0]

    # Offer degrades to BASIC with a null fee...
    assert offer["product"] == ["BASIC"]
    assert offer["serviceFeePerPax"] is None
    # ...but the penalty profile still applies (airline policy, not a product).
    assert max(_all_penalty_amounts(flight)) == 4.50


def test_msf_rule_only_shapes_matched_airline(client, admin_headers):
    _put_rule(client, admin_headers, "msf_valid")
    data = _search(client)  # all airlines
    by_carrier = {data["segments"][i]["marketingCarrier"]: o
                  for i, o in enumerate(data["offers"])}
    assert by_carrier["GA"]["product"] == MSF_PRODUCT
    for carrier, offer in by_carrier.items():
        if carrier != "GA":
            assert offer["product"] == ["BASIC"]
            assert offer["serviceFeePerPax"] is None
    assert len(by_carrier) == 8  # offer_override keeps the airline in results


# ---------------------------------------------------------------------------
# Downstream consistency — product identifier in all adjusted APIs
# ---------------------------------------------------------------------------

def test_msf_flows_through_verify_order_and_detail(client, admin_headers):
    _put_rule(client, admin_headers, "msf_valid")
    offer_key = _search(client, airlineIds=["GA"])["offers"][0]["offerKey"]

    verify = client.post("/flight/preOrderVerify/v3", json={"offerKey": offer_key}).json()
    assert verify["code"] == 0
    assert verify["data"]["offers"][0]["product"] == MSF_PRODUCT
    assert verify["data"]["offers"][0]["serviceFeePerPax"] == 1.80

    order = client.post("/flight/order/v3", json=order_body(offer_key)).json()
    assert order["code"] == 0
    assert order["data"]["product"] == MSF_PRODUCT
    assert order["data"]["serviceFeePerPax"] == 1.80
    # The fee is charged at refund/reschedule time, never at purchase.
    assert order["data"]["total"] == 9.00

    order_id = order["data"]["orderId"]
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert detail["code"] == 0
    assert detail["data"]["orderInfo"]["product"] == MSF_PRODUCT
    assert detail["data"]["orderInfo"]["serviceFeePerPax"] == 1.80
    assert max(_all_penalty_amounts(detail["data"]["flights"][0])) == 4.50


# ---------------------------------------------------------------------------
# Admin validation — offer_override presets take no code/msg overrides
# ---------------------------------------------------------------------------

def test_msf_preset_rejects_code_msg_overrides(client, admin_headers):
    res = _put_rule(client, admin_headers, "msf_valid", code=500, msg="boom")
    assert res.status_code == 422

    res = client.get("/admin/presets", headers=admin_headers)
    search_presets = next(e for e in res.json()["endpoints"]
                          if e["id"] == "search")["presets"]
    assert {"msf_valid", "msf_cap_violation", "basic_high_penalty"} <= set(search_presets)
