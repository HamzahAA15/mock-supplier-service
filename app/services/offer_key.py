"""Deterministic, stateless offerKey / ancillaryKey codecs (DESIGN.md section 6).

offerKey     = base64url("<AIRLINE>|<ORI>|<DEST>|<DEPDATE>|BASIC")
ancillaryKey = "<adt>_<chd>_<inf>$<flightNumber>$PA<kg>"
"""
import base64
import binascii
import re
from typing import Optional

from app import config

_OFFER_KEY_RE = re.compile(r"^([A-Z0-9]{2})\|([A-Z]{3})\|([A-Z]{3})\|(\d{4}-\d{2}-\d{2})\|BASIC$")
_ANCILLARY_KEY_RE = re.compile(r"^(\d+)_(\d+)_(\d+)\$([A-Z0-9]+)\$PA(\d+)$")


def encode_offer_key(airline: str, ori: str, dest: str, dep_date: str) -> str:
    raw = "{}|{}|{}|{}|BASIC".format(airline, ori, dest, dep_date)
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii").rstrip("=")


def decode_offer_key(offer_key: str) -> Optional[dict]:
    """Return {airline, ori, dest, dep_date} or None if undecodable/unknown."""
    if not offer_key:
        return None
    try:
        padded = offer_key + "=" * (-len(offer_key) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    match = _OFFER_KEY_RE.match(raw)
    if not match:
        return None
    airline, ori, dest, dep_date = match.groups()
    if airline not in config.AIRLINES:
        return None
    return {"airline": airline, "ori": ori, "dest": dest, "dep_date": dep_date}


def encode_ancillary_key(flight_number: str, kg: int) -> str:
    # All passenger types share the same baggage arrangement (confirmed 2026-07-05),
    # so the pax-count prefix is fixed at 1_0_0 as in the live samples.
    return "1_0_0${}$PA{}".format(flight_number, kg)


def decode_ancillary_key(ancillary_key: str) -> Optional[dict]:
    """Return {flight_number, kg} or None if unparseable/unknown flight."""
    if not ancillary_key:
        return None
    match = _ANCILLARY_KEY_RE.match(ancillary_key)
    if not match:
        return None
    _, _, _, flight_number, kg = match.groups()
    if flight_number not in config.FLIGHT_TO_AIRLINE:
        return None
    return {"flight_number": flight_number, "kg": int(kg)}
