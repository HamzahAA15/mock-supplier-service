"""Second Baggage endpoints — TSY BPI variant (tsy-bpi contract).

Flow: search (/secondBaggage) -> order (/orderCrossSecondBaggage) -> orderDetail
(/ancillaryOrderDetail). No pay step: a successful order means paid, so
orderDetail always returns orderStatus PURCHASED. See BPI_DESIGN.md.

These three paths and their logic are specific to TSY BPI; a second BPI version
(standardizedv3-bpi) is planned separately and would live in its own router.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.models.bpi import BpiOrderDetailRequest, BpiOrderRequest, BpiSearchRequest
from app.services import bpi_catalog, crypto
from app.services.bpi_orders import store

router = APIRouter()

_ORDER_FAILURE = {"auxiliaryOrderNo": None, "msg": "invalid productItemId", "status": "1"}


def _parse_order_payload(raw: bytes):
    """The /orderCrossSecondBaggage body is AES-CBC encrypted + base64 by the client.
    Try to decrypt first (the real client path); fall back to plaintext JSON so
    existing tests / manual curl keep working.

    Returns (payload_dict_or_None, was_encrypted). was_encrypted drives whether the
    response is encrypted too (symmetric channel).
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}, False
    try:
        return json.loads(crypto.decrypt_aes_cbc(text)), True
    except Exception:
        pass
    try:
        return json.loads(text), False
    except Exception:
        return None, False


def _order_response(body: dict, encrypted: bool, status_code: int = 200):
    """Encrypt the response body (same AES/CBC + base64) when the request was
    encrypted; otherwise return plain JSON. Applies to success and every error."""
    if encrypted:
        return Response(content=crypto.encrypt_aes_cbc(json.dumps(body)),
                        media_type="text/plain", status_code=status_code)
    return JSONResponse(content=body, status_code=status_code)


@router.post("/secondBaggage")
def bpi_search(req: BpiSearchRequest):
    # Response depends only on segments; passenger array is ignored.
    products = [
        {
            "segment": bpi_catalog.enrich_segment(seg),
            "productItems": bpi_catalog.build_product_items(seg),
        }
        for seg in (req.segments or [])
    ]
    return {"status": "0", "msg": "success", "auxiliaryOrderNo": None, "products": products}


@router.post("/orderCrossSecondBaggage")
async def bpi_order(request: Request):
    # AES-encrypted body (client) or plaintext JSON (fallback) — see _parse_order_payload.
    # The response is encrypted iff the request was (symmetric channel).
    payload, encrypted = _parse_order_payload(await request.body())
    if payload is None:
        return _order_response({"auxiliaryOrderNo": None, "msg": "invalid request body", "status": "1"}, encrypted)
    req = BpiOrderRequest.model_validate(payload)

    aux_no = req.ancillary_order_no or req.order_no
    if not aux_no:
        return _order_response({"auxiliaryOrderNo": None, "msg": "ancillaryOrderNo cannot be empty", "status": "1"}, encrypted)

    stored_auxes = []
    for pax in (req.passenger_auxes or []):
        seg_products = pax.get("segmentProducts") or {}
        seg = seg_products.get("segment") or {}
        product_item = seg_products.get("productItem") or {}
        baggage = product_item.get("baggage") or {}
        weight = baggage.get("baggageAllowance")
        # Business rule: certain routes are not eligible for second baggage. Fail the
        # order hard with HTTP 500 before it is created (see BPI_DESIGN.md).
        if bpi_catalog.is_route_blocked(seg):
            return _order_response({
                "auxiliaryOrderNo": None,
                "status": "1",
                "msg": "second baggage not available for route {}-{}".format(
                    seg.get("depAirport", ""), seg.get("arrAirport", "")),
            }, encrypted, status_code=500)
        if not bpi_catalog.validate_product_item(seg, weight, product_item.get("productItemId")):
            return _order_response(dict(_ORDER_FAILURE), encrypted)
        stored_auxes.append({
            "passengerInfo": pax.get("passengerInfo") or {},
            "segment": seg,
            "weight": weight,
            "basePrice": bpi_catalog.BAGGAGE_TIERS[weight],
        })

    is_cross = req.is_cross if req.is_cross is not None else 1
    store.upsert(aux_no, is_cross, stored_auxes)
    return _order_response({"auxiliaryOrderNo": aux_no, "msg": "success", "status": "0"}, encrypted)


@router.post("/ancillaryOrderDetail")
def bpi_order_detail(req: BpiOrderDetailRequest):
    aux_no = req.auxiliary_order_no
    order = store.get(aux_no) if aux_no else None
    if order is None:
        return {"status": "1", "msg": "order not found", "data": None}

    # Dedupe segments, assign a stable numeric id, and link passengerAncillaries to it.
    seg_id_by_key = {}
    segments = []
    for aux in order["passengerAuxes"]:
        seg = aux["segment"]
        key = bpi_catalog._segment_key(seg)
        if key not in seg_id_by_key:
            seg_id = bpi_catalog.segment_numeric_id(seg)
            seg_id_by_key[key] = seg_id
            segments.append({
                "depAirport": seg.get("depAirport", ""),
                "depTime": seg.get("depTime", ""),
                "arrAirport": seg.get("arrAirport", ""),
                "arrTime": None,  # null per sample
                "flightNumber": seg.get("flightNumber", ""),
                "segmentIndex": seg.get("segmentIndex"),
                "id": seg_id,
            })

    passenger_ancillaries = []
    total = 0.0
    for aux in order["passengerAuxes"]:
        info = aux["passengerInfo"]
        total += aux["basePrice"]
        passenger_ancillaries.append({
            "passengerName": "{}/{}".format(info.get("lastName", ""), info.get("firstName", "")),
            "baggageWeight": str(aux["weight"]),
            "pnrNo": info.get("pnrCode", ""),
            "segmentId": seg_id_by_key[bpi_catalog._segment_key(aux["segment"])],
        })

    return {
        "status": "0",
        "msg": "success",
        "data": {
            "ancillaryOrderNo": order["auxiliaryOrderNo"],
            "orderStatus": "PURCHASED",
            "currency": bpi_catalog.CURRENCY,
            "isCross": order["isCross"],
            "totalPrice": round(total, 2),
            "segments": segments,
            "passengerAncillaries": passenger_ancillaries,
        },
    }
