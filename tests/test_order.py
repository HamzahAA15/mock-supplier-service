from app.services.offer_key import encode_offer_key
from tests.conftest import order_body

GA_KEY = encode_offer_key("GA", "CGK", "DPS", "2026-07-10")

SANTOSO_FAMILY = [
    {"firstName": "BUDI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "M",
     "birthDay": "1990-01-15", "nationality": "ID"},
    {"firstName": "SITI", "lastName": "SANTOSO", "passengerType": "ADT", "sex": "F",
     "birthDay": "1992-03-20", "nationality": "ID"},
    {"firstName": "AGUS", "lastName": "SANTOSO", "passengerType": "CHD", "sex": "M",
     "birthDay": "2018-07-01", "nationality": "ID"},
]


def test_order_happy_path_with_baggage(client):
    body = order_body(GA_KEY, ancillary_key_lists=[
        {"passengerIndex": 0, "ancillaryKeys": ["1_0_0$GA200$PA25"]}
    ])
    res = client.post("/flight/order/v3", json=body).json()
    assert res["code"] == 0
    data = res["data"]
    assert data["orderId"].isdigit() and len(data["orderId"]) == 10  # req #6
    assert data["total"] == 15.25  # 7 + 2 + 6.25
    assert data["expireInMinutes"] == 30
    assert data["product"] == ["BASIC"]
    added = data["addedAncillary"]
    assert len(added) == 1
    assert added[0]["passengerIndex"] == 0
    assert added[0]["passengerName"] == "MURING BALA/CANDY FREDRICK"
    assert added[0]["ancillaryOffers"][0]["ancillaryCode"] == 25
    assert added[0]["ancillaryOffers"][0]["price"] == 6.25
    # Offer reconstructed from offerKey — route/date echoed.
    assert data["offers"][0]["offerKey"] == GA_KEY
    assert data["segments"][0]["depTime"] == "2026-07-10 12:00:00"


def test_multi_passenger_echo_verbatim(client):
    body = order_body(GA_KEY, passengers=SANTOSO_FAMILY)
    res = client.post("/flight/order/v3", json=body).json()
    assert res["code"] == 0
    # 2 ADT * (7+2) + 1 CHD * (5.25+1.5) = 18 + 6.75
    assert res["data"]["total"] == 24.75
    # Echo asserted end-to-end via orderDetail.
    detail = client.post("/flight/orderDetail/v3", json={"orderId": res["data"]["orderId"]}).json()
    assert detail["data"]["passengerList"] == SANTOSO_FAMILY  # N in => N out, verbatim, same order
    names = [p["passenger"] for p in detail["data"]["pnrs"][0]["passengers"]]
    assert names == ["SANTOSO/BUDI", "SANTOSO/SITI", "SANTOSO/AGUS"]


def test_contacts_echoed(client):
    contacts = [{"contactType": "AG", "firstName": "A", "lastName": "B",
                 "email": "a@b.co", "phone": "+62-1", "extraField": "kept"}]
    res = client.post("/flight/order/v3", json=order_body(GA_KEY, contacts=contacts)).json()
    detail = client.post("/flight/orderDetail/v3", json={"orderId": res["data"]["orderId"]}).json()
    assert detail["data"]["contactList"] == contacts


def test_email_empty_529(client):
    contacts = [{"contactType": "AG", "email": "", "phone": "+62-1"}]
    assert client.post("/flight/order/v3", json=order_body(GA_KEY, contacts=contacts)).json()["code"] == 529


def test_email_bad_format_530(client):
    contacts = [{"contactType": "AG", "email": "not-an-email", "phone": "+62-1"}]
    assert client.post("/flight/order/v3", json=order_body(GA_KEY, contacts=contacts)).json()["code"] == 530


def test_phone_empty_531(client):
    contacts = [{"contactType": "AG", "email": "a@b.co", "phone": ""}]
    assert client.post("/flight/order/v3", json=order_body(GA_KEY, contacts=contacts)).json()["code"] == 531


def test_unknown_ancillary_key_553(client):
    body = order_body(GA_KEY, ancillary_key_lists=[
        {"passengerIndex": 0, "ancillaryKeys": ["1_0_0$GA200$PA99"]}  # kg not offered
    ])
    assert client.post("/flight/order/v3", json=body).json()["code"] == 553


def test_mismatched_flight_ancillary_key_553(client):
    body = order_body(GA_KEY, ancillary_key_lists=[
        {"passengerIndex": 0, "ancillaryKeys": ["1_0_0$JT100$PA5"]}  # JT key on GA offer
    ])
    assert client.post("/flight/order/v3", json=body).json()["code"] == 553


def test_empty_offer_key_101(client):
    assert client.post("/flight/order/v3", json=order_body("")).json()["code"] == 101


def test_order_ids_are_random(client):
    ids = {client.post("/flight/order/v3", json=order_body(GA_KEY)).json()["data"]["orderId"]
           for _ in range(5)}
    assert len(ids) == 5
