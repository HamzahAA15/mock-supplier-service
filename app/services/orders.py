"""In-memory order store plus orderId / PNR / ticket / transaction generation."""
import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional

from app import config

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def new_order_id() -> str:
    return "".join(random.choices(string.digits, k=10))


def new_pnr() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def new_ticket_number() -> str:
    return "".join(random.choices(string.digits, k=13))


def new_transaction_id() -> str:
    return "TXN" + "".join(random.choices(string.digits, k=10))


def fmt(dt: datetime) -> str:
    return dt.strftime(DATETIME_FMT)


class OrderStore:
    def __init__(self):
        self._orders: Dict[str, dict] = {}

    def create(self, offer: dict, passengers: list, contacts: list,
               added_ancillary: list, total: float) -> dict:
        order_id = new_order_id()
        while order_id in self._orders:
            order_id = new_order_id()
        now = datetime.now()
        order = {
            "orderId": order_id,
            "pnr": new_pnr(),
            "offer": offer,  # decoded offerKey: airline/ori/dest/dep_date
            "offerKey": offer["offerKey"],
            "passengers": passengers,
            "contacts": contacts,
            "addedAncillary": added_ancillary,
            "total": total,
            "status": "UNPAID",
            "createdTime": fmt(now),
            "updateTime": fmt(now),
            "expiredTime": fmt(now + timedelta(minutes=config.ORDER_EXPIRE_IN_MINUTES)),
            "payTime": "",
            "accountNumber": "",
            "ticketNumbers": {},  # passenger index -> 13-digit ticket, minted at pay
        }
        self._orders[order_id] = order
        return order

    def get(self, order_id: str) -> Optional[dict]:
        return self._orders.get(order_id)

    def pay(self, order: dict, account_number: str) -> dict:
        now = fmt(datetime.now())
        order["status"] = "ISSUED"
        order["payTime"] = now
        order["updateTime"] = now
        order["accountNumber"] = account_number or ""
        order["ticketNumbers"] = {i: new_ticket_number() for i in range(len(order["passengers"]))}
        return order

    def clear(self):
        self._orders.clear()


store = OrderStore()
