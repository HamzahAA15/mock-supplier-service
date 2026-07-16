import base64

from tests.conftest import future_date, search_body


def decode_key(offer_key):
    padded = offer_key + "=" * (-len(offer_key) % 4)
    return base64.urlsafe_b64decode(padded).decode()


def test_happy_path_all_offers(client):
    res = client.post("/flight/search/v3", json=search_body())
    body = res.json()
    assert res.status_code == 200
    assert body["code"] == 0 and body["msg"] == "success"
    data = body["data"]
    assert data["currency"] == "USD"
    # One offer per airline in AIRLINE_ORDER: JT, GA, QZ, AK, SQ, JL, MM.
    assert len(data["offers"]) == 7
    assert len(data["flights"]) == 7
    assert len(data["segments"]) == 7
    assert len(data["ancillaries"]) == 7
    assert data["penalties"] == []

    # offerKeys encode the requested route/date (CGK->DPS, future-relative).
    dep = future_date()
    keys = [o["offerKey"] for o in data["offers"]]
    assert decode_key(keys[0]) == "JT|CGK|DPS|{}|BASIC".format(dep)
    assert decode_key(keys[1]) == "GA|CGK|DPS|{}|BASIC".format(dep)
    assert decode_key(keys[6]) == "MM|CGK|DPS|{}|BASIC".format(dep)

    # Per-airline FBA (req #8), in order; piece 0 when FBA=0.
    # JT 0, GA 20, QZ 0, AK 0, SQ 20, JL 15, MM 0.
    fbas = [(a["ancillaryCode"], a["ancillaryPiece"]) for a in data["ancillaries"]]
    assert fbas == [(0, 0), (20, 1), (0, 0), (0, 0), (20, 1), (15, 1), (0, 0)]
    assert all(a["ancillaryType"] == "FREECHECKEDBAGGAGE" for a in data["ancillaries"])

    # AK is still the cheapest offer (fare 50), at index 3; MM (65) is not.
    assert [o["cheapestOption"] for o in data["offers"]] == [False, False, False, True, False, False, False]

    # Charges: 1 adult -> ADT FARE+TAX only.
    jt = data["offers"][0]["charges"]
    assert jt == [
        {"passengerType": "ADT", "chargeType": "FARE", "price": 60.0},
        {"passengerType": "ADT", "chargeType": "TAX", "price": 8.0},
    ]


def test_echo_route_and_date(client):
    dep = future_date(90)
    res = client.post("/flight/search/v3", json=search_body(ori="KNO", dest="CGK", dep_date=dep))
    data = res.json()["data"]
    for seg in data["segments"]:
        assert seg["depAirport"] == "KNO"
        assert seg["arrAirport"] == "CGK"
        assert seg["depTime"].startswith(dep + " ")
        assert seg["arrTime"].startswith(dep + " ")
        assert seg["stopovers"] == []
    for offer in data["offers"]:
        airline, ori, dest, dep_date, product = decode_key(offer["offerKey"]).split("|")
        assert (ori, dest, dep_date, product) == ("KNO", "CGK", dep, "BASIC")


def test_airline_filter(client):
    res = client.post("/flight/search/v3", json=search_body(airlineIds=["GA"]))
    data = res.json()["data"]
    assert len(data["offers"]) == 1
    assert data["segments"][0]["marketingCarrier"] == "GA"
    assert data["offers"][0]["cheapestOption"] is True  # cheapest among returned


def test_child_infant_charges(client):
    res = client.post("/flight/search/v3", json=search_body(adult=2, child=1, infant=1, airlineIds=["GA"]))
    charges = res.json()["data"]["offers"][0]["charges"]
    by_type = {(c["passengerType"], c["chargeType"]): c["price"] for c in charges}
    assert by_type[("ADT", "FARE")] == 95.0
    assert by_type[("CHD", "FARE")] == 71.25  # 75%
    assert by_type[("INF", "FARE")] == 9.5    # 10%
    assert by_type[("CHD", "TAX")] == 9.0
    assert len(charges) == 6


def test_backdate_rejected_205(client):
    res = client.post("/flight/search/v3", json=search_body(dep_date="2020-01-01"))
    body = res.json()
    assert res.status_code == 200
    assert body["code"] == 205
    assert body["data"] is None


def test_bad_date_format_204(client):
    res = client.post("/flight/search/v3", json=search_body(dep_date="10-07-2026"))
    assert res.json()["code"] == 204


def test_missing_route_206(client):
    body = search_body()
    body["routes"] = []
    assert client.post("/flight/search/v3", json=body).json()["code"] == 206
    del body["routes"]
    assert client.post("/flight/search/v3", json=body).json()["code"] == 206


def test_missing_airport_201(client):
    body = search_body()
    body["routes"][0]["destAirport"] = ""
    assert client.post("/flight/search/v3", json=body).json()["code"] == 201


def test_missing_dep_date_203(client):
    body = search_body()
    body["routes"][0]["depDate"] = ""
    assert client.post("/flight/search/v3", json=body).json()["code"] == 203


def test_no_adult_241(client):
    assert client.post("/flight/search/v3", json=search_body(adult=0)).json()["code"] == 241


def test_offer_key_stable(client):
    k1 = client.post("/flight/search/v3", json=search_body()).json()["data"]["offers"][0]["offerKey"]
    k2 = client.post("/flight/search/v3", json=search_body()).json()["data"]["offers"][0]["offerKey"]
    assert k1 == k2
