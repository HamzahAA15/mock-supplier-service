"""Permissive RQ models for the BPI endpoints.

Passenger fields are ignored by search and echoed by order, so segments/auxes
are kept as raw dicts (empty/missing-tolerant), mirroring the flight models.
"""
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.models.common import PermissiveModel


class BpiSearchRequest(PermissiveModel):
    segments: Optional[List[Dict[str, Any]]] = None
    passenger: Optional[List[Dict[str, Any]]] = None


class BpiOrderRequest(PermissiveModel):
    ancillary_order_no: Optional[str] = Field(None, alias="ancillaryOrderNo")
    order_no: Optional[str] = Field(None, alias="orderNo")
    is_cross: Optional[int] = Field(None, alias="isCross")
    passenger_auxes: Optional[List[Dict[str, Any]]] = Field(None, alias="passengerAuxes")


class BpiOrderDetailRequest(PermissiveModel):
    auxiliary_order_no: Optional[str] = Field(None, alias="auxiliaryOrderNo")
