"""Full BPI chain: search -> order -> orderDetail, asserting productItemId round-trip."""
from tests.bpi_helpers import SEG_VJ, order_body, pax_aux, search_body


def test_bpi_chain(client):
    # 1. search
    rs = client.post("/secondBaggage", json=search_body()).json()
    assert rs["status"] == "0"
    items = rs["products"][0]["productItems"]

    # pick the 70kg tier
    tier = next(i for i in items if i["baggage"]["baggageAllowance"] == 70)
    assert tier["basePrice"] == 358.38
    pid = tier["productItemId"]

    # 2. order using the exact productItem from search (round-trip)
    aux_no = "1373091015-1-0"
    order = client.post("/orderCrossSecondBaggage",
                        json=order_body(aux_no, [pax_aux(SEG_VJ, tier)])).json()
    assert order["status"] == "0"
    assert order["auxiliaryOrderNo"] == aux_no

    # 3. orderDetail -> PURCHASED, totals + linkage
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": aux_no}).json()
    assert det["status"] == "0"
    data = det["data"]
    assert data["orderStatus"] == "PURCHASED"
    assert data["totalPrice"] == 358.38
    assert data["ancillaryOrderNo"] == aux_no
    pa = data["passengerAncillaries"][0]
    assert pa["baggageWeight"] == "70"
    assert pa["segmentId"] == data["segments"][0]["id"]

    # productItemId the client sent equals what search issued (stateless round-trip)
    assert pid == tier["productItemId"]
