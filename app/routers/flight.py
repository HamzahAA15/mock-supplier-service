import re
from datetime import date, datetime

from fastapi import APIRouter

from app import config
from app.models.ancillary import AncillarySearchRequest
from app.models.order import OrderRequest
from app.models.order_detail import OrderDetailRequest
from app.models.pay import PayRequest
from app.models.search import SearchRequest
from app.models.verify import VerifyRequest
from app.services import ancillary as ancillary_svc
from app.services import codes, inventory, payments, scenario_responses
from app.services.offer_key import decode_ancillary_key, decode_offer_key
from app.services.orders import store
from app.services.scenario_rules import preset_def, rules

router = APIRouter(prefix="/flight")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _passenger_name(passenger: dict) -> str:
    return "{}/{}".format(passenger.get("lastName", ""), passenger.get("firstName", ""))


def _light_segment(offer: dict) -> dict:
    return {
        "depAirport": offer["ori"],
        "arrAirport": offer["dest"],
        "flightNumber": config.AIRLINES[offer["airline"]]["flight_number"],
    }


def _msf_preset_for(airline: str, ori: str, dest: str):
    """The MSF profile key if a search-endpoint offer_override rule matches,
    else None. Downstream endpoints (preOrderVerify/order/orderDetail) re-derive
    the profile from the same rule so product/serviceFeePerPax stay consistent
    across all adjusted APIs (guideline: the product identifier must be returned
    in search, preOrderVerify, order & orderDetail)."""
    rule = rules.check("search", airline, ori, dest)
    if rule and preset_def(rule)["kind"] == "offer_override":
        return rule["preset"]
    return None


@router.post("/search/v3")
def search(req: SearchRequest):
    if not req.routes:
        return codes.error(codes.ROUTE_EMPTY)
    route = req.routes[0]
    ori, dest = route.get("oriAirport"), route.get("destAirport")
    if not ori or not dest:
        return codes.error(codes.AIRPORT_EMPTY)
    dep_date = route.get("depDate")
    if not dep_date:
        return codes.error(codes.DEP_DATE_EMPTY)
    try:
        parsed = datetime.strptime(dep_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return codes.error(codes.NO_DATA)
    if parsed < date.today():
        return codes.error(codes.DEP_DATE_BACKDATE)
    if not req.adult_number or req.adult_number < 1:
        return codes.error(codes.NO_ADULT)

    airlines = list(config.AIRLINE_ORDER)
    if req.airline_ids:
        airlines = [a for a in airlines if a in req.airline_ids]
        if not airlines:
            return codes.error(codes.NO_DATA)

    # Scenario guard: an empty_result search rule FILTERS the airline out of the
    # results (a supplier with no inventory is not an error) — it never fails
    # the search. An offer_override rule KEEPS the airline and shapes its offer
    # per the MSF profile instead (70% cap guideline).
    kept, msf_presets = [], {}
    for a in airlines:
        rule = rules.check("search", a, ori, dest)
        if rule is None:
            kept.append(a)
        elif preset_def(rule)["kind"] == "offer_override":
            kept.append(a)
            msf_presets[a] = rule["preset"]
    if not kept:
        # All airlines filtered -> empty success (build_offer_data([]) crashes).
        return codes.success(scenario_responses.empty_search_data())

    # Product tag rule (guideline): MSF offers are only returned when the
    # request's product array includes MODIFIED_SERVICE_FEE — never standalone.
    msf_requested = bool(req.product) and inventory.MSF_TAG in req.product
    counts = inventory.pax_counts(req.adult_number, req.child_number, req.infant_number)
    return codes.success(inventory.build_offer_data(
        kept, ori, dest, dep_date, counts,
        msf_presets=msf_presets, msf_requested=msf_requested))


@router.post("/preOrderVerify/v3")
def pre_order_verify(req: VerifyRequest):
    if not req.offer_key:
        return codes.error(codes.OFFER_KEY_EMPTY)
    offer = decode_offer_key(req.offer_key)
    if offer is None:
        return codes.error(codes.NO_DATA)
    # Scenario guard: keyed on the decoded offerKey.
    rule = rules.check("preOrderVerify", offer["airline"], offer["ori"], offer["dest"])
    if rule:
        body, _ = scenario_responses.render(rule)
        return body
    # Pax counts are not encoded in the offerKey; verify prices the adult view.
    preset = _msf_preset_for(offer["airline"], offer["ori"], offer["dest"])
    data = inventory.build_offer_data(
        [offer["airline"]], offer["ori"], offer["dest"], offer["dep_date"], {"ADT": 1},
        msf_presets={offer["airline"]: preset} if preset else None,
    )
    return codes.success(data)


@router.post("/ancillary/search/v3")
def ancillary_search(req: AncillarySearchRequest):
    if not req.offer_key:
        return codes.error(codes.OFFER_KEY_EMPTY)
    offer = decode_offer_key(req.offer_key)
    if offer is None:
        return codes.error(codes.NO_DATA)
    # Scenario guard: no_results renders an empty (schema-valid) offer list,
    # ancillary_expired renders the 553 envelope.
    rule = rules.check("ancillarySearch", offer["airline"], offer["ori"], offer["dest"])
    if rule:
        body, _ = scenario_responses.render(rule)
        return body
    return codes.success({
        "currency": config.CURRENCY,
        "ancillaryOffers": ancillary_svc.build_ancillary_offers(
            offer["airline"], offer["ori"], offer["dest"]
        ),
    })


@router.post("/order/v3")
def order(req: OrderRequest):
    if not req.offer_key:
        return codes.error(codes.OFFER_KEY_EMPTY)
    offer = decode_offer_key(req.offer_key)
    if offer is None:
        return codes.error(codes.NO_DATA)
    offer["offerKey"] = req.offer_key

    # Scenario guard: fires before the order is created (no store.create below).
    rule = rules.check("order", offer["airline"], offer["ori"], offer["dest"])
    if rule:
        body, _ = scenario_responses.render(rule)
        return body

    passengers = req.passengers or []
    if not any(p.get("passengerType") == "ADT" for p in passengers):
        return codes.error(codes.NO_ADULT)

    contacts = req.contacts or []
    if not contacts or any(not c.get("email") for c in contacts):
        return codes.error(codes.EMAIL_EMPTY)
    if any(not _EMAIL_RE.match(c["email"]) for c in contacts):
        return codes.error(codes.EMAIL_BAD_FORMAT)
    if any(not c.get("phone") for c in contacts):
        return codes.error(codes.PHONE_EMPTY)

    airline = offer["airline"]
    valid_kg = set(ancillary_svc.baggage_kg_options(airline))
    flight_number = config.AIRLINES[airline]["flight_number"]

    added_ancillary = []
    ancillary_total = 0.0
    for entry in req.ancillary_key_lists or []:
        pax_index = entry.passenger_index
        if pax_index is None or not (0 <= pax_index < len(passengers)):
            return codes.error(codes.ANCILLARY_EXPIRED)
        offers_for_pax = []
        for key in entry.ancillary_keys or []:
            decoded = decode_ancillary_key(key)
            if (decoded is None
                    or decoded["flight_number"] != flight_number
                    or decoded["kg"] not in valid_kg):
                return codes.error(codes.ANCILLARY_EXPIRED)
            item = ancillary_svc.build_ancillary_offer(
                airline, offer["ori"], offer["dest"], decoded["kg"]
            )
            offers_for_pax.append(item)
            ancillary_total += item["price"]
        if offers_for_pax:
            added_ancillary.append({
                "passengerIndex": pax_index,
                "passengerName": _passenger_name(passengers[pax_index]),
                "ancillaryOffers": offers_for_pax,
            })

    counts = {"ADT": 0, "CHD": 0, "INF": 0}
    for p in passengers:
        pax_type = p.get("passengerType")
        if pax_type in counts:
            counts[pax_type] += 1

    fare_total = sum(
        (inventory.fare_for(airline, t) + inventory.tax_for(airline, t)) * n
        for t, n in counts.items()
    )
    total = round(fare_total + ancillary_total, 2)

    stored = store.create(offer, passengers, contacts, added_ancillary, total)

    preset = _msf_preset_for(airline, offer["ori"], offer["dest"])
    data = {
        "currency": config.CURRENCY,
        "total": total,
        "orderId": stored["orderId"],
        "expireInMinutes": config.ORDER_EXPIRE_IN_MINUTES,
        "product": list(config.PRODUCT),
        "issuanceTimeInMins": config.ISSUANCE_TIME_IN_MINS,
        "serviceFeePerPax": None,
        "addedAncillary": added_ancillary,
    }
    if preset:
        data.update(inventory.msf_offer_fields(airline, preset))
    data.update(inventory.build_offer_data(
        [airline], offer["ori"], offer["dest"], offer["dep_date"], counts,
        msf_presets={airline: preset} if preset else None,
    ))
    return codes.success(data)


@router.post("/pay/v3")
def pay(req: PayRequest):
    if not req.order_id:
        return codes.error(codes.ORDER_ID_EMPTY)
    stored = store.get(req.order_id)
    if stored is None:
        return codes.error(codes.ORDER_NOT_FOUND)
    if stored["status"] != "UNPAID":
        return codes.error(codes.DUPLICATE_PAYMENT)
    # Scenario guard: after the genuine 148/748 paths, keyed on the stored
    # order's offer (the pay RQ only carries the orderId).
    offer = stored["offer"]
    rule = rules.check("pay", offer["airline"], offer["ori"], offer["dest"])
    if rule:
        body, _ = scenario_responses.render(rule)
        return body
    # Mocked gateway response ("PAY API adjustment" wiki): for ANTOM/YEEPAY the
    # accountNumber is the RECEIVER account of the wallet-to-wallet transaction;
    # for BPA it echoes the payer account from the request.
    receipt = payments.charge(stored, req.pay_type, req.account_number)
    store.pay(stored, receipt["accountNumber"], payments.normalize_pay_type(req.pay_type))
    return codes.success(receipt)


def _build_order_detail_data(stored: dict) -> dict:
    """The orderDetail success payload for a stored order. Extracted so
    status_override scenario rules can reuse it (build, then patch status)."""
    offer = stored["offer"]
    airline = offer["airline"]
    light_segments = [_light_segment(offer)]
    counts = {"ADT": 0, "CHD": 0, "INF": 0}
    for p in stored["passengers"]:
        if p.get("passengerType") in counts:
            counts[p["passengerType"]] += 1
    preset = _msf_preset_for(airline, offer["ori"], offer["dest"])
    full = inventory.build_offer_data(
        [airline], offer["ori"], offer["dest"], offer["dep_date"], counts,
        msf_presets={airline: preset} if preset else None,
    )
    # Top-level segments are FULL objects (matches the live supplier); the nested
    # pnrs[].segments / ancillaryList[].segments stay light (dep/arr/flightNumber only).
    full_segments = full["segments"]
    flight_refs = [
        {"flightIndex": ref["flightIndex"], "fareType": "PUBLISH", "brandedFare": ""}
        for ref in full["offers"][0]["flightRefs"]
    ]

    ancillary_list = []
    for entry in stored["addedAncillary"]:
        pax_idx = entry.get("passengerIndex")
        pax_card = ""
        if pax_idx is not None and 0 <= pax_idx < len(stored["passengers"]):
            pax_card = stored["passengers"][pax_idx].get("cardNumber", "") or ""
        for item in entry["ancillaryOffers"]:
            ancillary_list.append({
                "ancillaryType": item["addAncillaryType"],
                "ancillaryCode": item["ancillaryCode"],
                "ancillaryPiece": item["ancillaryPiece"],
                "unitOfMeasurement": item["unitOfMeasurement"],
                "desc": item["desc"],
                "passengerName": entry["passengerName"],
                "cardNumber": pax_card,
                "segments": light_segments,
            })

    order_info_msf = (inventory.msf_offer_fields(airline, preset) if preset
                      else {"product": list(config.PRODUCT), "serviceFeePerPax": None})
    data = {
        "orderInfo": {
            "orderId": stored["orderId"],
            "product": order_info_msf["product"],
            "issuanceTimeInMins": config.ISSUANCE_TIME_IN_MINS,
            "serviceFeePerPax": order_info_msf["serviceFeePerPax"],
            "status": stored["status"],
            "createdTime": stored["createdTime"],
            "updateTime": stored["updateTime"],
            "expiredTime": stored["expiredTime"],
            "payTime": stored["payTime"],
            "amount": "{:.2f}".format(stored["total"]),
            "currency": config.CURRENCY,
            "accountNumber": stored["accountNumber"],
        },
        "pnrs": [
            {
                "pnr": stored["pnr"],
                "providerPnr": "",
                "email": stored["contacts"][0].get("email", "") if stored["contacts"] else "",
                "segments": light_segments,
                "passengers": [
                    {
                        "passenger": _passenger_name(p),
                        "ticketNumber": stored["ticketNumbers"].get(i, ""),
                        "cardNumber": p.get("cardNumber"),
                    }
                    for i, p in enumerate(stored["passengers"])
                ],
            }
        ],
        "ancillaryList": ancillary_list,
        "penalties": [],
        "ancillaries": [inventory.build_fba_ancillary(airline)],
        "flightRefs": flight_refs,
        "flights": full["flights"],
        "passengerList": stored["passengers"],
        "contactList": stored["contacts"],
        "segments": full_segments,
    }
    return data


@router.post("/orderDetail/v3")
def order_detail(req: OrderDetailRequest):
    if not req.order_id:
        return codes.error(codes.ORDER_ID_EMPTY)
    stored = store.get(req.order_id)
    if stored is None:
        return codes.error(codes.ORDER_NOT_FOUND)

    # Scenario guard: keyed on the stored order's offer; the flow is inferred
    # from the order status (Decision 8) — UNPAID = pre-pay submitBooking
    # polling, anything else = post-pay issuance polling.
    offer = stored["offer"]
    flow = "submitBooking" if stored["status"] == "UNPAID" else "issuance"
    rule = rules.check("orderDetail", offer["airline"], offer["ori"], offer["dest"],
                       flow=flow)
    if rule and preset_def(rule)["kind"] != "status_override":
        body, _ = scenario_responses.render(rule)
        return body

    data = _build_order_detail_data(stored)
    if rule:  # status_override: e.g. stuck in ISSUING / ISSUE_FAILED
        scenario_responses.apply_status_override(rule, data)
    return codes.success(data)
