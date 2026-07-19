"""Scenario rules — admin API (group A, SCN-01..06) and exact-match semantics
(group B, SCN-10..15). See SCENARIO_RULES_DESIGN.md section 9."""
from app.services.offer_key import encode_offer_key
from app.services.scenario_rules import ENDPOINTS, SEED_RULES
from tests.conftest import ADMIN_KEY, future_date, order_body


def _rule(endpoint="order", airline="GA", origin="KNO", destination="CGK",
          preset=None, **extra):
    if preset is None:
        preset = {"order": "order_failed", "pay": "payment_declined",
                  "search": "no_results"}.get(endpoint, "order_not_found")
    body = {"endpoint": endpoint, "airline": airline, "origin": origin,
            "destination": destination, "preset": preset}
    body.update(extra)
    return body


# ---------------------------------------------------------------------------
# Group A — rule admin (feature in isolation)
# ---------------------------------------------------------------------------

def test_scn01_crud_lifecycle(client, admin_headers):
    # PUT -> visible in GET -> DELETE -> gone.
    res = client.put("/admin/rules", json=_rule(), headers=admin_headers)
    assert res.status_code == 200
    rule = res.json()["rule"]
    assert rule["rule_id"] and rule["seed"] is False

    listed = client.get("/admin/rules", headers=admin_headers).json()["rules"]
    assert any(r["rule_id"] == rule["rule_id"] for r in listed)

    res = client.delete("/admin/rules/{}".format(rule["rule_id"]), headers=admin_headers)
    assert res.status_code == 200
    listed = client.get("/admin/rules", headers=admin_headers).json()["rules"]
    assert not any(r["rule_id"] == rule["rule_id"] for r in listed)
    # Deleting again -> 404 (unknown rule_id).
    assert client.delete("/admin/rules/{}".format(rule["rule_id"]),
                         headers=admin_headers).status_code == 404


def test_scn02_auth(client, monkeypatch):
    # ADMIN_KEY unset -> admin disabled entirely (404), even with a key header.
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert client.get("/admin/rules").status_code == 404
    assert client.get("/admin/rules",
                      headers={"X-Admin-Key": "whatever"}).status_code == 404
    assert client.put("/admin/rules", json=_rule()).status_code == 404

    # ADMIN_KEY set: missing/wrong key -> 401; right key -> 200.
    monkeypatch.setenv("ADMIN_KEY", ADMIN_KEY)
    assert client.get("/admin/rules").status_code == 401
    assert client.get("/admin/rules",
                      headers={"X-Admin-Key": "wrong-key"}).status_code == 401
    assert client.get("/admin/rules",
                      headers={"X-Admin-Key": ADMIN_KEY}).status_code == 200


def test_scn03_put_same_key_silently_replaces(client, admin_headers):
    before = len(client.get("/admin/rules", headers=admin_headers).json()["rules"])
    r1 = client.put("/admin/rules", json=_rule(preset="order_failed"),
                    headers=admin_headers).json()["rule"]
    r2 = client.put("/admin/rules",
                    json=_rule(preset="order_failed", code=599, msg="custom"),
                    headers=admin_headers).json()["rule"]
    assert r1["rule_id"] == r2["rule_id"]  # same match key
    rules_now = client.get("/admin/rules", headers=admin_headers).json()["rules"]
    assert len(rules_now) == before + 1  # still one rule for that key
    stored = next(r for r in rules_now if r["rule_id"] == r2["rule_id"])
    assert stored["code"] == 599 and stored["msg"] == "custom"


def test_scn04_reset_restores_exactly_the_seeds(client, admin_headers):
    client.put("/admin/rules", json=_rule(), headers=admin_headers)
    res = client.post("/admin/rules/reset", headers=admin_headers)
    assert res.status_code == 200
    listed = res.json()["rules"]
    assert len(listed) == len(SEED_RULES)
    assert all(r["seed"] is True for r in listed)
    seeded_keys = {(r["endpoint"], r["airline"], r["origin"], r["destination"])
                   for r in listed}
    expected_keys = {(r["endpoint"], r["airline"], r["origin"], r["destination"])
                     for r in SEED_RULES}
    assert seeded_keys == expected_keys
    assert all(r["airline"] == "*" for r in listed)  # seeds are wildcard-airline


def test_scn05_validation(client, admin_headers):
    def put(body):
        return client.put("/admin/rules", json=body, headers=admin_headers)

    # Bad shapes -> 422 with error strings.
    assert put(_rule(origin="Jakarta")).status_code == 422
    assert put(_rule(destination="cg")).status_code == 422
    assert put(_rule(airline="garuda")).status_code == 422
    assert put(_rule(endpoint="nonsense")).status_code == 422
    assert put(_rule(preset="nonsense")).status_code == 422
    # Wildcard airline "*" accepted (airline field only).
    assert put(_rule(airline="*")).status_code == 200
    # Unknown-but-well-formed airline accepted (never matches, no crash).
    assert put(_rule(airline="ZZ")).status_code == 200
    # Non-int code override -> 422 (no silent coercion: 5.7 would truncate to 5,
    # and bool is an int subclass in Python).
    assert put(_rule(code="not-a-number")).status_code == 422
    assert put(_rule(code=5.7)).status_code == 422
    assert put(_rule(code=True)).status_code == 422
    # Numeric-string code coerces to int.
    res = put(_rule(code="600"))
    assert res.status_code == 200 and res.json()["rule"]["code"] == 600
    # Any override on tsy.* -> 422 (Decision 11).
    tsy = _rule(endpoint="tsy.order", preset="order_failed", code=1)
    assert put(tsy).status_code == 422
    tsy = _rule(endpoint="tsy.order", preset="order_failed", msg="boom")
    assert put(tsy).status_code == 422
    # Overrides on non-business_error presets -> 422.
    assert put(_rule(endpoint="search", preset="no_results", msg="x")).status_code == 422
    # flow only on orderDetail endpoints.
    assert put(_rule(endpoint="pay", preset="payment_declined",
                     flow="issuance")).status_code == 422
    assert put(_rule(endpoint="orderDetail", preset="order_not_found",
                     flow="bogus")).status_code == 422
    # Falsy non-string flows are invalid, not "both" (only ""/null mean both).
    assert put(_rule(endpoint="orderDetail", preset="order_not_found",
                     flow=0)).status_code == 422
    assert put(_rule(endpoint="orderDetail", preset="order_not_found",
                     flow=False)).status_code == 422
    assert put(_rule(endpoint="orderDetail", preset="order_not_found",
                     flow="issuance")).status_code == 200


def test_scn06_presets_catalog(client, admin_headers):
    body = client.get("/admin/presets", headers=admin_headers).json()
    ids = [e["id"] for e in body["endpoints"]]
    assert ids == list(ENDPOINTS)
    by_id = {e["id"]: e for e in body["endpoints"]}
    # overridable flag: everything except tsy.*.
    assert all(not by_id[i]["overridable"] for i in ids if i.startswith("tsy."))
    assert all(by_id[i]["overridable"] for i in ids if not i.startswith("tsy."))
    # flow_capable: exactly the three orderDetail endpoints.
    assert {i for i in ids if by_id[i]["flow_capable"]} == {
        "orderDetail", "tsy.orderDetail", "std.orderDetail"}
    assert body["flows"] == ["submitBooking", "issuance"]
    assert body["airlines"] == ["JT", "GA", "QZ", "AK", "SQ", "JL", "MM", "OD"]
    assert body["wildcard_airline"] == "*"
    # Every preset entry carries a label and a kind.
    for e in body["endpoints"]:
        assert e["presets"], "endpoint {} has no presets".format(e["id"])
        for preset in e["presets"].values():
            assert preset["label"] and preset["kind"] in (
                "empty_result", "business_error", "http_500", "status_override")


# ---------------------------------------------------------------------------
# Group B — exact-match semantics (near-miss suite)
# Canonical fixture per TEST_CASES.md: GA, KNO->CGK.
# ---------------------------------------------------------------------------

def _offer_key(airline="GA", ori="KNO", dest="CGK"):
    return encode_offer_key(airline, ori, dest, future_date())


def _order(client, airline="GA", ori="KNO", dest="CGK"):
    return client.post("/flight/order/v3",
                       json=order_body(_offer_key(airline, ori, dest))).json()


def _create_order(client, airline="GA", ori="KNO", dest="CGK"):
    rs = _order(client, airline, ori, dest)
    assert rs["code"] == 0
    return rs["data"]["orderId"]


def _pay(client, order_id):
    return client.post("/flight/pay/v3",
                       json={"orderId": order_id, "payType": "BPA"}).json()


def _detail(client, order_id):
    return client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()


def test_scn10_direction_matters(client, admin_headers):
    client.put("/admin/rules", json=_rule("order", "GA", "KNO", "CGK",
                                          preset="order_failed"), headers=admin_headers)
    assert _order(client, "GA", "KNO", "CGK")["code"] == 500  # matched
    assert _order(client, "GA", "CGK", "KNO")["code"] == 0    # reverse direction OK


def test_scn11_airline_isolation(client, admin_headers):
    client.put("/admin/rules", json=_rule("order", "GA", "KNO", "CGK",
                                          preset="order_failed"), headers=admin_headers)
    assert _order(client, "JT", "KNO", "CGK")["code"] == 0


def test_scn12_endpoint_isolation(client, admin_headers):
    # Order created BEFORE the rule; an `order`-endpoint rule must not leak
    # into pay for the same airline+route.
    order_id = _create_order(client)
    client.put("/admin/rules", json=_rule("order", "GA", "KNO", "CGK",
                                          preset="order_failed"), headers=admin_headers)
    assert _pay(client, order_id)["code"] == 0


def test_scn13_flow_targeting(client, admin_headers):
    # issuance-flow rule: pre-pay orderDetail succeeds, post-pay fails.
    client.put("/admin/rules",
               json=_rule("orderDetail", "GA", "KNO", "CGK",
                          preset="order_not_found", flow="issuance"),
               headers=admin_headers)
    order_id = _create_order(client)
    assert _detail(client, order_id)["code"] == 0        # UNPAID -> submitBooking
    assert _pay(client, order_id)["code"] == 0
    assert _detail(client, order_id)["code"] == 148      # ISSUED -> issuance

    # Inverse: submitBooking-flow rule hits pre-pay only.
    client.post("/admin/rules/reset", headers=admin_headers)
    client.put("/admin/rules",
               json=_rule("orderDetail", "GA", "KNO", "CGK",
                          preset="unpaid_missing_data", flow="submitBooking"),
               headers=admin_headers)
    order_id = _create_order(client)
    assert _detail(client, order_id)["code"] == 204      # pre-pay matched
    assert _pay(client, order_id)["code"] == 0
    assert _detail(client, order_id)["code"] == 0        # post-pay unaffected


def test_scn14_flow_null_hits_both(client, admin_headers):
    client.put("/admin/rules",
               json=_rule("orderDetail", "GA", "KNO", "CGK", preset="order_not_found"),
               headers=admin_headers)
    order_id = _create_order(client)
    assert _detail(client, order_id)["code"] == 148      # pre-pay
    assert _pay(client, order_id)["code"] == 0
    assert _detail(client, order_id)["code"] == 148      # post-pay


def test_scn15_wildcard_airline_and_exact_precedence(client, admin_headers):
    # Wildcard rule matches every airline on the route+endpoint...
    client.put("/admin/rules", json=_rule("pay", "*", "KNO", "CGK",
                                          preset="payment_declined"), headers=admin_headers)
    ga_order = _create_order(client, "GA")
    jt_order = _create_order(client, "JT")
    assert _pay(client, ga_order)["code"] == 501
    assert _pay(client, jt_order)["code"] == 501
    # ...but a coexisting exact-airline rule takes precedence over it.
    client.put("/admin/rules",
               json=_rule("pay", "GA", "KNO", "CGK", preset="payment_declined",
                          code=999, msg="GA-specific decline"),
               headers=admin_headers)
    ga_order2 = _create_order(client, "GA")
    jt_order2 = _create_order(client, "JT")
    ga_res = _pay(client, ga_order2)
    assert ga_res["code"] == 999 and ga_res["msg"] == "GA-specific decline"
    assert _pay(client, jt_order2)["code"] == 501        # wildcard still covers JT


def test_tsy_second_baggage_rule_failure_is_search_shaped(client, admin_headers):
    # A tsy.secondBaggage route_blocked rule must fail with the SEARCH envelope
    # (products: null), not the order-shaped body.
    from tests import bpi_helpers as tsy
    client.put("/admin/rules",
               json=_rule("tsy.secondBaggage", "GA", "CGK", "DPS",
                          preset="route_blocked"),
               headers=admin_headers)
    res = client.post("/secondBaggage", json=tsy.search_body(segments=[tsy.SEG_GA]))
    assert res.status_code == 500
    body = res.json()
    assert body["status"] == "1"
    assert "CGK-DPS" in body["msg"]
    assert body["auxiliaryOrderNo"] is None
    assert "products" in body and body["products"] is None
