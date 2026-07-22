from typing import Optional

from pydantic import Field

from app.models.common import PermissiveModel


class NotificationRequest(PermissiveModel):
    event_type: Optional[str] = Field(None, alias="eventType")
    reference_id: Optional[str] = Field(None, alias="referenceId")
    provider_order_id: Optional[str] = Field(None, alias="providerOrderId")
    amount: Optional[str] = Field(None, alias="amount")
    currency: Optional[str] = Field(None, alias="currency")
    receiver_account: Optional[str] = Field(None, alias="receiverAccount")
    origin_payment_id: Optional[str] = Field(None, alias="originPaymentId")
    paid_at: Optional[str] = Field(None, alias="paidAt")
    refunded_at: Optional[str] = Field(None, alias="refundedAt")
    timestamp: Optional[str] = Field(None, alias="timestamp")
