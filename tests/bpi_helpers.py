"""Shared fixtures/builders for the BPI test modules."""

SEG_VJ = {
    "carrier": "VJ", "flightNumber": "VJ84", "depAirport": "BNE",
    "depTime": "202607312330", "arrAirport": "SGN", "arrTime": "202608010500",
    "tripType": 1, "segmentIndex": 1, "id": 0,
}

SEG_GA = {
    "carrier": "GA", "flightNumber": "GA200", "depAirport": "CGK",
    "depTime": "202609201200", "arrAirport": "DPS", "arrTime": "202609201400",
    "tripType": 1, "segmentIndex": 2, "id": 0,
}

# Synthetic passenger — do NOT use real booking PII in the repo.
PAX_ADT = {
    "passengerType": "ADT", "lastName": "TESTER", "firstName": "ALPHA",
    "pnrCode": "TEST01", "gender": "F", "cardType": "PP", "cardNum": "X00000000",
    "cardExpired": "20301231", "nationality": "",
}


def search_body(segments=None, passenger=None):
    return {"segments": segments if segments is not None else [SEG_VJ],
            "passenger": passenger if passenger is not None else [PAX_ADT]}


def product_item_for(search_rs, seg_index, weight_kg):
    """Pull a specific tier's productItem out of a search response (round-trip)."""
    product = search_rs["products"][seg_index]
    item = next(i for i in product["productItems"] if i["baggage"]["baggageAllowance"] == weight_kg)
    return item


def pax_aux(segment, product_item, info=None):
    return {
        "passengerInfo": info or PAX_ADT,
        "segmentProducts": {
            "segment": segment,
            "productItem": {
                "productItemId": product_item["productItemId"],
                "productType": product_item["productType"],
                "basePrice": product_item["basePrice"],
                "currency": product_item["currency"],
                "baggage": product_item["baggage"],
            },
        },
    }


def order_body(aux_no, passenger_auxes, is_cross=1):
    return {"ancillaryOrderNo": aux_no, "orderNo": aux_no, "isCross": is_cross,
            "passengerAuxes": passenger_auxes}
