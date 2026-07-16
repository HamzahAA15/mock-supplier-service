"""AES-encrypted /orderCrossSecondBaggage request + response handling.

The client sends the order body AES/CBC/PKCS5-encrypted + base64 (key reused as IV).
The endpoint decrypts first, then falls back to plaintext JSON. When the request was
encrypted, the response is encrypted too (symmetric channel); plaintext in -> plaintext out.
"""
import json

import pytest

from app.services import crypto
from tests.bpi_helpers import (
    SEG_SIN_KUL, SEG_VJ, decrypt_order_response, order_body, pax_aux,
    post_encrypted_order, product_item_for, search_body,
)


def _search(client, segments=None):
    return client.post("/secondBaggage", json=search_body(segments=segments)).json()


def test_crypto_roundtrip_unit():
    plain = '{"hello":"world","n":42}'
    assert crypto.decrypt_aes_cbc(crypto.encrypt_aes_cbc(plain)) == plain


def test_encrypted_order_happy_path(client):
    rs = _search(client)
    item = product_item_for(rs, 0, 70)
    res = post_encrypted_order(client, order_body("ENC-1", [pax_aux(SEG_VJ, item)]))
    assert res.status_code == 200
    # Response is encrypted (not JSON) — the raw body does not parse as JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(res.text)
    body = decrypt_order_response(res)
    assert body["status"] == "0"
    assert body["auxiliaryOrderNo"] == "ENC-1"
    # Order really landed (decrypted payload was used).
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "ENC-1"}).json()
    assert det["data"]["orderStatus"] == "PURCHASED"
    assert det["data"]["totalPrice"] == 358.38


def test_plaintext_still_accepted_and_plaintext_response(client):
    # Symmetric: plaintext request -> plaintext JSON response (no decryption needed).
    rs = _search(client)
    item = product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage", json=order_body("PLAIN-1", [pax_aux(SEG_VJ, item)]))
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    assert res.json()["status"] == "0"


def test_encrypted_blocked_route_still_500_and_encrypted(client):
    # Business rules apply after decryption: SIN->KUL still fails with HTTP 500,
    # and the 500 body is encrypted too (all responses encrypted for an encrypted request).
    rs = _search(client, segments=[SEG_SIN_KUL])
    item = product_item_for(rs, 0, 20)
    res = post_encrypted_order(client, order_body("ENC-BLK", [pax_aux(SEG_SIN_KUL, item)]))
    assert res.status_code == 500
    body = decrypt_order_response(res)
    assert body["status"] == "1"
    assert "SIN-KUL" in body["msg"]


def test_encrypted_invalid_product_item_error_encrypted(client):
    # An error envelope for an encrypted request is itself encrypted.
    rs = _search(client)
    item = dict(product_item_for(rs, 0, 20), productItemId="TAMPERED/notreal=")
    res = post_encrypted_order(client, order_body("ENC-BAD", [pax_aux(SEG_VJ, item)]))
    assert res.status_code == 200
    body = decrypt_order_response(res)
    assert body["status"] == "1"
    assert body["auxiliaryOrderNo"] is None


def test_garbage_body_rejected(client):
    # Not valid base64-AES and not valid JSON -> invalid request body.
    res = client.post("/orderCrossSecondBaggage", content="!!!not-encrypted-not-json!!!",
                      headers={"Content-Type": "text/plain"})
    assert res.status_code == 200
    assert res.json()["status"] == "1"


def test_wire_format_matches_java_contract():
    # Encrypting a known string yields standard base64 that decrypts back (sanity of key/IV/mode).
    body = order_body("X", [])
    ciphertext = crypto.encrypt_aes_cbc(json.dumps(body))
    # base64 standard alphabet, decodes cleanly
    import base64
    base64.b64decode(ciphertext, validate=True)
    assert json.loads(crypto.decrypt_aes_cbc(ciphertext)) == body


def test_decrypt_tolerates_transit_corruption():
    # base64 in an HTTP body is commonly mangled: '+' -> space (form-encoding),
    # base64url alphabet, and MIME chunk newlines. All must still decrypt.
    pt = '{"ancillaryOrderNo":"105608238-0-0","isCross":1,"passengerAuxes":[]}'
    ct = crypto.encrypt_aes_cbc(pt)
    assert "+" in ct  # this fixture ciphertext actually contains '+'
    assert crypto.decrypt_aes_cbc(ct.replace("+", " ")) == pt          # form-encoding
    assert crypto.decrypt_aes_cbc(ct.replace("+", "-").replace("/", "_").rstrip("=")) == pt  # base64url
    assert crypto.decrypt_aes_cbc("\n".join(ct[i:i + 64] for i in range(0, len(ct), 64))) == pt  # chunked


def test_endpoint_accepts_form_mangled_encrypted_body(client):
    # An encrypted order whose '+' were turned into spaces in transit still works.
    rs = _search(client)
    item = product_item_for(rs, 0, 40)
    from tests.bpi_helpers import encrypt_order_body
    ciphertext = encrypt_order_body(order_body("ENC-FORM", [pax_aux(SEG_VJ, item)]))
    mangled = ciphertext.replace("+", " ")  # simulate application/x-www-form-urlencoded
    res = client.post("/orderCrossSecondBaggage", content=mangled,
                      headers={"Content-Type": "text/plain"})
    assert res.status_code == 200
    assert decrypt_order_response(res)["status"] == "0"
    assert client.post("/ancillaryOrderDetail",
                       json={"auxiliaryOrderNo": "ENC-FORM"}).json()["data"]["orderStatus"] == "PURCHASED"
