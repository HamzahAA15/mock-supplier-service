from app.services.offer_key import encode_offer_key
from tests.conftest import order_body

GA_KEY = encode_offer_key("GA", "CGK", "DPS", "2026-07-10")


def test_unpaid_order_detail(client):
    order_id = client.post("/flight/order/v3", json=order_body(GA_KEY)).json()["data"]["orderId"]
    res = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert res["code"] == 0
    info = res["data"]["orderInfo"]
    assert info["orderId"] == order_id
    assert info["status"] == "UNPAID"
    assert info["payTime"] == ""
    assert info["amount"] == "9.00"
    pnr = res["data"]["pnrs"][0]
    assert len(pnr["pnr"]) == 6 and pnr["pnr"].isalnum()  # PNR minted at order time
    assert pnr["providerPnr"] == ""
    assert pnr["email"] == "agent@example.com"
    assert pnr["passengers"][0]["ticketNumber"] == ""  # not issued yet
    # Nested pnr segments are light; top-level segments are full objects.
    assert pnr["segments"] == [
        {"depAirport": "CGK", "arrAirport": "DPS", "flightNumber": "GA200"}
    ]
    top_seg = res["data"]["segments"][0]
    assert top_seg["marketingCarrier"] == "GA" and top_seg["flightNumber"] == "GA200"
    assert top_seg["depAirport"] == "CGK" and top_seg["arrAirport"] == "DPS"
    assert top_seg["depTime"] == "2026-07-10 12:00:00" and top_seg["aircraftCode"] == "B738"
    assert top_seg["stopovers"] == []
    # flightRefs present at top level with fareType/brandedFare.
    assert res["data"]["flightRefs"] == [{"flightIndex": 0, "fareType": "PUBLISH", "brandedFare": ""}]


def test_offer_key_identity_search_to_order_detail(client):
    # req #5: the same offerKey obtained at search survives to orderDetail's stored order.
    from tests.conftest import search_body
    search_key = client.post("/flight/search/v3", json=search_body()).json()["data"]["offers"][1]["offerKey"]
    order_id = client.post("/flight/order/v3", json=order_body(search_key)).json()["data"]["orderId"]
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert detail["code"] == 0
    # Route/date rebuilt from that exact key.
    assert detail["data"]["segments"][0]["flightNumber"] == "GA200"


def test_ancillary_list_populated(client):
    body = order_body(GA_KEY, ancillary_key_lists=[
        {"passengerIndex": 0, "ancillaryKeys": ["1_0_0$GA200$PA30"]}
    ])
    order_id = client.post("/flight/order/v3", json=body).json()["data"]["orderId"]
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    items = detail["data"]["ancillaryList"]
    assert len(items) == 1
    assert items[0]["ancillaryType"] == "CHECKEDBAGGAGE"
    assert items[0]["ancillaryCode"] == 30
    assert items[0]["passengerName"] == "MURING BALA/CANDY FREDRICK"
    assert detail["data"]["ancillaries"][0]["ancillaryType"] == "FREECHECKEDBAGGAGE"
    assert detail["data"]["ancillaries"][0]["ancillaryCode"] == 20


def test_unknown_order_148(client):
    assert client.post("/flight/orderDetail/v3", json={"orderId": "1111111111"}).json()["code"] == 148


def test_empty_order_id_745(client):
    assert client.post("/flight/orderDetail/v3", json={"orderId": ""}).json()["code"] == 745
