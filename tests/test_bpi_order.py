from tests.bpi_helpers import (
    SEG_KUL_SIN, SEG_MM, SEG_SIN_CGK, SEG_SIN_KUL, SEG_VJ,
    order_body, pax_aux, product_item_for, search_body,
)


def _search(client, segments=None):
    return client.post("/secondBaggage", json=search_body(segments=segments)).json()


def test_order_mm_segment(client):
    # TSY BPI is carrier-agnostic: an MM segment flows through search -> order -> orderDetail.
    rs = _search(client, segments=[SEG_MM])
    item = product_item_for(rs, 0, 30)
    res = client.post("/orderCrossSecondBaggage",
                      json=order_body("MM-BPI-1", [pax_aux(SEG_MM, item)])).json()
    assert res["status"] == "0" and res["auxiliaryOrderNo"] == "MM-BPI-1"
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "MM-BPI-1"}).json()
    assert det["data"]["orderStatus"] == "PURCHASED"
    assert det["data"]["segments"][0]["flightNumber"] == "MM700"


def test_order_happy_path(client):
    rs = _search(client)
    item = product_item_for(rs, 0, 20)
    body = order_body("1373091015-1-0", [pax_aux(SEG_VJ, item)])
    res = client.post("/orderCrossSecondBaggage", json=body).json()
    assert res["status"] == "0"
    assert res["msg"] == "success"
    assert res["auxiliaryOrderNo"] == "1373091015-1-0"  # echoed, never generated


def test_order_via_order_no_only(client):
    rs = _search(client)
    item = product_item_for(rs, 0, 30)
    body = {"orderNo": "ONLY-ORDER-NO", "isCross": 1,
            "passengerAuxes": [pax_aux(SEG_VJ, item)]}
    res = client.post("/orderCrossSecondBaggage", json=body).json()
    assert res["status"] == "0"
    assert res["auxiliaryOrderNo"] == "ONLY-ORDER-NO"


def test_invalid_product_item_id_fails(client):
    rs = _search(client)
    item = product_item_for(rs, 0, 20)
    item = dict(item, productItemId="TAMPERED/notarealid=")
    res = client.post("/orderCrossSecondBaggage", json=order_body("AUX-1", [pax_aux(SEG_VJ, item)])).json()
    assert res["status"] == "1"
    assert res["auxiliaryOrderNo"] is None


def test_mismatched_weight_fails(client):
    # productItemId for 20kg but baggageAllowance claims 30kg -> re-derivation mismatch.
    rs = _search(client)
    item20 = product_item_for(rs, 0, 20)
    tampered = dict(item20, baggage={"baggagePieces": 1, "baggageAllowance": 30, "isAllWeight": True})
    res = client.post("/orderCrossSecondBaggage", json=order_body("AUX-2", [pax_aux(SEG_VJ, tampered)])).json()
    assert res["status"] == "1"
    assert res["auxiliaryOrderNo"] is None


def test_empty_aux_no_fails(client):
    rs = _search(client)
    item = product_item_for(rs, 0, 20)
    body = {"passengerAuxes": [pax_aux(SEG_VJ, item)]}
    res = client.post("/orderCrossSecondBaggage", json=body).json()
    assert res["status"] == "1"
    assert res["auxiliaryOrderNo"] is None


def test_idempotent_reorder(client):
    rs = _search(client)
    item20 = product_item_for(rs, 0, 20)
    item50 = product_item_for(rs, 0, 50)
    r1 = client.post("/orderCrossSecondBaggage", json=order_body("DUP", [pax_aux(SEG_VJ, item20)])).json()
    r2 = client.post("/orderCrossSecondBaggage", json=order_body("DUP", [pax_aux(SEG_VJ, item50)])).json()
    assert r1["status"] == "0" and r2["status"] == "0"
    # Latest wins: orderDetail reflects the 50kg re-order.
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "DUP"}).json()
    assert det["data"]["totalPrice"] == 4.00
    assert det["data"]["passengerAncillaries"][0]["baggageWeight"] == "50"


def test_blocked_route_sin_kul_fails_http_500(client):
    rs = _search(client, segments=[SEG_SIN_KUL])
    item = product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage",
                      json=order_body("BLOCK-KUL", [pax_aux(SEG_SIN_KUL, item)]))
    assert res.status_code == 500
    body = res.json()
    assert body["status"] == "1"
    assert "SIN-KUL" in body["msg"]
    # Order must not have been created.
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "BLOCK-KUL"}).json()
    assert det["status"] == "1" and det["data"] is None


def test_blocked_route_sin_cgk_fails_http_500(client):
    rs = _search(client, segments=[SEG_SIN_CGK])
    item = product_item_for(rs, 0, 30)
    res = client.post("/orderCrossSecondBaggage",
                      json=order_body("BLOCK-CGK", [pax_aux(SEG_SIN_CGK, item)]))
    assert res.status_code == 500
    assert "SIN-CGK" in res.json()["msg"]


def test_reverse_route_kul_sin_allowed(client):
    # Only SIN->KUL / SIN->CGK are blocked; the reverse direction is fine.
    rs = _search(client, segments=[SEG_KUL_SIN])
    item = product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage",
                      json=order_body("ALLOW-REV", [pax_aux(SEG_KUL_SIN, item)]))
    assert res.status_code == 200
    assert res.json()["status"] == "0"
