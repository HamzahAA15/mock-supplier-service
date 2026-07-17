from tests.bpi_helpers import (
    SEG_GA, SEG_VJ, order_body, pax_aux, product_item_for, search_body,
)


def _place_order(client, aux_no="ORD-1", weight=20, segments=None):
    rs = client.post("/secondBaggage", json=search_body(segments=segments)).json()
    seg = (segments or [SEG_VJ])[0]
    item = product_item_for(rs, 0, weight)
    client.post("/orderCrossSecondBaggage", json=order_body(aux_no, [pax_aux(seg, item)]))
    return aux_no


def test_order_detail_purchased(client):
    aux_no = _place_order(client, weight=20)
    res = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": aux_no}).json()
    assert res["status"] == "0" and res["msg"] == "success"
    data = res["data"]
    assert data["ancillaryOrderNo"] == aux_no
    assert data["orderStatus"] == "PURCHASED"   # always, immediately
    assert data["currency"] == "USD"
    assert data["isCross"] == 1
    assert data["totalPrice"] == 2.00


def test_segment_and_passenger_ancillary_linkage(client):
    aux_no = _place_order(client, weight=40)
    data = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": aux_no}).json()["data"]
    seg = data["segments"][0]
    assert seg["flightNumber"] == "VJ84"
    assert seg["depAirport"] == "BNE" and seg["arrAirport"] == "SGN"
    assert seg["arrTime"] is None  # null per sample
    assert isinstance(seg["id"], int) and seg["id"] > 0
    pa = data["passengerAncillaries"][0]
    assert pa["passengerName"] == "TESTER/ALPHA"   # Last/First
    assert pa["baggageWeight"] == "40"
    assert pa["pnrNo"] == "TEST01"
    assert pa["segmentId"] == seg["id"]   # links to the segment


def test_multi_passenger_totals(client):
    rs = client.post("/secondBaggage", json=search_body()).json()
    item20 = product_item_for(rs, 0, 20)
    item30 = product_item_for(rs, 0, 30)
    pax2 = {"passengerType": "ADT", "lastName": "SAMPLE", "firstName": "BETA", "pnrCode": "TEST01"}
    body = order_body("MULTI", [pax_aux(SEG_VJ, item20), pax_aux(SEG_VJ, item30, info=pax2)])
    client.post("/orderCrossSecondBaggage", json=body)
    data = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "MULTI"}).json()["data"]
    assert data["totalPrice"] == round(2.00 + 4.00, 2)
    assert len(data["passengerAncillaries"]) == 2
    assert len(data["segments"]) == 1  # same segment deduped
    # both ancillaries reference the single segment id
    assert {p["segmentId"] for p in data["passengerAncillaries"]} == {data["segments"][0]["id"]}


def test_unknown_order_not_found(client):
    res = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "does-not-exist"}).json()
    assert res["status"] == "1"
    assert res["msg"] == "order not found"
    assert res["data"] is None


def test_empty_aux_no_not_found(client):
    res = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": ""}).json()
    assert res["status"] == "1"
    assert res["data"] is None
