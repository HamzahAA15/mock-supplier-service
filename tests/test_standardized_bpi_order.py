from app.services.standardized_bpi_catalog import encode_ancillary_key
from tests.standardized_bpi_helpers import (
    BASE_SEARCH_PATH,
    ORDER_PATH,
    PAX_1,
    PAX_2,
    blocked_segment,
    offer_for,
    order_body,
    search_body,
    search_then_order,
    segment,
)


def test_order_happy_path(client):
    _, order_rs = search_then_order(client, order_no="TVLK-BPI-100", weight_kg=20)
    assert order_rs["code"] == 0 and order_rs["msg"] == "Success"
    data = order_rs["data"]
    assert data["ancillaryOrderNo"] == "TVLK-BPI-100"
    assert data["orderStatus"] == "ISSUING"
    assert data["total"] == 1.00 and data["currency"] == "USD"
    assert data["isCross"] is True
    assert data["createdTime"] == data["updatedTime"]
    assert data["passengers"][0]["passengerId"] == 1
    item = data["selectedAncillary"][0]
    assert item["passengerId"] == 1
    assert item["ancillaryType"] == "CHECKEDBAGGAGE"
    assert item["ancillaryCode"] == 20 and item["ancillaryPiece"] == 1
    assert item["price"] == 1.00


def test_order_reconstructs_segments_from_key(client):
    seg = segment()
    search_rs, order_rs = search_then_order(
        client, routes=[{"tripType": 1, "segments": [seg]}])
    rs_seg = order_rs["data"]["selectedAncillary"][0]["segments"][0]
    for field in ("marketingCarrier", "flightNumber", "operatingCarrier",
                  "operatingFlightNumber", "departureAirport", "arrivalAirport",
                  "departureTime", "arrivalTime"):
        assert rs_seg[field] == seg[field]


def test_order_multi_pax_totals(client):
    passengers = [PAX_1, PAX_2]
    search_rs = client.post(BASE_SEARCH_PATH,
                            json=search_body(passengers=passengers)).json()
    selected = [
        {"passengerId": 1, "ancillaryKey": offer_for(search_rs, 0, 20)["ancillaryKey"]},
        {"passengerId": 2, "ancillaryKey": offer_for(search_rs, 0, 30, 1)["ancillaryKey"]},
    ]
    body = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-200", passengers=passengers, selected=selected)).json()
    assert body["code"] == 0
    assert body["data"]["total"] == round(1.00 + 2.00, 2)
    assert len(body["data"]["selectedAncillary"]) == 2


def test_order_missing_order_no_returns_400(client):
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body(passengers=[PAX_1])).json()
    selected = [{"passengerId": 1, "ancillaryKey": offer_for(search_rs, 0, 20)["ancillaryKey"]}]
    body_dict = order_body("X", selected=selected)
    del body_dict["ancillaryOrderNo"]
    body = client.post(ORDER_PATH, json=body_dict).json()
    assert body["code"] == 400 and body["data"] is None


def test_order_invalid_key_returns_400(client):
    body = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-300", selected=[{"passengerId": 1, "ancillaryKey": "FORGED"}])).json()
    assert body["code"] == 400
    assert body["msg"] == "invalid ancillaryKey"
    assert body["data"] is None


def test_order_unknown_passenger_id_returns_400(client):
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body(passengers=[PAX_1])).json()
    key = offer_for(search_rs, 0, 20)["ancillaryKey"]
    body = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-400", selected=[{"passengerId": 99, "ancillaryKey": key}])).json()
    assert body["code"] == 400 and body["data"] is None


def test_order_empty_selection_returns_400(client):
    body = client.post(ORDER_PATH, json=order_body("TVLK-BPI-500", selected=[])).json()
    assert body["code"] == 400 and body["data"] is None


def test_order_blocked_route_key_returns_555(client):
    # A key for a blocked route can't come from search (search already 555s),
    # but the order endpoint still guards against it independently.
    key = encode_ancillary_key(1, [blocked_segment()], 20)
    body = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-600", selected=[{"passengerId": 1, "ancillaryKey": key}])).json()
    assert body["code"] == 555 and body["data"] is None


def test_order_is_idempotent_upsert(client):
    _, first = search_then_order(client, order_no="TVLK-BPI-700", weight_kg=20)
    _, second = search_then_order(client, order_no="TVLK-BPI-700", weight_kg=30)
    assert first["code"] == 0 and second["code"] == 0
    # Latest wins.
    detail = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-700")).json()
    assert detail["data"]["selectedAncillary"][0]["ancillaryCode"] == 30


def test_order_failure_does_not_create_order(client):
    client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-800", selected=[{"passengerId": 1, "ancillaryKey": "FORGED"}]))
    detail = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-800")).json()
    assert detail["code"] == 400 and detail["data"] is None
