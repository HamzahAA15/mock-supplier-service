"""Runtime scenario rules — configurable negative outcomes per airline+route+endpoint.

Replaces the hard-coded BLOCKED_SECOND_BAGGAGE_ROUTES: the same blocked routes
are loaded as deletable SEED_RULES on startup/reset. In-memory only, same
singleton pattern as orders.py — rules are lost on restart and re-seeded.

A rule is an exact match on (endpoint, airline, origin, destination, flow) with
exactly one wildcard: the airline field may be the literal "*" (any airline).
Origin/destination/endpoint are always exact-match. No matching rule means the
endpoint behaves positively. See SCENARIO_RULES_DESIGN.md.
"""
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

# The 12 configurable endpoint ids. auth/token are excluded — no airline/route
# context to match a rule against.
ENDPOINTS = (
    # Core ticketing chain
    "search", "preOrderVerify", "ancillarySearch", "order", "pay", "orderDetail",
    # TSY BPI (second baggage)
    "tsy.secondBaggage", "tsy.order", "tsy.orderDetail",
    # Standardized BPI
    "std.baggageSearch", "std.order", "std.orderDetail",
)

# orderDetail endpoints accept an optional flow: "submitBooking" (pre-pay) /
# "issuance" (post-pay) / None (both). TSY/std have no pay step, so their
# orderDetail guards always run with flow="issuance" — submitBooking rules on
# them are accepted but never match (Decision 8 + plan decision 6).
FLOW_ENDPOINTS = ("orderDetail", "tsy.orderDetail", "std.orderDetail")
FLOWS = ("submitBooking", "issuance")

WILDCARD_AIRLINE = "*"

_AIRLINE_RE = re.compile(r"^[A-Z0-9]{2}$")
_AIRPORT_RE = re.compile(r"^[A-Z]{3}$")


def is_overridable(endpoint: str) -> bool:
    """TSY failure shapes are fixed (Decision 11) — no code/msg overrides."""
    return not endpoint.startswith("tsy.")


# Preset catalog. `kind` drives rendering in scenario_responses:
#   empty_result    -> schema-valid success with an empty result set
#   business_error  -> the contract's error envelope (code/msg overridable)
#   http_500        -> TSY hard failure (HTTP 500, string-status envelope)
#   status_override -> orderDetail succeeds but reports the preset's `status`
# Default codes/msgs are literals on purpose (services layer must not import
# routers — avoids cycles); comments point at the constants they mirror.
PRESETS = {
    "search": {
        # A supplier with no inventory is not an error: the airline is simply
        # filtered out of the results (design section 5).
        "no_results": {"label": "No results (airline filtered out)", "kind": "empty_result"},
    },
    "preOrderVerify": {
        "verify_failed": {"label": "Verify failed (no data)", "kind": "business_error",
                          "default_code": 204, "default_msg": "No data"},  # codes.NO_DATA
    },
    "ancillarySearch": {
        "no_results": {"label": "No ancillary offers", "kind": "empty_result"},
        "ancillary_expired": {"label": "Ancillary expired", "kind": "business_error",
                              "default_code": 553,  # codes.ANCILLARY_EXPIRED
                              "default_msg": "The ancillary offer has expired"},
    },
    "order": {
        "order_failed": {"label": "Order creation failed", "kind": "business_error",
                         "default_code": 500,  # mock-defined (no contract constant)
                         "default_msg": "Order creation failed"},
    },
    "pay": {
        "payment_declined": {"label": "Payment declined", "kind": "business_error",
                             "default_code": 501,  # mock-defined (no contract constant)
                             "default_msg": "Payment declined"},
        "duplicate_payment": {"label": "Duplicate payment", "kind": "business_error",
                              "default_code": 748,  # codes.DUPLICATE_PAYMENT
                              "default_msg": "Duplicate payment"},
    },
    "orderDetail": {
        "order_not_found": {"label": "Order not found", "kind": "business_error",
                            "default_code": 148,  # codes.ORDER_NOT_FOUND
                            "default_msg": "The order does not exist"},
        "unpaid_missing_data": {"label": "Unpaid order data missing", "kind": "business_error",
                                "default_code": 204,  # codes.NO_DATA
                                "default_msg": "No data"},
        # Mock-chosen status vocabulary — the core contract defines none for
        # these negative states (plan decision 5).
        "stuck_issuing": {"label": "Stuck in ISSUING", "kind": "status_override",
                          "status": "ISSUING"},
        "issue_failed": {"label": "Issuance failed", "kind": "status_override",
                         "status": "ISSUE_FAILED"},
    },
    "tsy.secondBaggage": {
        "route_blocked": {"label": "Route blocked (HTTP 500)", "kind": "http_500"},
    },
    "tsy.order": {
        "route_blocked": {"label": "Route blocked (HTTP 500)", "kind": "http_500"},  # seed
        # Mirrors bpi.py _ORDER_FAILURE (HTTP 200, string-status envelope).
        "order_failed": {"label": "Order failed", "kind": "business_error",
                         "default_msg": "invalid productItemId"},
    },
    "tsy.orderDetail": {
        # Same body as the genuine unknown-auxiliaryOrderNo path in bpi.py.
        "order_not_found": {"label": "Order not found", "kind": "business_error",
                            "default_msg": "order not found"},
        # TSY only documents PURCHASED; PROCESSING/FAILED are mock-chosen.
        "stuck_issuing": {"label": "Stuck in PROCESSING", "kind": "status_override",
                          "status": "PROCESSING"},
        "issue_failed": {"label": "Issuance failed", "kind": "status_override",
                         "status": "FAILED"},
    },
    "std.baggageSearch": {
        # Mirror standardized_bpi.py CODE_NO_QUOTATION / CODE_SALE_PROHIBITED.
        "no_quotation": {"label": "No quotation (555)", "kind": "business_error",  # seed
                         "default_code": 555,
                         "default_msg": "no ancillary quotation for the current offer"},
        "sale_prohibited": {"label": "Sale prohibited (5001)", "kind": "business_error",
                            "default_code": 5001,
                            "default_msg": "prohibition of sale before or after departure"},
    },
    "std.order": {
        "no_quotation": {"label": "No quotation (555)", "kind": "business_error",  # seed
                         "default_code": 555,
                         "default_msg": "no ancillary quotation for the current offer"},
        "invalid_order": {"label": "Invalid order (400)", "kind": "business_error",
                          "default_code": 400,  # standardized_bpi.py CODE_INVALID_ORDER_NO
                          "default_msg": "invalid ancillary order number"},
        "sale_prohibited": {"label": "Sale prohibited (5001)", "kind": "business_error",
                            "default_code": 5001,
                            "default_msg": "prohibition of sale before or after departure"},
    },
    "std.orderDetail": {
        "order_not_found": {"label": "Order not found (400)", "kind": "business_error",
                            "default_code": 400,
                            "default_msg": "invalid ancillary order number"},
        "stuck_issuing": {"label": "Stuck in ISSUING", "kind": "status_override",
                          "status": "ISSUING"},
        "issue_failed": {"label": "Issuance failed", "kind": "status_override",
                         "status": "ISSUE_FAILED"},
    },
}


def preset_def(rule: Dict[str, Any]) -> Dict[str, Any]:
    """The catalog entry a rule points at (kind / defaults / status)."""
    return PRESETS[rule["endpoint"]][rule["preset"]]


def validate_rule(payload: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate/normalize a raw rule dict. Returns (rule, errors); rule is None
    whenever errors is non-empty. Shape-only validation: unknown-but-well-formed
    airline/airport codes are accepted and simply never match (design section 4).
    """
    errors = []
    if not isinstance(payload, dict):
        return None, ["rule must be a JSON object"]

    endpoint = payload.get("endpoint")
    if endpoint not in ENDPOINTS:
        errors.append("endpoint must be one of: {}".format(", ".join(ENDPOINTS)))

    airline = payload.get("airline")
    if (not isinstance(airline, str)
            or not (airline == WILDCARD_AIRLINE or _AIRLINE_RE.match(airline))):
        errors.append('airline must match ^[A-Z0-9]{2}$ or be "*" (any airline)')

    origin = payload.get("origin")
    if not isinstance(origin, str) or not _AIRPORT_RE.match(origin):
        errors.append("origin must match ^[A-Z]{3}$")

    destination = payload.get("destination")
    if not isinstance(destination, str) or not _AIRPORT_RE.match(destination):
        errors.append("destination must match ^[A-Z]{3}$")

    flow = payload.get("flow")
    if flow == "":
        flow = None  # "" from the UI means "both"; any other falsy value is invalid
    if flow is not None:
        if flow not in FLOWS:  # also rejects non-strings (0, false, ...)
            errors.append("flow must be one of: {}".format(", ".join(FLOWS)))
        elif endpoint not in FLOW_ENDPOINTS:
            errors.append("flow is only allowed on orderDetail endpoints: {}".format(
                ", ".join(FLOW_ENDPOINTS)))

    preset = payload.get("preset")
    preset_entry = None
    if preset in PRESETS.get(endpoint, {}):
        preset_entry = PRESETS[endpoint][preset]
    else:
        errors.append("preset must be one of: {}".format(
            ", ".join(sorted(PRESETS.get(endpoint, {})))))

    code = payload.get("code")
    msg = payload.get("msg")
    if code == "":
        code = None
    if msg == "":
        msg = None
    if code is not None or msg is not None:
        if endpoint in ENDPOINTS and not is_overridable(endpoint):
            # Decision 11: TSY failure shapes are fixed.
            errors.append("code/msg overrides are not allowed on tsy.* endpoints")
        elif preset_entry is not None and preset_entry["kind"] != "business_error":
            errors.append("code/msg overrides are only allowed on business_error presets")
    if code is not None:
        # Only an int or a string of digits — no silent coercion of floats
        # (5.7 -> 5) or bools (isinstance(True, int) is True in Python).
        if isinstance(code, int) and not isinstance(code, bool):
            pass
        elif isinstance(code, str) and code.isdigit():
            code = int(code)
        else:
            errors.append("code override must be an integer")
    if msg is not None and not isinstance(msg, str):
        errors.append("msg override must be a string")

    if errors:
        return None, errors
    return {
        "endpoint": endpoint,
        "airline": airline,
        "origin": origin,
        "destination": destination,
        "flow": flow,
        "preset": preset,
        "code": code,
        "msg": msg,
    }, []


def _key(rule: Dict[str, Any]) -> Tuple:
    return (rule["endpoint"], rule["airline"], rule["origin"],
            rule["destination"], rule["flow"])


def _rule_id(key: Tuple) -> str:
    """Deterministic id derived from the match key (design section 7)."""
    raw = "|".join("" if part is None else str(part) for part in key)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class RuleStore:
    """In-memory rule registry, same singleton pattern as orders.py."""

    def __init__(self):
        self._rules: Dict[Tuple, dict] = {}

    def put(self, rule: Dict[str, Any], seed: bool = False) -> dict:
        """Upsert — silent replace on the same match key (editing = re-adding)."""
        key = _key(rule)
        stored = dict(rule, seed=seed, rule_id=_rule_id(key))
        self._rules[key] = stored
        return dict(stored)

    def list(self) -> List[dict]:
        return [dict(r) for r in sorted(
            self._rules.values(),
            key=lambda r: (r["endpoint"], r["airline"], r["origin"],
                           r["destination"], r["flow"] or ""),
        )]

    def delete(self, rule_id: str) -> bool:
        for key, rule in self._rules.items():
            if rule["rule_id"] == rule_id:
                del self._rules[key]
                return True
        return False

    def check(self, endpoint: str, airline: Optional[str], origin: Optional[str],
              destination: Optional[str], flow: Optional[str] = None) -> Optional[dict]:
        """Most-specific match wins: exact airline before the "*" wildcard,
        exact flow before flow=None — i.e. (airline, "*") x (flow, None)."""
        for candidate_airline in (airline, WILDCARD_AIRLINE):
            for candidate_flow in (flow, None):
                rule = self._rules.get(
                    (endpoint, candidate_airline, origin, destination, candidate_flow))
                if rule is not None:
                    return dict(rule)
        return None

    def clear(self):
        self._rules.clear()

    def reset(self):
        """Wipe everything and reload the seeds (startup / POST /admin/rules/reset)."""
        self.clear()
        for rule in SEED_RULES:
            self.put(dict(rule), seed=True)


# Seeds reproduce the deleted BLOCKED_SECOND_BAGGAGE_ROUTES exactly: SIN->KUL and
# SIN->CGK are blocked for ANY airline (wildcard "*") on TSY order creation and
# on Standardized BPI search + order — 6 rules. TSY search is deliberately NOT
# seeded: it succeeds on blocked routes today (order-time blocking only).
SEED_RULES = tuple(
    {"endpoint": endpoint, "airline": WILDCARD_AIRLINE, "origin": origin,
     "destination": destination, "flow": None, "preset": preset,
     "code": None, "msg": None}
    for endpoint, preset in (
        ("tsy.order", "route_blocked"),
        ("std.baggageSearch", "no_quotation"),
        ("std.order", "no_quotation"),
    )
    for origin, destination in (("SIN", "KUL"), ("SIN", "CGK"))
)

rules = RuleStore()
rules.reset()
