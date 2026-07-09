"""Baggage Post-Issuance (BPI) endpoints — tsy-bpi contract.

Flow: search (/postBaggage) -> order (/orderCrossPostBaggage) -> orderDetail
(/ancillaryOrderDetail). No pay step: a successful order means paid, so
orderDetail always returns orderStatus PURCHASED. See BPI_DESIGN.md.
"""
from fastapi import APIRouter

from app.models.bpi import BpiOrderDetailRequest, BpiOrderRequest, BpiSearchRequest
from app.services import bpi_catalog
from app.services.bpi_orders import store

router = APIRouter()

_ORDER_FAILURE = {"auxiliaryOrderNo": None, "msg": "invalid productItemId", "status": "1"}


@router.post("/postBaggage")
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


@router.post("/orderCrossPostBaggage")
def bpi_order(req: BpiOrderRequest):
    aux_no = req.ancillary_order_no or req.order_no
    if not aux_no:
        return {"auxiliaryOrderNo": None, "msg": "ancillaryOrderNo cannot be empty", "status": "1"}

    stored_auxes = []
    for pax in (req.passenger_auxes or []):
        seg_products = pax.get("segmentProducts") or {}
        seg = seg_products.get("segment") or {}
        product_item = seg_products.get("productItem") or {}
        baggage = product_item.get("baggage") or {}
        weight = baggage.get("baggageAllowance")
        if not bpi_catalog.validate_product_item(seg, weight, product_item.get("productItemId")):
            return dict(_ORDER_FAILURE)
        stored_auxes.append({
            "passengerInfo": pax.get("passengerInfo") or {},
            "segment": seg,
            "weight": weight,
            "basePrice": bpi_catalog.BAGGAGE_TIERS[weight],
        })

    is_cross = req.is_cross if req.is_cross is not None else 1
    store.upsert(aux_no, is_cross, stored_auxes)
    return {"auxiliaryOrderNo": aux_no, "msg": "success", "status": "0"}


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
