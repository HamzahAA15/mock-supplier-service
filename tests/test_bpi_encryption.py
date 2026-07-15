"""AES-encrypted /orderCrossSecondBaggage request handling.

The client sends the order body AES/CBC/PKCS5-encrypted + base64 (key reused as IV).
The endpoint decrypts first, then falls back to plaintext JSON.
"""
import json

from app.services import crypto
from tests.bpi_helpers import (
    SEG_SIN_KUL, SEG_VJ, order_body, pax_aux, post_encrypted_order, product_item_for, search_body,
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
    body = res.json()
    assert body["status"] == "0"
    assert body["auxiliaryOrderNo"] == "ENC-1"
    # Order really landed (decrypted payload was used).
    det = client.post("/ancillaryOrderDetail", json={"auxiliaryOrderNo": "ENC-1"}).json()
    assert det["data"]["orderStatus"] == "PURCHASED"
    assert det["data"]["totalPrice"] == 358.38


def test_plaintext_still_accepted(client):
    # Fallback: plaintext JSON body keeps working (accept-both).
    rs = _search(client)
    item = product_item_for(rs, 0, 20)
    res = client.post("/orderCrossSecondBaggage", json=order_body("PLAIN-1", [pax_aux(SEG_VJ, item)]))
    assert res.status_code == 200
    assert res.json()["status"] == "0"


def test_encrypted_blocked_route_still_500(client):
    # Business rules apply after decryption: SIN->KUL still fails with HTTP 500.
    rs = _search(client, segments=[SEG_SIN_KUL])
    item = product_item_for(rs, 0, 20)
    res = post_encrypted_order(client, order_body("ENC-BLK", [pax_aux(SEG_SIN_KUL, item)]))
    assert res.status_code == 500
    assert "SIN-KUL" in res.json()["msg"]


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
