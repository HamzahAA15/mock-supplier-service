"""Permissive RQ models for the Standardized BPI endpoints.

Routes/passengers/selectedAncillary are kept as raw dicts (echo principle),
mirroring the tsy-bpi models. Validation happens in the router, never as a
FastAPI 422 — the contract returns result codes in an HTTP-200 envelope.
"""
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.models.common import PermissiveModel


class StandardizedBpiSearchRequest(PermissiveModel):
    ancillary_type: Optional[str] = Field(None, alias="ancillaryType")
    routes: Optional[List[Dict[str, Any]]] = None
    passengers: Optional[List[Dict[str, Any]]] = None
    ticketing_funnel: Optional[str] = Field(None, alias="ticketingFunnel")


class StandardizedBpiOrderRequest(PermissiveModel):
    ancillary_order_no: Optional[str] = Field(None, alias="ancillaryOrderNo")
    is_cross: Optional[bool] = Field(None, alias="isCross")
    passengers: Optional[List[Dict[str, Any]]] = None
    selected_ancillary: Optional[List[Dict[str, Any]]] = Field(None, alias="selectedAncillary")
    ticketing_funnel: Optional[str] = Field(None, alias="ticketingFunnel")
