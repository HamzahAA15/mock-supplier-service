from app.services.offer_key import encode_offer_key

GA_KEY = encode_offer_key("GA", "CGK", "DPS", "2026-07-10")
JT_KEY = encode_offer_key("JT", "CGK", "DPS", "2026-07-10")
QZ_KEY = encode_offer_key("QZ", "CGK", "DPS", "2026-07-10")


def get_offers(client, key):
    body = client.post("/flight/ancillary/search/v3", json={"offerKey": key}).json()
    assert body["code"] == 0
    assert body["data"]["currency"] == "USD"
    return body["data"]["ancillaryOffers"]


def test_ga_options_above_fba_20(client):
    offers = get_offers(client, GA_KEY)
    assert [o["ancillaryCode"] for o in offers] == [25, 30, 35]
    assert [o["price"] for o in offers] == [37.5, 45.0, 52.5]
    assert offers[0]["ancillaryKey"] == "1_0_0$GA200$PA25"
    assert all(o["addAncillaryType"] == "CHECKEDBAGGAGE" for o in offers)
    assert all(o["flightNumber"] == "GA200" for o in offers)
    assert offers[0]["oriAirport"] == "CGK" and offers[0]["destAirport"] == "DPS"


def test_jt_qz_options_above_fba_0(client):
    for key, flight in ((JT_KEY, "JT100"), (QZ_KEY, "QZ300")):
        offers = get_offers(client, key)
        assert [o["ancillaryCode"] for o in offers] == [5, 10, 15]
        assert [o["price"] for o in offers] == [7.5, 15.0, 22.5]
        assert offers[0]["ancillaryKey"] == "1_0_0${}$PA5".format(flight)


def test_exactly_three_options(client):
    assert len(get_offers(client, GA_KEY)) == 3


def test_keys_reversible(client):
    from app.services.offer_key import decode_ancillary_key
    for offer in get_offers(client, GA_KEY):
        decoded = decode_ancillary_key(offer["ancillaryKey"])
        assert decoded == {"flight_number": "GA200", "kg": offer["ancillaryCode"]}


def test_empty_and_bad_offer_key(client):
    assert client.post("/flight/ancillary/search/v3", json={"offerKey": ""}).json()["code"] == 101
    assert client.post("/flight/ancillary/search/v3", json={"offerKey": "zzz"}).json()["code"] == 204
