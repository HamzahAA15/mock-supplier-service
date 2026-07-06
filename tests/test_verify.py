from tests.conftest import search_body

GA_KEY = "R0F8Q0dLfERQU3wyMDI2LTA3LTEwfEJBU0lD"  # GA|CGK|DPS|2026-07-10|BASIC


def test_verify_echoes_single_offer(client):
    res = client.post("/flight/preOrderVerify/v3", json={"offerKey": GA_KEY})
    body = res.json()
    assert body["code"] == 0
    data = body["data"]
    assert len(data["offers"]) == 1
    assert data["offers"][0]["offerKey"] == GA_KEY
    # Refs re-indexed to 0 in the single-offer view.
    assert data["offers"][0]["flightRefs"] == [{"flightIndex": 0}]
    assert data["flights"][0]["segmentRefs"][0]["segmentIndex"] == 0
    seg = data["segments"][0]
    assert seg["flightNumber"] == "GA200"
    assert seg["depAirport"] == "CGK" and seg["arrAirport"] == "DPS"
    assert seg["depTime"] == "2026-07-10 12:00:00"
    assert data["ancillaries"][0]["ancillaryCode"] == 20


def test_verify_matches_search_offer_key(client):
    search_key = client.post("/flight/search/v3", json=search_body()).json()["data"]["offers"][1]["offerKey"]
    verified = client.post("/flight/preOrderVerify/v3", json={"offerKey": search_key}).json()
    assert verified["data"]["offers"][0]["offerKey"] == search_key


def test_empty_offer_key_101(client):
    assert client.post("/flight/preOrderVerify/v3", json={"offerKey": ""}).json()["code"] == 101
    assert client.post("/flight/preOrderVerify/v3", json={}).json()["code"] == 101


def test_undecodable_offer_key_204(client):
    assert client.post("/flight/preOrderVerify/v3", json={"offerKey": "not-a-key"}).json()["code"] == 204
