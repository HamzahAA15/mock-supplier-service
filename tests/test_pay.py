from app.services.offer_key import encode_offer_key
from tests.conftest import order_body

GA_KEY = encode_offer_key("GA", "CGK", "DPS", "2026-07-10")


def place_order(client, **kwargs):
    return client.post("/flight/order/v3", json=order_body(GA_KEY, **kwargs)).json()["data"]["orderId"]


def test_pay_transitions_to_issued(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "BPA", "accountNumber": ""}).json()
    assert res["code"] == 0
    data = res["data"]
    assert data["transactionId"].startswith("TXN")
    assert data["amount"] == "107.00"  # 95 + 12, string per contract
    assert data["currency"] == "USD"
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert detail["data"]["orderInfo"]["status"] == "ISSUED"
    assert detail["data"]["orderInfo"]["payTime"] != ""


def test_ticket_number_13_digits_per_passenger(client):
    passengers = [
        {"firstName": "BUDI", "lastName": "SANTOSO", "passengerType": "ADT"},
        {"firstName": "SITI", "lastName": "SANTOSO", "passengerType": "ADT"},
    ]
    order_id = place_order(client, passengers=passengers)
    client.post("/flight/pay/v3", json={"orderId": order_id})
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    tickets = [p["ticketNumber"] for p in detail["data"]["pnrs"][0]["passengers"]]
    assert len(tickets) == 2
    assert all(t.isdigit() and len(t) == 13 for t in tickets)


def test_pay_antom_returns_receiver_wallet_account(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "ANTOM", "accountNumber": ""}).json()
    assert res["code"] == 0
    data = res["data"]
    assert data["accountNumber"] == "21881200168224D1"  # receiver account, not payer's
    assert data["amount"] == "107.00"
    detail = client.post("/flight/orderDetail/v3", json={"orderId": order_id}).json()
    assert detail["data"]["orderInfo"]["status"] == "ISSUED"
    assert detail["data"]["orderInfo"]["accountNumber"] == "21881200168224D1"


def test_pay_yeepay_returns_receiver_wallet_account(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "YEEPAY", "accountNumber": ""}).json()
    assert res["code"] == 0
    assert res["data"]["accountNumber"] == "21881200168224D1"


def test_pay_wallet_type_case_insensitive(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "antom"}).json()
    assert res["code"] == 0
    assert res["data"]["accountNumber"] == "21881200168224D1"


def test_pay_wallet_ignores_payer_account_number(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "YEEPAY", "accountNumber": "PAYER_WALLET_123"}).json()
    assert res["code"] == 0
    assert res["data"]["accountNumber"] == "21881200168224D1"


def test_pay_bpa_echoes_request_account_number(client):
    order_id = place_order(client)
    res = client.post("/flight/pay/v3", json={"orderId": order_id, "payType": "BPA", "accountNumber": "TVLK_ACC"}).json()
    assert res["code"] == 0
    assert res["data"]["accountNumber"] == "TVLK_ACC"


def test_duplicate_payment_748(client):
    order_id = place_order(client)
    assert client.post("/flight/pay/v3", json={"orderId": order_id}).json()["code"] == 0
    assert client.post("/flight/pay/v3", json={"orderId": order_id}).json()["code"] == 748


def test_unknown_order_148(client):
    assert client.post("/flight/pay/v3", json={"orderId": "0000000000"}).json()["code"] == 148


def test_empty_order_id_745(client):
    assert client.post("/flight/pay/v3", json={"orderId": ""}).json()["code"] == 745
    assert client.post("/flight/pay/v3", json={}).json()["code"] == 745
