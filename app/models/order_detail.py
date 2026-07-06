from typing import Optional

from pydantic import Field

from app.models.common import PermissiveModel


class OrderDetailRequest(PermissiveModel):
    order_id: Optional[str] = Field(None, alias="orderId")
