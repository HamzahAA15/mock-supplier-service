"""CHECKEDBAGGAGE upsell generation: 3 options in +5 kg steps above the airline FBA."""
from typing import List

from app import config
from app.services.offer_key import encode_ancillary_key


def baggage_kg_options(airline: str) -> List[int]:
    fba = config.AIRLINES[airline]["fba_kg"]
    return [fba + step for step in config.ANCILLARY_OPTION_STEPS]


def baggage_price(kg: int) -> float:
    return round(kg * config.ANCILLARY_PRICE_PER_KG, 2)


def build_ancillary_offer(airline: str, ori: str, dest: str, kg: int) -> dict:
    flight_number = config.AIRLINES[airline]["flight_number"]
    return {
        "addAncillaryType": "CHECKEDBAGGAGE",
        "ancillaryKey": encode_ancillary_key(flight_number, kg),
        "ancillaryCode": kg,
        "ancillaryPiece": 1,
        "unitOfMeasurement": "WEIGHT",
        "desc": "{}kg".format(kg),
        "oriAirport": ori,
        "destAirport": dest,
        "transferAirport": "",
        "flightNumber": flight_number,
        "price": baggage_price(kg),
    }


def build_ancillary_offers(airline: str, ori: str, dest: str) -> List[dict]:
    return [build_ancillary_offer(airline, ori, dest, kg) for kg in baggage_kg_options(airline)]
