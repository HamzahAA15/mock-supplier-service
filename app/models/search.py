from typing import Any, Dict, List, Optional

from pydantic import Field

from app.models.common import PermissiveModel


class SearchRequest(PermissiveModel):
    product: Optional[List[str]] = None
    nonstop: Optional[bool] = None
    routes: Optional[List[Dict[str, Any]]] = None
    adult_number: Optional[int] = Field(None, alias="adultNumber")
    child_number: Optional[int] = Field(None, alias="childNumber")
    infant_number: Optional[int] = Field(None, alias="infantNumber")
    airline_ids: Optional[List[str]] = Field(None, alias="airlineIds")
