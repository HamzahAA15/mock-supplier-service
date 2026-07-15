"""Second Baggage fixed catalog + deterministic productItemId — TSY BPI variant.

Same stateless philosophy as offer_key: search derives IDs on the fly, order
re-derives from its own RQ and compares. No shared state, restart-tolerant.
Specific to TSY BPI (tsy-bpi contract); a second BPI version is planned separately.
"""
import base64
import hashlib
import zlib
from typing import Any, Dict, List, Optional

CURRENCY = "USD"

# 9 fixed baggage tiers: weight (kg) -> base price (USD). From the tsy-bpi sample.
BAGGAGE_TIERS = {
    20: 52.14,
    30: 76.84,
    40: 103.18,
    50: 256.30,
    60: 307.33,
    70: 358.38,
    80: 430.27,
    90: 483.49,
    100: 536.74,
}
TIER_WEIGHTS = sorted(BAGGAGE_TIERS)  # ascending 20..100

# Routes not eligible for second baggage at order time (directional dep->arr).
# Ordering these fails the order with HTTP 500 (see routers/bpi.py, BPI_DESIGN.md).
BLOCKED_SECOND_BAGGAGE_ROUTES = {("SIN", "KUL"), ("SIN", "CGK")}


def is_route_blocked(seg: Dict[str, Any]) -> bool:
    return (seg.get("depAirport"), seg.get("arrAirport")) in BLOCKED_SECOND_BAGGAGE_ROUTES


def _segment_key(seg: Dict[str, Any]) -> str:
    """The six core segment fields that identify a flight leg (used for the
    productItemId hash and the orderDetail numeric segment id)."""
    return "{}|{}|{}|{}|{}|{}".format(
        seg.get("carrier", ""),
        seg.get("flightNumber", ""),
        seg.get("depAirport", ""),
        seg.get("depTime", ""),
        seg.get("arrAirport", ""),
        seg.get("arrTime", ""),
    )


def product_item_id(seg: Dict[str, Any], weight_kg: int) -> str:
    """Deterministic, stateless. Standard base64 of sha256 (matches sample format)."""
    raw = "{}|{}|BPI".format(_segment_key(seg), weight_kg)
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def segment_numeric_id(seg: Dict[str, Any]) -> int:
    """Stable positive int id for a segment (crc32 of its key)."""
    return zlib.crc32(_segment_key(seg).encode("utf-8")) & 0xFFFFFFFF


def _refund_rule() -> Dict[str, Any]:
    return {
        "canRefund": False,
        "canRefundIndependent": False,
        "refundRule": "*",
        "canModify": False,
        "canModifyIndependent": False,
        "modifyRule": "*",
    }


def build_product_items(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = []
    for kg in TIER_WEIGHTS:
        items.append({
            "productItemId": product_item_id(seg, kg),
            "productType": 1,
            "saleType": 2,
            "basePrice": BAGGAGE_TIERS[kg],
            "currency": CURRENCY,
            "supportOverWeight": False,
            "baggage": {"baggagePieces": 1, "baggageAllowance": kg, "isAllWeight": True},
            "refundRule": _refund_rule(),
            "dataSource": None,
        })
    return items


def enrich_segment(seg: Dict[str, Any]) -> Dict[str, Any]:
    """Echo the RQ segment enriched with the static extra fields from the sample."""
    trip_type = seg.get("tripType")
    return {
        "carrier": seg.get("carrier", ""),
        "flightNumber": seg.get("flightNumber", ""),
        "depAirport": seg.get("depAirport", ""),
        "depTerminal": "",
        "depTime": seg.get("depTime", ""),
        "arrAirport": seg.get("arrAirport", ""),
        "arrTerminal": "",
        "arrTime": seg.get("arrTime", ""),
        "stopCities": "",
        "stopAirports": "",
        "codeShare": False,
        "operatingCarrier": "",
        "operatingFlightNo": "",
        "cabin": "B",
        "cabinGrade": "Y",
        "cabinCount": None,
        "aircraftCode": "",
        "duration": 0,
        "isTransitVisa": False,
        "tripType": "" if trip_type is None else str(trip_type),
        "segmentIndex": seg.get("segmentIndex"),
    }


def validate_product_item(seg: Dict[str, Any], weight_kg: Optional[int], claimed_id: Optional[str]) -> bool:
    """Order-time check: weight must be a known tier and the productItemId must
    re-derive from the RQ segment + weight."""
    if weight_kg not in BAGGAGE_TIERS:
        return False
    return claimed_id == product_item_id(seg, weight_kg)
