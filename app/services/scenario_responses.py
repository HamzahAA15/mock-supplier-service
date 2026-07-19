"""Renders scenario-rule failures through each contract's envelope.

Kept separate from scenario_rules (pure matching) so the store has no rendering
concerns. Shapes are byte-identical to the hard-coded failures they replace:
TSY string-status envelope, standardized {code,msg,data}, core codes.py
envelope. See SCENARIO_RULES_DESIGN.md section 6.
"""
from typing import Any, Dict, Tuple

from app import config
from app.services import codes
from app.services.scenario_rules import preset_def


def empty_search_data() -> Dict[str, Any]:
    """Search-shaped success data with zero offers. Hand-built on purpose:
    inventory.build_offer_data([]) crashes (min() over an empty airline list)."""
    return {
        "currency": config.CURRENCY,
        "offers": [],
        "penalties": [],
        "flights": [],
        "segments": [],
        "ancillaries": [],
    }


def render(rule: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """(body, http_status) for empty_result / business_error / http_500 presets.

    status_override presets never come here — routers build the normal success
    payload and pass it through apply_status_override instead.
    """
    endpoint = rule["endpoint"]
    preset = preset_def(rule)
    kind = preset["kind"]

    if endpoint.startswith("tsy."):
        # TSY: fixed string-status shapes, no overrides (Decision 11).
        if kind == "http_500":
            # Same message the deleted is_route_blocked path produced ("SIN-KUL").
            msg = "second baggage not available for route {}-{}".format(
                rule["origin"], rule["destination"])
            body = {"status": "1", "msg": msg, "auxiliaryOrderNo": None}
            if endpoint == "tsy.secondBaggage":
                body["products"] = None  # search-shaped failure envelope
            return body, 500
        if endpoint == "tsy.orderDetail":
            # Same body as the genuine unknown-order path in routers/bpi.py.
            return {"status": "1", "msg": preset["default_msg"], "data": None}, 200
        # tsy.order order_failed — mirrors routers/bpi.py _ORDER_FAILURE.
        return {"auxiliaryOrderNo": None, "msg": preset["default_msg"], "status": "1"}, 200

    code = rule.get("code")
    msg = rule.get("msg")
    if code is None:
        code = preset.get("default_code")
    if msg is None:
        msg = preset.get("default_msg")

    if endpoint.startswith("std."):
        # Standardized envelope is always HTTP 200 (never 5xx).
        return {"code": code, "msg": msg, "data": None}, 200

    # Core ticketing: always HTTP 200, envelope helpers from codes.py.
    if kind == "empty_result":
        if endpoint == "ancillarySearch":
            return codes.success({"currency": config.CURRENCY, "ancillaryOffers": []}), 200
        return codes.success(empty_search_data()), 200  # search
    return codes.error(code, msg), 200


def apply_status_override(rule: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Mutate a successful orderDetail payload to report the preset's status."""
    status = preset_def(rule)["status"]
    if rule["endpoint"] == "orderDetail":
        data["orderInfo"]["status"] = status
        if status != "ISSUED":
            # Tickets only exist once ISSUED — blank them for stuck/failed states.
            for pnr in data.get("pnrs") or []:
                for pax in pnr.get("passengers") or []:
                    pax["ticketNumber"] = ""
    else:
        # tsy.orderDetail / std.orderDetail both report data["orderStatus"].
        data["orderStatus"] = status
    return data
