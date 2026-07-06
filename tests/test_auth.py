def test_token_returns_bearer_and_scope(client):
    res = client.post("/uaa/oauth/token", json={"grantType": "clientCredentials"})
    assert res.status_code == 200
    body = res.json()
    assert "code" not in body  # no envelope on the auth endpoint
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] == 3600
    assert body["scope"] == "search preOrderVerify ancillarySearch order pay orderDetail"
    assert len(body["accessToken"]) == 36  # uuid


def test_token_tolerates_empty_body(client):
    res = client.post("/uaa/oauth/token")
    assert res.status_code == 200
    assert res.json()["tokenType"] == "Bearer"
