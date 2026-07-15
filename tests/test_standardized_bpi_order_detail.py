from tests.standardized_bpi_helpers import ORDER_PATH, search_then_order


def test_order_detail_happy_path(client):
    _, order_rs = search_then_order(client, order_no="TVLK-BPI-D1", weight_kg=40)
    res = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-D1"))
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0 and body["msg"] == "Success"
    data = body["data"]
    assert data["ancillaryOrderNo"] == "TVLK-BPI-D1"
    # Polling target state: the mock issues immediately.
    assert data["orderStatus"] == "ISSUED"
    assert data["total"] == order_rs["data"]["total"]
    assert data["currency"] == "USD"
    assert data["isCross"] is True
    assert data["createdTime"] == order_rs["data"]["createdTime"]
    assert data["passengers"] == order_rs["data"]["passengers"]


def test_order_detail_adds_unit_of_measurement(client):
    search_then_order(client, order_no="TVLK-BPI-D2", weight_kg=20)
    body = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-D2")).json()
    item = body["data"]["selectedAncillary"][0]
    assert item["unitOfMeasurement"] == "WEIGHT"
    assert item["ancillaryCode"] == 20 and item["ancillaryPiece"] == 1
    assert item["segments"]  # segments reconstructed from the key are preserved


def test_order_detail_unknown_order_returns_400(client):
    body = client.get("{}/{}".format(ORDER_PATH, "NO-SUCH-ORDER")).json()
    assert body["code"] == 400
    assert body["msg"] == "invalid ancillary order number"
    assert body["data"] is None


def test_order_detail_is_repeatable(client):
    # Traveloka polls this endpoint; every poll must return ISSUED consistently.
    search_then_order(client, order_no="TVLK-BPI-D3", weight_kg=20)
    first = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-D3")).json()
    second = client.get("{}/{}".format(ORDER_PATH, "TVLK-BPI-D3")).json()
    assert first["data"]["orderStatus"] == second["data"]["orderStatus"] == "ISSUED"
    assert first["data"]["total"] == second["data"]["total"]
