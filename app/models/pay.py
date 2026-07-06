from typing import Optional

from pydantic import Field

from app.models.common import PermissiveModel


class PayRequest(PermissiveModel):
    order_id: Optional[str] = Field(None, alias="orderId")
    pay_type: Optional[str] = Field("BPA", alias="payType")
    account_number: Optional[str] = Field("", alias="accountNumber")
