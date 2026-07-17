import base64

from tests.bpi_helpers import SEG_GA, SEG_MM, SEG_VJ, search_body

TIER_WEIGHTS = [20, 30, 40, 50, 60, 70, 80, 90, 100]
TIER_PRICES = {20: 1.00, 30: 2.00, 40: 3.00, 50: 4.00, 60: 5.00,
               70: 6.00, 80: 7.00, 90: 8.00, 100: 9.00}


def test_search_happy_path(client):
    res = client.post("/secondBaggage", json=search_body())
    body = res.json()
    assert res.status_code == 200
    assert body["status"] == "0" and body["msg"] == "success"
    assert body["auxiliaryOrderNo"] is None
    assert len(body["products"]) == 1  # one product per RQ segment


def test_nine_tiers_with_prices(client):
    body = client.post("/secondBaggage", json=search_body()).json()
    items = body["products"][0]["productItems"]
    assert len(items) == 9
    weights = [i["baggage"]["baggageAllowance"] for i in items]
    assert weights == TIER_WEIGHTS  # ascending
    for i in items:
        kg = i["baggage"]["baggageAllowance"]
        assert i["basePrice"] == TIER_PRICES[kg]
        assert i["currency"] == "USD"
        assert i["productType"] == 1 and i["saleType"] == 2
        assert i["supportOverWeight"] is False
        assert i["baggage"]["baggagePieces"] == 1 and i["baggage"]["isAllWeight"] is True
        assert i["refundRule"]["refundRule"] == "*" and i["refundRule"]["canRefund"] is False


def test_product_item_id_is_standard_base64(client):
    body = client.post("/secondBaggage", json=search_body()).json()
    for i in body["products"][0]["productItems"]:
        pid = i["productItemId"]
        # 32-byte sha256 -> 44-char standard base64 ending with '='
        assert len(pid) == 44 and pid.endswith("=")
        base64.b64decode(pid)  # decodes without error
    ids = [i["productItemId"] for i in body["products"][0]["productItems"]]
    assert len(set(ids)) == 9  # unique per tier


def test_segment_echoed_and_enriched(client):
    body = client.post("/secondBaggage", json=search_body()).json()
    seg = body["products"][0]["segment"]
    assert seg["carrier"] == "VJ" and seg["flightNumber"] == "VJ84"
    assert seg["depAirport"] == "BNE" and seg["arrAirport"] == "SGN"
    assert seg["depTime"] == "202607312330" and seg["arrTime"] == "202608010500"
    assert seg["cabin"] == "B" and seg["cabinGrade"] == "Y"
    assert seg["codeShare"] is False and seg["isTransitVisa"] is False
    assert seg["tripType"] == "1"  # stringified
    assert seg["segmentIndex"] == 1


def test_per_segment_products(client):
    body = client.post("/secondBaggage", json=search_body(segments=[SEG_VJ, SEG_GA])).json()
    assert len(body["products"]) == 2
    assert body["products"][0]["segment"]["flightNumber"] == "VJ84"
    assert body["products"][1]["segment"]["flightNumber"] == "GA200"
    # IDs differ across segments for the same weight tier.
    id_vj = body["products"][0]["productItems"][0]["productItemId"]
    id_ga = body["products"][1]["productItems"][0]["productItemId"]
    assert id_vj != id_ga


def test_passenger_ignored(client):
    # Missing, empty, and empty-field passenger arrays all still return the catalog.
    for passenger in (None, [], [{"passengerType": "", "lastName": "", "firstName": ""}]):
        body = client.post("/secondBaggage", json=search_body(passenger=passenger)).json()
        assert body["status"] == "0"
        assert len(body["products"][0]["productItems"]) == 9


def test_mm_baggage_is_piece_based(client):
    # MM's second baggage is piece-based: baggage.isAllWeight is False for every tier
    # (vs True for weight-based carriers like VJ).
    mm = client.post("/secondBaggage", json=search_body(segments=[SEG_MM])).json()
    assert all(i["baggage"]["isAllWeight"] is False for i in mm["products"][0]["productItems"])
    vj = client.post("/secondBaggage", json=search_body(segments=[SEG_VJ])).json()
    assert all(i["baggage"]["isAllWeight"] is True for i in vj["products"][0]["productItems"])
