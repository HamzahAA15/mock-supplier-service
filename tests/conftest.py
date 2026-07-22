from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.bpi_orders import store as bpi_store
from app.services.notifications import store as notification_store
from app.services.orders import store
from app.services.scenario_rules import rules as scenario_rules
from app.services.standardized_bpi_orders import store as standardized_bpi_store


def future_date(days=60):
    """A YYYY-MM-DD departure date safely in the future, relative to today.

    Tests must not hardcode near-future dates: /flight/search/v3 rejects
    departures earlier than the current time (result code 205), so a literal
    date silently expires once the system clock passes it.
    """
    return (date.today() + timedelta(days=days)).strftime("%Y-%m-%d")


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_store():
    # Scenario rules reset BEFORE and AFTER: a leaked rule from one test would
    # silently change another test's blocked-route behavior.
    store.clear()
    bpi_store.clear()
    standardized_bpi_store.clear()
    notification_store.clear()
    scenario_rules.reset()
    yield
    store.clear()
    bpi_store.clear()
    standardized_bpi_store.clear()
    notification_store.clear()
    scenario_rules.reset()


ADMIN_KEY = "test-admin-key"


@pytest.fixture()
def admin_env(monkeypatch):
    """Enable the admin API for a test (ADMIN_KEY is read per-request)."""
    monkeypatch.setenv("ADMIN_KEY", ADMIN_KEY)


@pytest.fixture()
def admin_headers(admin_env):
    return {"X-Admin-Key": ADMIN_KEY}


def search_body(ori="CGK", dest="DPS", dep_date=None, adult=1, child=0, infant=0, **extra):
    if dep_date is None:
        dep_date = future_date()
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
