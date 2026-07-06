import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.orders import store


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    store.clear()
    yield
    store.clear()


def search_body(ori="CGK", dest="DPS", dep_date="2026-07-10", adult=1, child=0, infant=0, **extra):
    body = {
        "product": ["BASIC"],
        "nonstop": False,
        "routes": [{"cabin": ["Y"], "oriAirport": ori, "destAirport": dest, "depDate": dep_date}],
        "adultNumber": adult,
        "childNumber": child,
        "infantNumber": infant,
    }
    body.update(extra)
    return body


def order_body(offer_key, passengers=None, contacts=None, ancillary_key_lists=None):
    return {
        "offerKey": offer_key,
        "ancillaryKeyLists": ancillary_key_lists or [],
        "passengers": passengers or [
            {"firstName": "CANDY FREDRICK", "lastName": "MURING BALA", "passengerType": "ADT",
             "sex": "M", "birthDay": "1997-06-02", "nationality": "MY"}
        ],
        "contacts": contacts or [
            {"contactType": "AG", "firstName": "CANDY FREDRICK", "lastName": "MURING BALA",
             "email": "agent@example.com", "phone": "+62-8110000000"}
        ],
    }
