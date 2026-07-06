from typing import Optional

from pydantic import Field

from app.models.common import PermissiveModel


class VerifyRequest(PermissiveModel):
    offer_key: Optional[str] = Field(None, alias="offerKey")
