"""Fixed mock inventory and pricing rules (DESIGN.md section 4)."""

CURRENCY = "USD"
PRODUCT = ["BASIC"]
ISSUANCE_TIME_IN_MINS = 120
ORDER_EXPIRE_IN_MINUTES = 30
SEAT_COUNT = 9
CABIN = "Y"
SEAT_CLASS = "Y"

# Wallet-to-wallet pay types (PAY API adjustment wiki). For these payTypes the
# request accountNumber is empty and the response accountNumber is the RECEIVER
# account on the wallet-to-wallet transaction (fixed mock value per gateway).
WALLET_RECEIVER_ACCOUNTS = {
    "ANTOM": "21881200168224D1",
    "YEEPAY": "21881200168224D1",
}

# Pax-type fare multipliers relative to the adult fare (mock rule).
PAX_FARE_MULTIPLIER = {"ADT": 1.0, "CHD": 0.75, "INF": 0.10}

# Checked-baggage ancillary price rule: USD per kg.
ANCILLARY_PRICE_PER_KG = 1.5
# Number of CHECKEDBAGGAGE upsell options, in +5 kg steps above FBA.
ANCILLARY_OPTION_STEPS = (5, 10, 15)

AIRLINES = {
    "JT": {
        "flight_number": "JT100",
        "dep_time": "08:00:00",
        "arr_time": "10:00:00",
        "duration": 120,
        "aircraft": "B739",
        "fba_kg": 0,
        "fare": 60.00,
        "tax": 8.00,
    },
    "GA": {
        "flight_number": "GA200",
        "dep_time": "12:00:00",
        "arr_time": "14:00:00",
        "duration": 120,
        "aircraft": "B738",
        "fba_kg": 20,
        "fare": 95.00,
        "tax": 12.00,
    },
    "QZ": {
        "flight_number": "QZ300",
        "dep_time": "16:00:00",
        "arr_time": "18:00:00",
        "duration": 120,
        "aircraft": "A320",
        "fba_kg": 0,
        "fare": 55.00,
        "tax": 7.00,
    },
    "AK": {
        "flight_number": "AK400",
        "dep_time": "06:00:00",
        "arr_time": "08:00:00",
        "duration": 120,
        "aircraft": "A320",
        "fba_kg": 0,
        "fare": 50.00,
        "tax": 6.00,
    },
    "SQ": {
        "flight_number": "SQ500",
        "dep_time": "18:00:00",
        "arr_time": "20:00:00",
        "duration": 120,
        "aircraft": "B77W",
        "fba_kg": 20,
        "fare": 120.00,
        "tax": 15.00,
    },
    "JL": {
        "flight_number": "JL600",
        "dep_time": "20:00:00",
        "arr_time": "22:00:00",
        "duration": 120,
        "aircraft": "B788",
        "fba_kg": 15,
        "fare": 110.00,
        "tax": 14.00,
    },
}

AIRLINE_ORDER = ["JT", "GA", "QZ", "AK", "SQ", "JL"]

FLIGHT_TO_AIRLINE = {v["flight_number"]: k for k, v in AIRLINES.items()}
