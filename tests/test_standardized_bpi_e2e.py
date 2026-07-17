"""End-to-end Standardized BPI flow:
search -> order (keys from search RS) -> orderDetail (GET, polled).
Mirrors test_bpi_e2e.py for the tsy contract."""
from tests.standardized_bpi_helpers import (
    BASE_SEARCH_PATH,
    ORDER_PATH,
    PAX_1,
    PAX_2,
    offer_for,
    order_body,
    search_body,
    segment,
)


def test_full_flow_roundtrip_multi_pax_multi_route(client):
    seg_out = segment(dep="CGK", arr="KUL")
    seg_in = segment(marketing="ID", flight_no="ID5261", dep="KUL", arr="CGK")
    passengers = [PAX_1, PAX_2]

    # 1. Search (post-issuance: with passengers).
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body(
        routes=[{"tripType": 1, "segments": [seg_out]},
                {"tripType": 2, "segments": [seg_in]}],
        passengers=passengers)).json()
    assert search_rs["code"] == 0
    assert len(search_rs["data"]["routes"]) == 2

    # 2. Order: pax 1 buys 20kg outbound, pax 2 buys 30kg inbound.
    key_out = offer_for(search_rs, 0, 20)["ancillaryKey"]
    key_in = offer_for(search_rs, 1, 30, 1)["ancillaryKey"]
    order_rs = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-E2E", passengers=passengers,
        selected=[{"passengerId": 1, "ancillaryKey": key_out},
                  {"passengerId": 2, "ancillaryKey": key_in}])).json()
    assert order_rs["code"] == 0
    assert order_rs["data"]["orderStatus"] == "ISSUING"
    assert order_rs["data"]["total"] == round(1.00 + 2.00, 2)

    # Segments in the order RS reconstruct the search RQ segments.
    segs = order_rs["data"]["selectedAncillary"][0]["segments"]
    assert segs[0]["departureAirport"] == "CGK" and segs[0]["arrivalAirport"] == "KUL"
    segs = order_rs["data"]["selectedAncillary"][1]["segments"]
    assert segs[0]["departureAirport"] == "KUL" and segs[0]["arrivalAirport"] == "CGK"

    # 3. Order detail: poll twice, ISSUED both times, totals consistent.
    for _ in range(2):
        detail = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-E2E")).json()
        assert detail["code"] == 0
        assert detail["data"]["orderStatus"] == "ISSUED"
        assert detail["data"]["total"] == order_rs["data"]["total"]
        assert len(detail["data"]["selectedAncillary"]) == 2
        assert all(i["unitOfMeasurement"] == "WEIGHT"
                   for i in detail["data"]["selectedAncillary"])


def test_pre_issuance_general_offers_can_still_be_ordered(client):
    # Pre-issuance live fetch returns generalOffers; the same keys must be
    # orderable later once passenger info exists (post-to-pre flow).
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body()).json()
    key = offer_for(search_rs, 0, 20)["ancillaryKey"]
    order_rs = client.post(ORDER_PATH, json=order_body(
        "TVLK-BPI-P2P", passengers=[PAX_1],
        selected=[{"passengerId": 1, "ancillaryKey": key}])).json()
    assert order_rs["code"] == 0
    detail = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-P2P")).json()
    assert detail["data"]["orderStatus"] == "ISSUED"


def test_tsy_and_standardized_versions_coexist(client):
    # Both BPI contract versions are served side by side.
    from tests.bpi_helpers import search_body as tsy_search_body
    tsy = client.post("/secondBaggage", json=tsy_search_body()).json()
    std = client.post(BASE_SEARCH_PATH, json=search_body()).json()
    assert tsy["status"] == "0"  # tsy string envelope
    assert std["code"] == 0      # standardized int envelope


def test_od_segment_is_weight_based(client):
    # OD is a normal weight-based carrier -> unitOfMeasurement WEIGHT in offers + orderDetail.
    seg_od = segment(marketing="OD", flight_no="OD800", dep="CGK", arr="DPS")
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body(
        routes=[{"tripType": 1, "segments": [seg_od]}], passengers=[PAX_1])).json()
    assert search_rs["code"] == 0
    offer = offer_for(search_rs, 0, 20)
    assert offer["unitOfMeasurement"] == "WEIGHT"
    order_rs = client.post(ORDER_PATH, json=order_body(
        "OD-STD-1", passengers=[PAX_1],
        selected=[{"passengerId": 1, "ancillaryKey": offer["ancillaryKey"]}])).json()
    assert order_rs["code"] == 0
    seg0 = order_rs["data"]["selectedAncillary"][0]["segments"][0]
    assert seg0["marketingCarrier"] == "OD" and seg0["flightNumber"] == "OD800"
    detail = client.get("{}/{}".format(ORDER_PATH, "OD-STD-1")).json()
    assert detail["data"]["selectedAncillary"][0]["unitOfMeasurement"] == "WEIGHT"


def test_mm_segment_flows_through(client):
    # Standardized BPI is carrier-agnostic: an MM segment searches, orders, and
    # its carrier is reconstructed in the order RS.
    seg_mm = segment(marketing="MM", flight_no="MM700", dep="CGK", arr="DPS")
    search_rs = client.post(BASE_SEARCH_PATH, json=search_body(
        routes=[{"tripType": 1, "segments": [seg_mm]}], passengers=[PAX_1])).json()
    assert search_rs["code"] == 0
    offer = offer_for(search_rs, 0, 20)
    # MM baggage is piece-based -> unitOfMeasurement PIECE (WEIGHT for other carriers).
    assert offer["unitOfMeasurement"] == "PIECE"
    order_rs = client.post(ORDER_PATH, json=order_body(
        "MM-STD-1", passengers=[PAX_1],
        selected=[{"passengerId": 1, "ancillaryKey": offer["ancillaryKey"]}])).json()
    assert order_rs["code"] == 0 and order_rs["data"]["orderStatus"] == "ISSUING"
    seg0 = order_rs["data"]["selectedAncillary"][0]["segments"][0]
    assert seg0["marketingCarrier"] == "MM" and seg0["flightNumber"] == "MM700"
    detail = client.get("{}/{}".format(ORDER_PATH, "MM-STD-1")).json()
    assert detail["data"]["orderStatus"] == "ISSUED"
    assert detail["data"]["selectedAncillary"][0]["unitOfMeasurement"] == "PIECE"
