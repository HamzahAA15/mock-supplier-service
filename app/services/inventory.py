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

# ---------------------------------------------------------------------------
# MODIFIED_SERVICE_FEE — 70% cap guideline (Lark doc, Jul 17 2026).
#
# The total charge to the user (airline penalty + serviceFeePerPax) must never
# exceed 70% of the ADT total fare (FARE + TAX). Since penalty amounts vary per
# period and per action, the HIGHEST penalty across all refund & reschedule
# periods is the benchmark:
#
#   maxServiceFeePerPax = 70% x ADT total fare - highestPenalty
#
# Profiles are keyed by the search-endpoint scenario preset (offer_override
# kind) and expressed as percents of the ADT total fare so they hold for any
# airline regardless of its fare:
#
#   msf_valid           penalty 50% + fee 20% = 70%  (at the cap — valid)
#   msf_cap_violation   penalty 50% + fee 30% = 80%  (> 70% — Traveloka rejects)
#   basic_high_penalty  penalty 75%, no fee          (> 70% — BASIC only; the
#                       supplier is not allowed to use MODIFIED_SERVICE_FEE)
#
# Two periods per action mirror the guideline sample (early period cheaper,
# late period = the profile's headline percent).
# ---------------------------------------------------------------------------
MSF_TAG = "MODIFIED_SERVICE_FEE"

MSF_PROFILES = {
    "msf_valid": {
        "refund_pcts": (0.25, 0.50),
        "change_pcts": (0.15, 0.30),
        # "cap" = the maximum allowed fee: 70% x total - highest penalty.
        "fee_pct": "cap",
    },
    "msf_cap_violation": {
        "refund_pcts": (0.25, 0.50),
        "change_pcts": (0.15, 0.30),
        "fee_pct": 0.30,  # 50% highest penalty + 30% fee = 80% > 70%
    },
    "basic_high_penalty": {
        "refund_pcts": (0.50, 0.75),
        "change_pcts": (0.30, 0.40),
        "fee_pct": None,  # BASIC only — serviceFeePerPax stays null
    },
}


def adt_total_fare(airline: str) -> float:
    """ADT total fare (FARE + TAX) — the base of the 70% cap."""
    return round(fare_for(airline, "ADT") + tax_for(airline, "ADT"), 2)


def _msf_amounts(airline: str, pcts) -> List[float]:
    total = adt_total_fare(airline)
    return [round(pct * total, 2) for pct in pcts]


def msf_highest_penalty(airline: str, preset: str) -> float:
    """max(all refund & reschedule penalty amounts across all periods)."""
    profile = MSF_PROFILES[preset]
    return max(_msf_amounts(airline, profile["refund_pcts"])
               + _msf_amounts(airline, profile["change_pcts"]))


def msf_fee_per_pax(airline: str, preset: str):
    """serviceFeePerPax for the profile, or None (BASIC-only profile)."""
    fee_pct = MSF_PROFILES[preset]["fee_pct"]
    if fee_pct is None:
        return None
    total = adt_total_fare(airline)
    cap = round(0.70 * total, 2)
    if fee_pct == "cap":
        # Exactly the maximum allowed — penalty + fee lands on the cap, never over.
        return round(cap - msf_highest_penalty(airline, preset), 2)
    return round(fee_pct * total, 2)


def _msf_period_pair(amounts: List[float], fee_fields: dict) -> List[dict]:
    """Two guideline-style periods: >48h before departure (cheaper), then <=48h."""
    periods = []
    for amount, (start_type, start_h, end_h) in zip(
            amounts, (("AFTER_PURCHASE", 0, 48), ("BEFORE_DEPARTURE", 48, 0))):
        period = {
            "startPeriodType": start_type,
            "endPeriodType": "BEFORE_DEPARTURE",
            "startNumHours": start_h,
            "endNumHours": end_h,
            "amount": amount,
            "currencyCode": config.CURRENCY,
            "isPercentage": False,
        }
        period.update(fee_fields)
        periods.append(period)
    return periods


def _msf_refund_ref(airline: str, preset: str) -> dict:
    ref = copy.deepcopy(_REFUND_REF_TEMPLATE)
    ref["periodAndFees"] = _msf_period_pair(
        _msf_amounts(airline, MSF_PROFILES[preset]["refund_pcts"]),
        {"refundable": True, "refundType": "REGULAR",
         "flightRefundFeeLevelType": "PER_ROUTE"},
    )
    return ref


def _msf_change_ref(airline: str, preset: str) -> dict:
    ref = copy.deepcopy(_CHANGE_REF_TEMPLATE)
    ref["periodAndFees"] = _msf_period_pair(
        _msf_amounts(airline, MSF_PROFILES[preset]["change_pcts"]),
        {"changeable": True, "feeValueType": "PER_ROUTE",
         "changeType": "REISSUANCE", "reasonType": "REGULAR"},
    )
    return ref


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


def msf_offer_fields(airline: str, preset: str, msf_requested: bool = True) -> dict:
    """The offer-level product/serviceFeePerPax pair for an MSF profile.

    Product tag rule (guideline): MODIFIED_SERVICE_FEE is never standalone —
    always BASIC + MODIFIED_SERVICE_FEE, and only when the /search request
    asked for it (msf_requested). Otherwise the offer degrades to BASIC with a
    null fee; the penalty profile still applies (it is airline policy, not a
    product attribute).
    """
    fee = msf_fee_per_pax(airline, preset) if msf_requested else None
    product = list(config.PRODUCT)
    if fee is not None:
        product.append(MSF_TAG)
    return {"product": product, "serviceFeePerPax": fee}


def build_offer_data(airlines: List[str], ori: str, dest: str, dep_date: str,
                     counts: Dict[str, int], msf_presets: Dict[str, str] = None,
                     msf_requested: bool = True) -> dict:
    """Search-shaped data for the given airline subset; indices are local to this response.

    msf_presets maps airline -> MSF_PROFILES key (from an offer_override
    scenario rule); msf_requested says whether the /search request's product
    array included MODIFIED_SERVICE_FEE (downstream endpoints pass the default
    True — their requests carry no product array).
    """
    msf_presets = msf_presets or {}
    offers, flights, segments, ancillaries = [], [], [], []
    cheapest = min(airlines, key=lambda a: config.AIRLINES[a]["fare"])
    for idx, airline in enumerate(airlines):
        free_refs = [
            {"ancillaryIndex": idx, "passengerType": pax_type, "segmentIndex": idx}
            for pax_type in ("ADT", "CHD")
            if counts.get(pax_type, 0) > 0
        ]
        preset = msf_presets.get(airline)
        offer = {
            "offerKey": encode_offer_key(airline, ori, dest, dep_date),
            "routeIndex": 0,
            "product": list(config.PRODUCT),
            "issuanceTimeInMins": config.ISSUANCE_TIME_IN_MINS,
            "serviceFeePerPax": None,
            "cheapestOption": airline == cheapest,
            "flightRefs": [{"flightIndex": idx}],
            "charges": build_charges(airline, counts),
            "freeAncillaryRefs": free_refs,
        }
        if preset:
            offer.update(msf_offer_fields(airline, preset, msf_requested))
        offers.append(offer)
        flights.append({
            "segmentRefs": [{
                "segmentIndex": idx,
                "seatClass": config.SEAT_CLASS,
                "cabin": config.CABIN,
                "seatCount": config.SEAT_COUNT,
            }],
            "transferCount": 0,
            "transfer": [],
            "refundRefs": [_msf_refund_ref(airline, preset) if preset
                           else copy.deepcopy(_REFUND_REF_TEMPLATE)],
            "changeRefs": [_msf_change_ref(airline, preset) if preset
                           else copy.deepcopy(_CHANGE_REF_TEMPLATE)],
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
