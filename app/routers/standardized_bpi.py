"""Standardized BPI endpoints — Standardized Ancillary Post-Issuance contract.

Flow: search (POST /ancillary/v1/baggage/search) -> order (POST
/ancillary/v1/orders) -> orderDetail (GET /ancillary/v1/orders/{no}).
No pay step: order RS returns ISSUING, orderDetail always returns ISSUED
(Traveloka polls orderDetail until the status changes).

Envelope: {"code": int, "msg": str, "data": obj|null}, always HTTP 200.
The Authorization header is accepted but never validated (mock decision).
See STANDARDIZED_BPI_DESIGN.md.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from app.models.standardized_bpi import (
    StandardizedBpiOrderRequest,
    StandardizedBpiSearchRequest,
)
from app.services import standardized_bpi_catalog as catalog
from app.services.standardized_bpi_orders import store

router = APIRouter(prefix="/ancillary/v1")

# Result codes (PRD section V, Result Code table).
CODE_SUCCESS = 0
CODE_INVALID_ORDER_NO = 400
CODE_NO_QUOTATION = 555
CODE_SALE_PROHIBITED = 5001

MSG_INVALID_ORDER_NO = "invalid ancillary order number"
MSG_INVALID_KEY = "invalid ancillaryKey"
MSG_NO_QUOTATION = "no ancillary quotation for the current offer"
MSG_SALE_PROHIBITED = "prohibition of sale before or after departure"


def ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"code": CODE_SUCCESS, "msg": "Success", "data": data}


def err(code: int, msg: str) -> Dict[str, Any]:
    return {"code": code, "msg": msg, "data": None}


def _echo_passenger(pax: Dict[str, Any]) -> Dict[str, Any]:
    echoed = {
        "passengerId": pax.get("passengerId"),
        "pnr": pax.get("pnr", ""),
        "firstName": pax.get("firstName", ""),
        "lastName": pax.get("lastName", ""),
        "passengerType": pax.get("passengerType", ""),
    }
    ticket_no = pax.get("ticketNumber") or pax.get("ticketNo")
    if ticket_no is not None:
        echoed["ticketNumber"] = ticket_no
    return echoed


@router.post("/baggage/search")
def standardized_bpi_search(req: StandardizedBpiSearchRequest):
    if req.ancillary_type != catalog.ANCILLARY_TYPE_BAGGAGE:
        return err(CODE_NO_QUOTATION, MSG_NO_QUOTATION)

    routes = req.routes or []
    if not routes:
        return err(CODE_NO_QUOTATION, MSG_NO_QUOTATION)

    for route in routes:
        for seg in (route.get("segments") or []):
            if catalog.is_route_blocked(seg):
                return err(CODE_NO_QUOTATION, MSG_NO_QUOTATION)
            if catalog.is_departure_past(seg):
                return err(CODE_SALE_PROHIBITED, MSG_SALE_PROHIBITED)

    # Post-issuance (passengers present) -> per-passenger offers.
    # Pre-issuance live fetch (no passengers) -> general offers.
    passengers = req.passengers or []

    rs_routes: List[Dict[str, Any]] = []
    for route in routes:
        trip_type = route.get("tripType")
        segments = route.get("segments") or []
        offers = catalog.build_ancillary_offers(trip_type, segments)
        rs_route: Dict[str, Any] = {
            "tripType": trip_type,
            # Echo principle: reflect the RQ segments back verbatim.
            "segments": segments,
        }
        if passengers:
            rs_route["passengerOffers"] = [
                {"passengerId": pax.get("passengerId"), "ancillaryOffers": offers}
                for pax in passengers
            ]
        else:
            rs_route["generalOffers"] = [{"ancillaryOffers": offers}]
        rs_routes.append(rs_route)

    return ok({"currency": catalog.CURRENCY, "routes": rs_routes})


@router.post("/orders")
def standardized_bpi_order(req: StandardizedBpiOrderRequest):
    order_no = req.ancillary_order_no
    if not order_no:
        return err(CODE_INVALID_ORDER_NO, MSG_INVALID_ORDER_NO)

    passengers = req.passengers or []
    pax_ids = {pax.get("passengerId") for pax in passengers}

    selected = req.selected_ancillary or []
    if not selected:
        return err(CODE_INVALID_ORDER_NO, "selectedAncillary cannot be empty")

    total = 0.0
    rs_selected: List[Dict[str, Any]] = []
    for item in selected:
        pax_id = item.get("passengerId")
        if pax_id not in pax_ids:
            return err(CODE_INVALID_ORDER_NO, "invalid passengerId {}".format(pax_id))
        decoded = catalog.decode_ancillary_key(item.get("ancillaryKey"))
        if decoded is None:
            return err(CODE_INVALID_ORDER_NO, MSG_INVALID_KEY)
        for seg in decoded["segments"]:
            if catalog.is_route_blocked(seg):
                return err(CODE_NO_QUOTATION, MSG_NO_QUOTATION)
        weight = decoded["weight"]
        price = catalog.BAGGAGE_TIERS[weight]
        total += price
        rs_selected.append({
            "passengerId": pax_id,
            "ancillaryKey": item.get("ancillaryKey"),
            "ancillaryType": catalog.ANCILLARY_TYPE_BAGGAGE,
            "ancillaryCode": weight,
            "ancillaryPiece": 1,
            "price": price,
            # Reconstructed from the self-describing key (order RQ has no segments).
            "segments": decoded["segments"],
        })

    now = catalog.now_timestamp()
    is_cross = req.is_cross if req.is_cross is not None else True
    record = {
        "ancillaryOrderNo": order_no,
        "total": round(total, 2),
        "currency": catalog.CURRENCY,
        "isCross": is_cross,
        "createdTime": now,
        "passengers": [_echo_passenger(pax) for pax in passengers],
        "selectedAncillary": rs_selected,
    }
    store.upsert(order_no, record)

    return ok({
        "ancillaryOrderNo": order_no,
        "orderStatus": "ISSUING",
        "total": record["total"],
        "currency": catalog.CURRENCY,
        "isCross": is_cross,
        "createdTime": now,
        "updatedTime": now,
        "passengers": record["passengers"],
        "selectedAncillary": rs_selected,
    })


@router.get("/orders/{ancillary_order_no}")
def standardized_bpi_order_detail(ancillary_order_no: str):
    record = store.get(ancillary_order_no)
    if record is None:
        return err(CODE_INVALID_ORDER_NO, MSG_INVALID_ORDER_NO)

    detail_selected = [
        dict(item, unitOfMeasurement=catalog.unit_of_measurement(item.get("segments")))
        for item in record["selectedAncillary"]
    ]
    return ok({
        "ancillaryOrderNo": record["ancillaryOrderNo"],
        "orderStatus": "ISSUED",  # polling target state; mock issues immediately
        "total": record["total"],
        "currency": record["currency"],
        "isCross": record["isCross"],
        "createdTime": record["createdTime"],
        "updatedTime": catalog.now_timestamp(),
        "passengers": record["passengers"],
        "selectedAncillary": detail_selected,
    })
