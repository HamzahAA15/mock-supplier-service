"""Shared fixtures/builders for the Standardized BPI test modules."""
from datetime import datetime, timedelta

BASE_SEARCH_PATH = "/ancillary/v1/baggage/search"
ORDER_PATH = "/ancillary/v1/orders"

TIER_WEIGHTS = [20, 30, 40, 50, 60, 70, 80, 90, 100]
TIER_PRICES = {20: 52.14, 30: 76.84, 40: 103.18, 50: 256.30, 60: 307.33,
               70: 358.38, 80: 430.27, 90: 483.49, 100: 536.74}


def future_dt(days=60, hour=8):
    """A 'yyyy-MM-dd HH:mm:ss' departure datetime safely in the future.
    Never hardcode near-future datetimes: past departures fail with code 5001."""
    dt = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def past_dt(days=1):
    dt = datetime.now() - timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def segment(marketing="AK", flight_no="AK342", dep="CGK", arr="BKI",
            dep_time=None, arr_time=None, operating=None, operating_flight_no=None,
            cabin="Y"):
    dep_time = dep_time or future_dt()
    arr_time = arr_time or future_dt(days=60, hour=12)
    return {
        "marketingCarrier": marketing,
        "flightNumber": flight_no,
        "operatingCarrier": operating or marketing,
        "operatingFlightNumber": operating_flight_no or flight_no,
        "departureAirport": dep,
        "arrivalAirport": arr,
        "departureTime": dep_time,
        "arrivalTime": arr_time,
        "cabin": cabin,
    }


# Blocked route for negative cases (dep SIN -> arr KUL is directionally blocked).
def blocked_segment():
    return segment(marketing="TR", flight_no="TR456", dep="SIN", arr="KUL")


# Synthetic passengers — do NOT use real booking PII in the repo.
PAX_1 = {"passengerId": 1, "pnr": "TEST01", "firstName": "ALPHA",
         "lastName": "TESTER", "passengerType": "ADT"}
PAX_2 = {"passengerId": 2, "pnr": "TEST02", "firstName": "BRAVO",
         "lastName": "TESTER", "passengerType": "ADT"}


def search_body(routes=None, passengers=None, ancillary_type="CHECKEDBAGGAGE", **extra):
    body = {
        "ancillaryType": ancillary_type,
        "routes": routes if routes is not None else [{"tripType": 1, "segments": [segment()]}],
    }
    if passengers is not None:
        body["passengers"] = passengers
    body.update(extra)
    return body


def offer_for(search_rs, route_index, weight_kg, passenger_index=0):
    """Pull a specific tier's offer out of a search response (round-trip)."""
    route = search_rs["data"]["routes"][route_index]
    if "passengerOffers" in route:
        offers = route["passengerOffers"][passenger_index]["ancillaryOffers"]
    else:
        offers = route["generalOffers"][0]["ancillaryOffers"]
    return next(o for o in offers if o["ancillaryCode"] == weight_kg)


def order_body(order_no, passengers=None, selected=None, is_cross=True, **extra):
    body = {
        "ancillaryOrderNo": order_no,
        "isCross": is_cross,
        "passengers": passengers if passengers is not None else [PAX_1],
        "selectedAncillary": selected or [],
    }
    body.update(extra)
    return body


def search_then_order(client, order_no="TVLK-BPI-TEST-1", weight_kg=20,
                      routes=None, passengers=None):
    """Full round-trip: search, pick a tier, order it. Returns (search_rs, order_rs)."""
    passengers = passengers if passengers is not None else [PAX_1]
    search_rs = client.post(BASE_SEARCH_PATH,
                            json=search_body(routes=routes, passengers=passengers)).json()
    offer = offer_for(search_rs, 0, weight_kg)
    selected = [{"passengerId": passengers[0]["passengerId"],
                 "ancillaryKey": offer["ancillaryKey"]}]
    order_rs = client.post(ORDER_PATH,
                           json=order_body(order_no, passengers=passengers,
                                           selected=selected)).json()
    return search_rs, order_rs
