"""Scenario rules — cross-feature interaction (group C) and regression
spot-checks (group D): SCN-20..28, 32, 33, 34. See SCENARIO_RULES_DESIGN.md
section 9. Rules are injected through the admin API (admin_headers fixture)."""
import json

import pytest

from app.services.offer_key import encode_offer_key
from app.services.standardized_bpi_catalog import encode_ancillary_key
from tests import bpi_helpers as tsy
from tests import standardized_bpi_helpers as std
from tests.conftest import future_date, order_body, search_body


def _put_rule(client, headers, endpoint, airline, origin, destination, preset,
              **extra):
    body = {"endpoint": endpoint, "airline": airline, "origin": origin,
            "destination": destination, "preset": preset}
    body.update(extra)
    res = client.put("/admin/rules", json=body, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["rule"]


def _offer_key(airline="GA", ori="KNO", dest="CGK"):
    return encode_offer_key(airline, ori, dest, future_date())


def _create_order(client, airline="GA", ori="KNO", dest="CGK"):
    rs = client.post("/flight/order/v3",
                     json=order_body(_offer_key(airline, ori, dest))).json()
    assert rs["code"] == 0
    return rs["data"]["orderId"]


def _pay(client, order_id):
    return client.post("/flight/pay/v3",
                       json={"orderId": order_id, "payType": "BPA"}).json()


def _detail(client, order_id):
    return client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()


# ---------------------------------------------------------------------------
# Group C — cross-feature interaction
# ---------------------------------------------------------------------------

def test_scn20_search_rule_containment(client, admin_headers):
    # Capture an offerKey from a clean search first.
    clean = client.post("/flight/search/v3",
                        json=search_body(ori="KNO", dest="CGK", airlineIds=["GA"])).json()
    offer_key = clean["data"]["offers"][0]["offerKey"]

    _put_rule(client, admin_headers, "search", "GA", "KNO", "CGK", "no_results")

    # Old offerKey still verifies and orders (search rule is contained to search).
    assert client.post("/flight/preOrderVerify/v3",
                       json={"offerKey": offer_key}).json()["code"] == 0
    assert client.post("/flight/order/v3", json=order_body(offer_key)).json()["code"] == 0

    # GA-only search: SUCCESS envelope with zero offers, not an error.
    filtered = client.post("/flight/search/v3",
                           json=search_body(ori="KNO", dest="CGK", airlineIds=["GA"])).json()
    assert filtered["code"] == 0
    assert filtered["data"]["offers"] == []
    assert filtered["data"]["segments"] == []

    # Unrestricted search: GA filtered out, everyone else still present.
    full = client.post("/flight/search/v3", json=search_body(ori="KNO", dest="CGK")).json()
    carriers = {s["marketingCarrier"] for s in full["data"]["segments"]}
    assert "GA" not in carriers and len(carriers) == 7


def test_scn21_pay_and_order_detail_match_via_stored_order(client, admin_headers):
    # The pay/orderDetail RQs only carry the orderId; rules are still keyed on
    # the stored order's airline+route.
    order_id = _create_order(client, "GA", "KNO", "CGK")
    _put_rule(client, admin_headers, "pay", "GA", "KNO", "CGK", "payment_declined")
    _put_rule(client, admin_headers, "orderDetail", "GA", "KNO", "CGK", "order_not_found")
    assert _pay(client, order_id)["code"] == 501
    assert _detail(client, order_id)["code"] == 148


def test_scn22_rule_added_and_deleted_mid_flow(client, admin_headers):
    order_id = _create_order(client)
    rule = _put_rule(client, admin_headers, "pay", "GA", "KNO", "CGK", "payment_declined")
    assert _pay(client, order_id)["code"] == 501  # applies immediately
    assert client.delete("/admin/rules/{}".format(rule["rule_id"]),
                         headers=admin_headers).status_code == 200
    assert _pay(client, order_id)["code"] == 0    # stops applying immediately


def test_scn23_ancillary_no_results_then_plain_order(client, admin_headers):
    _put_rule(client, admin_headers, "ancillarySearch", "GA", "KNO", "CGK", "no_results")
    rs = client.post("/flight/ancillary/search/v3",
                     json={"offerKey": _offer_key()}).json()
    # Schema-valid success with an empty offer list, not an error.
    assert rs["code"] == 0
    assert rs["data"]["ancillaryOffers"] == []
    assert rs["data"]["currency"] == "USD"
    # A subsequent order without ancillaries still works.
    assert _create_order(client)


def test_scn24_tsy_encryption_symmetry_on_non_seed_route(client, admin_headers):
    # Non-seed route (GA CGK->DPS) so the failure comes from the injected rule.
    _put_rule(client, admin_headers, "tsy.order", "GA", "CGK", "DPS", "route_blocked")
    rs = client.post("/secondBaggage", json=tsy.search_body(segments=[tsy.SEG_GA])).json()
    item = tsy.product_item_for(rs, 0, 20)
    body = tsy.order_body("SCN24-ENC", [tsy.pax_aux(tsy.SEG_GA, item)])

    # Encrypted request -> HTTP 500 with an ENCRYPTED body (symmetric channel).
    res = tsy.post_encrypted_order(client, body)
    assert res.status_code == 500
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.text)  # raw body is ciphertext, not JSON
    decrypted = tsy.decrypt_order_response(res)
    assert decrypted["status"] == "1"
    assert decrypted["auxiliaryOrderNo"] is None
    assert "CGK-DPS" in decrypted["msg"]

    # Plaintext request -> plaintext 500.
    res = client.post("/orderCrossSecondBaggage", json=body)
    assert res.status_code == 500
    assert "CGK-DPS" in res.json()["msg"]
    # The order was never created.
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "SCN24-ENC"}).json()
    assert det["status"] == "1" and det["data"] is None


def test_scn25_std_failure_is_http_200_envelope(client):
    # Seed rule route: the failure is a business envelope, never HTTP 5xx.
    res = client.post(std.BASE_SEARCH_PATH, json=std.search_body(
        routes=[{"tripType": 1, "segments": [std.blocked_segment()]}]))
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 555 and body["data"] is None


def test_scn26_tsy_and_std_contracts_are_independent(client, admin_headers):
    # Negative on TSY only (GA CGK->DPS): the standardized contract for the
    # same airline+route keeps working.
    _put_rule(client, admin_headers, "tsy.order", "GA", "CGK", "DPS", "route_blocked")
    routes = [{"tripType": 1, "segments": [std.segment(
        marketing="GA", flight_no="GA200", dep="CGK", arr="DPS")]}]
    search_rs, order_rs = std.search_then_order(client, order_no="SCN26-STD",
                                                routes=routes)
    assert search_rs["code"] == 0 and order_rs["code"] == 0


def test_scn27_stuck_issuing_uses_each_contracts_vocabulary(client, admin_headers):
    # Core orderDetail: ISSUING + blanked tickets (mock-chosen vocab).
    order_id = _create_order(client, "GA", "KNO", "CGK")
    assert _pay(client, order_id)["code"] == 0
    _put_rule(client, admin_headers, "orderDetail", "GA", "KNO", "CGK", "stuck_issuing")
    detail = _detail(client, order_id)
    assert detail["code"] == 0
    assert detail["data"]["orderInfo"]["status"] == "ISSUING"
    assert all(p["ticketNumber"] == "" for p in detail["data"]["pnrs"][0]["passengers"])

    # Standardized orderDetail: orderStatus ISSUING.
    std.search_then_order(client, order_no="SCN27-STD")
    _put_rule(client, admin_headers, "std.orderDetail", "AK", "CGK", "BKI", "stuck_issuing")
    std_detail = client.get("{}/{}".format(std.ORDER_PATH, "SCN27-STD")).json()
    assert std_detail["code"] == 0
    assert std_detail["data"]["orderStatus"] == "ISSUING"

    # TSY orderDetail: PROCESSING (TSY only documents PURCHASED).
    rs = client.post("/secondBaggage", json=tsy.search_body()).json()
    item = tsy.product_item_for(rs, 0, 20)
    client.post("/orderCrossSecondBaggage",
                json=tsy.order_body("SCN27-TSY", [tsy.pax_aux(tsy.SEG_VJ, item)]))
    _put_rule(client, admin_headers, "tsy.orderDetail", "VJ", "BNE", "SGN", "stuck_issuing")
    tsy_detail = client.post("/ancillaryOrderDetail",
                             json={"auxiliaryOrderNo": "SCN27-TSY"}).json()
    assert tsy_detail["status"] == "0"
    assert tsy_detail["data"]["orderStatus"] == "PROCESSING"


def test_scn28_order_not_found_rule_with_valid_order_id(client, admin_headers):
    # The rule-injected 148 with a VALID orderId is byte-identical to the
    # genuine bogus-orderId path — same shape, different trigger.
    genuine = _detail(client, "0000000000")
    order_id = _create_order(client, "GA", "KNO", "CGK")
    _put_rule(client, admin_headers, "orderDetail", "GA", "KNO", "CGK", "order_not_found")
    injected = _detail(client, order_id)
    assert injected == genuine
    assert injected["code"] == 148 and injected["data"] is None


# ---------------------------------------------------------------------------
# Group D — regression spot-checks (SCN-30/31 are release gates, not tests)
# ---------------------------------------------------------------------------

def test_scn32_deleting_seed_rule_unblocks_route(client, admin_headers):
    # Blocking is truly rule-driven: drop the tsy.order SIN->KUL seed and the
    # previously blocked route orders fine.
    rules_list = client.get("/admin/rules", headers=admin_headers).json()["rules"]
    seed = next(r for r in rules_list
                if r["endpoint"] == "tsy.order" and r["origin"] == "SIN"
                and r["destination"] == "KUL")
    assert seed["seed"] is True
    assert client.delete("/admin/rules/{}".format(seed["rule_id"]),
                         headers=admin_headers).status_code == 200

    rs = client.post("/secondBaggage", json=tsy.search_body(segments=[tsy.SEG_SIN_KUL])).json()
    item = tsy.product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage",
                      json=tsy.order_body("SCN32-OK", [tsy.pax_aux(tsy.SEG_SIN_KUL, item)]))
    assert res.status_code == 200
    assert res.json()["status"] == "0"
    # SIN->CGK stays blocked (only one seed was deleted).
    rs = client.post("/secondBaggage", json=tsy.search_body(segments=[tsy.SEG_SIN_CGK])).json()
    item = tsy.product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage",
                      json=tsy.order_body("SCN32-BLK", [tsy.pax_aux(tsy.SEG_SIN_CGK, item)]))
    assert res.status_code == 500


def test_scn33_golden_path_with_unrelated_rule(client, admin_headers):
    # A rule for another airline+route must have zero bystander effect.
    _put_rule(client, admin_headers, "order", "JT", "SUB", "DPS", "order_failed")
    search = client.post("/flight/search/v3",
                         json=search_body(ori="KNO", dest="CGK", airlineIds=["GA"])).json()
    assert search["code"] == 0
    offer_key = search["data"]["offers"][0]["offerKey"]
    assert client.post("/flight/preOrderVerify/v3",
                       json={"offerKey": offer_key}).json()["code"] == 0
    order = client.post("/flight/order/v3", json=order_body(offer_key)).json()
    assert order["code"] == 0
    order_id = order["data"]["orderId"]
    assert _pay(client, order_id)["code"] == 0
    detail = _detail(client, order_id)
    assert detail["code"] == 0
    assert detail["data"]["orderInfo"]["status"] == "ISSUED"


def test_scn34_seed_parity_blocks_any_airline(client):
    # The deleted BLOCKED_SECOND_BAGGAGE_ROUTES was carrier-agnostic; the
    # wildcard seeds must block SIN->KUL for a different carrier (GA) too.
    seg_ga_sin_kul = dict(tsy.SEG_SIN_KUL, carrier="GA", flightNumber="GA200")

    # tsy.order: HTTP 500 for GA as well.
    rs = client.post("/secondBaggage", json=tsy.search_body(segments=[seg_ga_sin_kul])).json()
    item = tsy.product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage",
                      json=tsy.order_body("SCN34-TSY", [tsy.pax_aux(seg_ga_sin_kul, item)]))
    assert res.status_code == 500
    assert "SIN-KUL" in res.json()["msg"]

    # std.order: 555 for GA as well (key forged: search would already refuse).
    key = encode_ancillary_key(1, [std.segment(marketing="GA", flight_no="GA200",
                                               dep="SIN", arr="KUL")], 20)
    body = client.post(std.ORDER_PATH, json=std.order_body(
        "SCN34-STD", selected=[{"passengerId": 1, "ancillaryKey": key}])).json()
    assert body["code"] == 555 and body["data"] is None

    # std.baggageSearch: 555 for GA as well.
    search_rs = client.post(std.BASE_SEARCH_PATH, json=std.search_body(
        routes=[{"tripType": 1, "segments": [std.segment(
            marketing="GA", flight_no="GA200", dep="SIN", arr="KUL")]}])).json()
    assert search_rs["code"] == 555
