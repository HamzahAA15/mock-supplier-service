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
ANCILLARY_PRICE_PER_KG = 0.5
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
        "fare": 12.00,
        "tax": 2.00,
    },
    "GA": {
        "flight_number": "GA200",
        "dep_time": "12:00:00",
        "arr_time": "14:00:00",
        "duration": 120,
        "aircraft": "B738",
        "fba_kg": 20,
        "fare": 15.00,
        "tax": 3.00,
    },
    "QZ": {
        "flight_number": "QZ300",
        "dep_time": "16:00:00",
        "arr_time": "18:00:00",
        "duration": 120,
        "aircraft": "A320",
        "fba_kg": 0,
        "fare": 11.00,
        "tax": 2.50,
    },
    "AK": {
        "flight_number": "AK400",
        "dep_time": "06:00:00",
        "arr_time": "08:00:00",
        "duration": 120,
        "aircraft": "A320",
        "fba_kg": 0,
        "fare": 10.00,
        "tax": 1.50,
    },
    "SQ": {
        "flight_number": "SQ500",
        "dep_time": "18:00:00",
        "arr_time": "20:00:00",
        "duration": 120,
        "aircraft": "B77W",
        "fba_kg": 20,
        "fare": 18.00,
        "tax": 4.00,
    },
    "JL": {
        "flight_number": "JL600",
        "dep_time": "20:00:00",
        "arr_time": "22:00:00",
        "duration": 120,
        "aircraft": "B788",
        "fba_kg": 15,
        "fare": 17.00,
        "tax": 3.50,
    },
    "MM": {
        "flight_number": "MM700",
        "dep_time": "10:00:00",
        "arr_time": "12:00:00",
        "duration": 120,
        "aircraft": "A320",
        "fba_kg": 0,
        "fare": 13.00,
        "tax": 2.50,
    },
}

AIRLINE_ORDER = ["JT", "GA", "QZ", "AK", "SQ", "JL", "MM"]

FLIGHT_TO_AIRLINE = {v["flight_number"]: k for k, v in AIRLINES.items()}
