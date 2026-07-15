from app.services.standardized_bpi_catalog import decode_ancillary_key, encode_ancillary_key
from tests.standardized_bpi_helpers import (
    BASE_SEARCH_PATH,
    PAX_1,
    PAX_2,
    TIER_PRICES,
    TIER_WEIGHTS,
    blocked_segment,
    past_dt,
    search_body,
    segment,
)


def test_search_happy_path_with_passengers(client):
    res = client.post(BASE_SEARCH_PATH, json=search_body(passengers=[PAX_1, PAX_2]))
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0 and body["msg"] == "Success"
    data = body["data"]
    assert data["currency"] == "USD"
    assert len(data["routes"]) == 1
    route = data["routes"][0]
    assert route["tripType"] == 1
    # Post-issuance: per-passenger offers, no general offers.
    assert "generalOffers" not in route
    assert [po["passengerId"] for po in route["passengerOffers"]] == [1, 2]


def test_nine_tiers_with_prices(client):
    body = client.post(BASE_SEARCH_PATH, json=search_body(passengers=[PAX_1])).json()
    offers = body["data"]["routes"][0]["passengerOffers"][0]["ancillaryOffers"]
    assert len(offers) == 9
    assert [o["ancillaryCode"] for o in offers] == TIER_WEIGHTS  # ascending
    for o in offers:
        assert o["price"] == TIER_PRICES[o["ancillaryCode"]]
        assert o["ancillaryType"] == "CHECKEDBAGGAGE"
        assert o["ancillaryPiece"] == 1
        assert o["unitOfMeasurement"] == "WEIGHT"


def test_general_offers_when_no_passengers(client):
    # Pre-issuance live fetch: no passenger information -> generalOffers.
    body = client.post(BASE_SEARCH_PATH, json=search_body()).json()
    route = body["data"]["routes"][0]
    assert "passengerOffers" not in route
    offers = route["generalOffers"][0]["ancillaryOffers"]
    assert len(offers) == 9


def test_segments_echoed(client):
    seg = segment()
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": [seg]}], passengers=[PAX_1]),
    ).json()
    assert body["data"]["routes"][0]["segments"] == [seg]


def test_ancillary_key_roundtrip_and_uniqueness(client):
    seg_a = segment()
    seg_b = segment(marketing="GA", flight_no="GA200", dep="CGK", arr="DPS")
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": [seg_a]},
                                 {"tripType": 2, "segments": [seg_b]}],
                         passengers=[PAX_1]),
    ).json()
    routes = body["data"]["routes"]
    keys_a = [o["ancillaryKey"] for o in routes[0]["passengerOffers"][0]["ancillaryOffers"]]
    keys_b = [o["ancillaryKey"] for o in routes[1]["passengerOffers"][0]["ancillaryOffers"]]
    assert len(set(keys_a)) == 9  # unique per tier
    assert set(keys_a).isdisjoint(keys_b)  # differ across routes
    decoded = decode_ancillary_key(keys_a[0])
    assert decoded["weight"] == 20
    assert decoded["segments"][0]["departureAirport"] == seg_a["departureAirport"]
    assert decoded["segments"][0]["departureTime"] == seg_a["departureTime"]


def test_same_keys_across_passengers(client):
    # One key per (route, tier), identical across passengers (PRD sample).
    body = client.post(BASE_SEARCH_PATH, json=search_body(passengers=[PAX_1, PAX_2])).json()
    offers = body["data"]["routes"][0]["passengerOffers"]
    assert ([o["ancillaryKey"] for o in offers[0]["ancillaryOffers"]]
            == [o["ancillaryKey"] for o in offers[1]["ancillaryOffers"]])


def test_multi_segment_route_encodes_all_segments(client):
    segs = [segment(dep="CGK", arr="BKI"),
            segment(flight_no="AK341", dep="BKI", arr="DMK")]
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": segs}], passengers=[PAX_1]),
    ).json()
    key = body["data"]["routes"][0]["passengerOffers"][0]["ancillaryOffers"][0]["ancillaryKey"]
    decoded = decode_ancillary_key(key)
    assert [s["departureAirport"] for s in decoded["segments"]] == ["CGK", "BKI"]


def test_unsupported_ancillary_type_returns_555(client):
    body = client.post(BASE_SEARCH_PATH, json=search_body(ancillary_type="SEAT")).json()
    assert body["code"] == 555 and body["data"] is None


def test_empty_routes_returns_555(client):
    body = client.post(BASE_SEARCH_PATH, json=search_body(routes=[])).json()
    assert body["code"] == 555 and body["data"] is None


def test_blocked_route_returns_555(client):
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": [blocked_segment()]}]),
    ).json()
    assert body["code"] == 555 and body["data"] is None


def test_reverse_of_blocked_route_is_allowed(client):
    seg = segment(marketing="TR", flight_no="TR457", dep="KUL", arr="SIN")
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": [seg]}]),
    ).json()
    assert body["code"] == 0


def test_past_departure_returns_5001(client):
    seg = segment(dep_time=past_dt())
    body = client.post(
        BASE_SEARCH_PATH,
        json=search_body(routes=[{"tripType": 1, "segments": [seg]}]),
    ).json()
    assert body["code"] == 5001 and body["data"] is None


def test_decode_rejects_garbage_keys():
    assert decode_ancillary_key(None) is None
    assert decode_ancillary_key("") is None
    assert decode_ancillary_key("not-base64!!") is None
    # Valid base64 but wrong structure/prefix.
    import base64
    assert decode_ancillary_key(base64.urlsafe_b64encode(b'["X",1,20,[]]').decode()) is None
    # Unknown weight tier.
    bad = encode_ancillary_key(1, [segment()], 20).replace("=", "")
    assert decode_ancillary_key(encode_ancillary_key(1, [segment()], 20)) is not None
    import json
    raw = json.loads(base64.urlsafe_b64decode(encode_ancillary_key(1, [segment()], 20)))
    raw[2] = 25  # not a tier
    forged = base64.urlsafe_b64encode(json.dumps(raw).encode()).decode()
    assert decode_ancillary_key(forged) is None
