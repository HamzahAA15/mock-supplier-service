"""Builds Search-shaped offer data from fixed inventory + echoed request fields.

The route (ori/dest), departure date and pax counts always come from the request
(echo principle, DESIGN.md section 3.1); everything else is config.AIRLINES.
"""
import copy
from typing import Dict, List

from app import config
from app.services.offer_key import encode_offer_key

_REFUND_REF_TEMPLATE = {
    "routeIndex": 0,
    "sourcePolicy": "AIRLINE_POLICY",
    "matchingPaxTypes": ["ALL"],
    "partialPax": True,
    "partialRoute": "NO",
    "periodAndFees": [
        {
            "refundable": False,
            "startPeriodType": "AFTER_PURCHASE",
            "endPeriodType": "BEFORE_DEPARTURE",
            "startNumHours": 0,
            "endNumHours": 0,
            "amount": 0.0,
            "currencyCode": config.CURRENCY,
            "isPercentage": False,
            "refundType": "REGULAR",
            "flightRefundFeeLevelType": "PER_ROUTE",
        }
    ],
    "otherInfo": {"cat16Info": "", "cat31Info": "", "cat33Info": ""},
}

_CHANGE_REF_TEMPLATE = {
    "routeIndex": 0,
    "sourcePolicy": "AIRLINE_POLICY",
    "matchingPaxTypes": ["ALL"],
    "partialPax": True,
    "partialRoute": "NO",
    "periodAndFees": [
        {
            "changeable": True,
            "startPeriodType": "AFTER_PURCHASE",
            "endPeriodType": "BEFORE_DEPARTURE",
            "startNumHours": 0,
            "endNumHours": 48,
            "amount": 25.0,
            "currencyCode": config.CURRENCY,
            "isPercentage": False,
            "feeValueType": "PER_ROUTE",
            "changeType": "REISSUANCE",
            "reasonType": "REGULAR",
        }
    ],
    "otherInfo": {"cat16Info": "", "cat31Info": "", "cat33Info": ""},
}


def pax_counts(adult: int, child: int, infant: int) -> Dict[str, int]:
    return {"ADT": adult or 0, "CHD": child or 0, "INF": infant or 0}


def fare_for(airline: str, pax_type: str) -> float:
    return round(config.AIRLINES[airline]["fare"] * config.PAX_FARE_MULTIPLIER[pax_type], 2)


def tax_for(airline: str, pax_type: str) -> float:
    return round(config.AIRLINES[airline]["tax"] * config.PAX_FARE_MULTIPLIER[pax_type], 2)


def build_segment(airline: str, ori: str, dest: str, dep_date: str) -> dict:
    info = config.AIRLINES[airline]
    return {
        "marketingCarrier": airline,
        "flightNumber": info["flight_number"],
        "operatingCarrier": airline,
        "operatingFlightNumber": info["flight_number"],
        "depAirport": ori,
        "arrAirport": dest,
        "depTerminal": "",
        "arrTerminal": "",
        "depTime": "{} {}".format(dep_date, info["dep_time"]),
        "arrTime": "{} {}".format(dep_date, info["arr_time"]),
        "codeShare": False,
        "aircraftCode": info["aircraft"],
        "fareBasis": "",
        "brandedFare": "",
        "duration": info["duration"],
        # Guideline field name (confirmed 2026-07-05); live wire shows "stopover".
        "stopovers": [],
    }


def build_fba_ancillary(airline: str) -> dict:
    fba = config.AIRLINES[airline]["fba_kg"]
    return {
        "ancillaryType": "FREECHECKEDBAGGAGE",
        "ancillaryCode": fba,
        "ancillaryPiece": 1 if fba > 0 else 0,
        "unitOfMeasurement": "WEIGHT",
        "desc": "{}kg".format(fba),
    }


def build_charges(airline: str, counts: Dict[str, int]) -> List[dict]:
    charges = []
    for pax_type in ("ADT", "CHD", "INF"):
        if counts.get(pax_type, 0) > 0:
            charges.append({"passengerType": pax_type, "chargeType": "FARE", "price": fare_for(airline, pax_type)})
            charges.append({"passengerType": pax_type, "chargeType": "TAX", "price": tax_for(airline, pax_type)})
    return charges


def build_offer_data(airlines: List[str], ori: str, dest: str, dep_date: str, counts: Dict[str, int]) -> dict:
    """Search-shaped data for the given airline subset; indices are local to this response."""
    offers, flights, segments, ancillaries = [], [], [], []
    cheapest = min(airlines, key=lambda a: config.AIRLINES[a]["fare"])
    for idx, airline in enumerate(airlines):
        free_refs = [
            {"ancillaryIndex": idx, "passengerType": pax_type, "segmentIndex": idx}
            for pax_type in ("ADT", "CHD")
            if counts.get(pax_type, 0) > 0
        ]
        offers.append({
            "offerKey": encode_offer_key(airline, ori, dest, dep_date),
            "routeIndex": 0,
            "product": list(config.PRODUCT),
            "issuanceTimeInMins": config.ISSUANCE_TIME_IN_MINS,
            "serviceFeePerPax": None,
            "cheapestOption": airline == cheapest,
            "flightRefs": [{"flightIndex": idx}],
            "charges": build_charges(airline, counts),
            "freeAncillaryRefs": free_refs,
        })
        flights.append({
            "segmentRefs": [{
                "segmentIndex": idx,
                "seatClass": config.SEAT_CLASS,
                "cabin": config.CABIN,
                "seatCount": config.SEAT_COUNT,
            }],
            "transferCount": 0,
            "transfer": [],
            "refundRefs": [copy.deepcopy(_REFUND_REF_TEMPLATE)],
            "changeRefs": [copy.deepcopy(_CHANGE_REF_TEMPLATE)],
        })
        segments.append(build_segment(airline, ori, dest, dep_date))
        ancillaries.append(build_fba_ancillary(airline))
    return {
        "currency": config.CURRENCY,
        "offers": offers,
        "penalties": [],
        "flights": flights,
        "segments": segments,
        "ancillaries": ancillaries,
    }
