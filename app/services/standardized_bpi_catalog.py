"""Standardized BPI catalog: self-describing ancillaryKey + offer building.

Contract: PRD "Standardized 3PS Baggage Post Issuance Automation" section V.
See STANDARDIZED_BPI_DESIGN.md.

Same stateless philosophy as offer_key/bpi_catalog, but the key must be
REVERSIBLE: the standardized order RQ carries no segment data, so the order
endpoint decodes the ancillaryKey to validate the tier and reconstruct the
segments echoed in the order/orderDetail responses. Restart-tolerant, no
shared state between search and order.

The baggage tiers and blocked routes are shared with the tsy-bpi version —
same behaviour, different contract.
"""
import base64
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.bpi_catalog import (  # shared with tsy-bpi
    BAGGAGE_TIERS,
    BLOCKED_SECOND_BAGGAGE_ROUTES,
    CURRENCY,
    PIECE_CARRIERS,
    TIER_WEIGHTS,
)

KEY_PREFIX = "SBPI"
ANCILLARY_TYPE_BAGGAGE = "CHECKEDBAGGAGE"
UNIT_OF_MEASUREMENT = "WEIGHT"       # default (weight-based carriers)
UNIT_OF_MEASUREMENT_PIECE = "PIECE"  # PIECE_CARRIERS (e.g. MM)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def unit_of_measurement(segments: Optional[List[Dict[str, Any]]]) -> str:
    """PIECE when any segment's marketingCarrier is a PIECE carrier (e.g. MM),
    else WEIGHT."""
    for seg in segments or []:
        if (seg.get("marketingCarrier") or "") in PIECE_CARRIERS:
            return UNIT_OF_MEASUREMENT_PIECE
    return UNIT_OF_MEASUREMENT

# Segment fields encoded into the ancillaryKey, in order. Enough to fully
# reconstruct the standardized Segments Element in order/orderDetail RS.
_SEG_FIELDS = (
    "marketingCarrier",
    "flightNumber",
    "operatingCarrier",
    "operatingFlightNumber",
    "departureAirport",
    "arrivalAirport",
    "departureTime",
    "arrivalTime",
)


def _segment_tuple(seg: Dict[str, Any]) -> List[str]:
    marketing = seg.get("marketingCarrier", "") or ""
    flight_no = seg.get("flightNumber", "") or ""
    return [
        marketing,
        flight_no,
        seg.get("operatingCarrier") or marketing,
        seg.get("operatingFlightNumber") or flight_no,
        seg.get("departureAirport", "") or "",
        seg.get("arrivalAirport", "") or "",
        seg.get("departureTime", "") or "",
        seg.get("arrivalTime", "") or "",
    ]


def encode_ancillary_key(trip_type: Any, segments: List[Dict[str, Any]], weight_kg: int) -> str:
    """Deterministic, reversible key: base64url of a compact JSON envelope."""
    payload = [KEY_PREFIX, trip_type, weight_kg, [_segment_tuple(s) for s in segments or []]]
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_ancillary_key(key: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns {tripType, weight, segments[]} or None if the key is invalid.
    A key is valid only if it decodes, carries the SBPI prefix, and its weight
    is a known baggage tier."""
    if not key or not isinstance(key, str):
        return None
    try:
        raw = base64.urlsafe_b64decode(key.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list) or len(payload) != 4 or payload[0] != KEY_PREFIX:
        return None
    _, trip_type, weight, seg_tuples = payload
    if weight not in BAGGAGE_TIERS or not isinstance(seg_tuples, list):
        return None
    segments = []
    for t in seg_tuples:
        if not isinstance(t, list) or len(t) != len(_SEG_FIELDS):
            return None
        segments.append(dict(zip(_SEG_FIELDS, t)))
    return {"tripType": trip_type, "weight": weight, "segments": segments}


def is_route_blocked(seg: Dict[str, Any]) -> bool:
    """Standardized field names; same directional blocklist as tsy-bpi."""
    return (seg.get("departureAirport"), seg.get("arrivalAirport")) in BLOCKED_SECOND_BAGGAGE_ROUTES


def is_departure_past(seg: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """True only when departureTime parses and is strictly in the past.
    Unparseable/missing values are tolerated (permissive mock)."""
    value = seg.get("departureTime")
    if not value or not isinstance(value, str):
        return False
    try:
        departure = datetime.strptime(value.strip(), TIME_FORMAT)
    except ValueError:
        return False
    return departure < (now or datetime.now())


def build_ancillary_offers(trip_type: Any, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The 9 shared tiers as standardized Ancillary Offer Elements. One key per
    (route segment-chain, tier); identical across passengers by design."""
    unit = unit_of_measurement(segments)  # PIECE for MM, else WEIGHT
    offers = []
    for kg in TIER_WEIGHTS:
        offers.append({
            "ancillaryKey": encode_ancillary_key(trip_type, segments, kg),
            "ancillaryType": ANCILLARY_TYPE_BAGGAGE,
            "ancillaryCode": kg,
            "ancillaryPiece": 1,
            "unitOfMeasurement": unit,
            "price": BAGGAGE_TIERS[kg],
        })
    return offers


def now_timestamp() -> str:
    return datetime.now().strftime(TIME_FORMAT)
