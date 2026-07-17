"""Full happy-path chain: token -> search -> verify -> ancillary -> order -> pay -> orderDetail."""
from tests.conftest import search_body


def test_e2e_booking_chain(client):
    # 1. token
    token = client.post("/uaa/oauth/token", json={"grantType": "clientCredentials"}).json()
    assert token["tokenType"] == "Bearer"

    # 2. search KNO->CGK (echo route) and pick the GA offer
    search = client.post(
        "/flight/search/v3", json=search_body(ori="KNO", dest="CGK", dep_date="2026-09-20", adult=2)
    ).json()
    assert search["code"] == 0
    offer = search["data"]["offers"][1]
    offer_key = offer["offerKey"]
    assert search["data"]["segments"][1]["depAirport"] == "KNO"

    # 3. preOrderVerify returns the same offerKey (req #5, no price change)
    verify = client.post("/flight/preOrderVerify/v3", json={"offerKey": offer_key}).json()
    assert verify["code"] == 0
    assert verify["data"]["offers"][0]["offerKey"] == offer_key

    # 4. ancillarySearch: GA -> 25/30/35 kg
    anc = client.post("/flight/ancillary/search/v3", json={"offerKey": offer_key}).json()
    assert [a["ancillaryCode"] for a in anc["data"]["ancillaryOffers"]] == [25, 30, 35]
    baggage = anc["data"]["ancillaryOffers"][0]

    # 5. order with 2 passengers + 1 baggage
    passengers = [
        {"firstName": "BUDI", "lastName": "SANTOSO", "passengerType": "ADT",
         "sex": "M", "birthDay": "1990-01-15", "nationality": "ID"},
        {"firstName": "SITI", "lastName": "SANTOSO", "passengerType": "ADT",
         "sex": "F", "birthDay": "1992-03-20", "nationality": "ID"},
    ]
    contacts = [{"contactType": "AG", "firstName": "BUDI", "lastName": "SANTOSO",
                 "email": "budi@example.com", "phone": "+62-811111111"}]
    order = client.post("/flight/order/v3", json={
        "offerKey": offer_key,
        "ancillaryKeyLists": [{"passengerIndex": 1, "ancillaryKeys": [baggage["ancillaryKey"]]}],
        "passengers": passengers,
        "contacts": contacts,
    }).json()
    assert order["code"] == 0
    order_id = order["data"]["orderId"]
    expected_total = round(2 * (15.0 + 3.0) + 12.5, 2)
    assert order["data"]["total"] == expected_total
    assert order["data"]["offers"][0]["offerKey"] == offer_key  # identity holds at order

    # 6. detail before pay: UNPAID, no tickets
    before = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert before["data"]["orderInfo"]["status"] == "UNPAID"
    assert all(p["ticketNumber"] == "" for p in before["data"]["pnrs"][0]["passengers"])

    # 7. pay
    pay = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "BPA"}).json()
    assert pay["code"] == 0
    assert pay["data"]["amount"] == "{:.2f}".format(expected_total)

    # 8. detail after pay: ISSUED, 13-digit ticket per pax, passengers echoed verbatim
    after = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert after["data"]["orderInfo"]["status"] == "ISSUED"
    tickets = [p["ticketNumber"] for p in after["data"]["pnrs"][0]["passengers"]]
    assert len(tickets) == 2 and all(len(t) == 13 and t.isdigit() for t in tickets)
    assert after["data"]["passengerList"] == passengers
    assert after["data"]["contactList"] == contacts
    # Top-level segments are full objects; nested pnr segments stay light.
    top_seg = after["data"]["segments"][0]
    assert top_seg["marketingCarrier"] == "GA" and top_seg["flightNumber"] == "GA200"
    assert top_seg["depAirport"] == "KNO" and top_seg["arrAirport"] == "CGK"
    assert top_seg["depTime"].startswith("2026-09-20")
    assert after["data"]["pnrs"][0]["segments"][0] == {
        "depAirport": "KNO", "arrAirport": "CGK", "flightNumber": "GA200"
    }
    assert after["data"]["flightRefs"][0]["flightIndex"] == 0
    assert after["data"]["ancillaryList"][0]["passengerName"] == "SANTOSO/SITI"
