from typing import Any, Dict, List, Optional

from pydantic import Field

from app.models.common import PermissiveModel


class AncillaryKeyList(PermissiveModel):
    passenger_index: Optional[int] = Field(None, alias="passengerIndex")
    ancillary_keys: Optional[List[str]] = Field(None, alias="ancillaryKeys")


class OrderRequest(PermissiveModel):
    offer_key: Optional[str] = Field(None, alias="offerKey")
    ancillary_key_lists: Optional[List[AncillaryKeyList]] = Field(None, alias="ancillaryKeyLists")
    # Raw dicts: echoed back verbatim (req #7).
    passengers: Optional[List[Dict[str, Any]]] = None
    contacts: Optional[List[Dict[str, Any]]] = None
