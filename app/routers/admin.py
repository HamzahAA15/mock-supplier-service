"""Admin plane for scenario rules — UI page + CRUD API.

Unlike the business endpoints (always HTTP 200, envelope codes), the admin API
uses real HTTP statuses: 401 wrong key, 404 disabled/unknown, 422 invalid rule.
Auth is a shared secret: X-Admin-Key header checked against the ADMIN_KEY env
var, read PER REQUEST so it can be set/rotated without a restart (and so tests
can monkeypatch it). ADMIN_KEY unset -> the whole admin API is disabled (404).
See SCENARIO_RULES_DESIGN.md section 7.
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app import config
from app.services.scenario_rules import (
    ENDPOINTS,
    FLOW_ENDPOINTS,
    FLOWS,
    PRESETS,
    WILDCARD_AIRLINE,
    is_overridable,
    rules,
    validate_rule,
)

router = APIRouter(prefix="/admin")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def require_admin_key(x_admin_key: Optional[str] = Header(None)):
    admin_key = os.environ.get("ADMIN_KEY")  # per-request read, never cached
    if not admin_key:
        # Admin disabled entirely when the env var is unset (Decision 6).
        raise HTTPException(status_code=404, detail="Not Found")
    if x_admin_key != admin_key:
        raise HTTPException(status_code=401, detail="invalid admin key")


@router.get("")
def admin_page():
    """The UI page itself is unauthenticated; it prompts for the key and sends
    it as X-Admin-Key on every fetch (design section 7)."""
    return FileResponse(_STATIC_DIR / "admin.html", media_type="text/html")


@router.get("/rules", dependencies=[Depends(require_admin_key)])
def list_rules():
    return {"rules": rules.list()}


@router.put("/rules", dependencies=[Depends(require_admin_key)])
def put_rule(payload: dict = Body(...)):
    rule, errors = validate_rule(payload)
    if errors:
        return JSONResponse(status_code=422, content={"errors": errors})
    return {"rule": rules.put(rule)}


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_admin_key)])
def delete_rule(rule_id: str):
    if not rules.delete(rule_id):
        raise HTTPException(status_code=404, detail="unknown rule_id")
    return {"deleted": rule_id}


@router.post("/rules/reset", dependencies=[Depends(require_admin_key)])
def reset_rules():
    rules.reset()
    return {"rules": rules.list()}


@router.get("/presets", dependencies=[Depends(require_admin_key)])
def get_presets():
    """Everything the UI needs to drive its dropdowns — no hardcoded lists in JS."""
    return {
        "endpoints": [
            {
                "id": endpoint,
                "overridable": is_overridable(endpoint),
                "flow_capable": endpoint in FLOW_ENDPOINTS,
                "presets": PRESETS[endpoint],
            }
            for endpoint in ENDPOINTS
        ],
        "flows": list(FLOWS),
        "airlines": list(config.AIRLINE_ORDER),
        "wildcard_airline": WILDCARD_AIRLINE,  # "*" = any airline (airline field only)
    }
