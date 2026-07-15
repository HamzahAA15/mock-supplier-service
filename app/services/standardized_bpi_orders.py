"""In-memory Standardized BPI order store, keyed by client-supplied
ancillaryOrderNo.

Consistent with bpi_orders.py: lost on restart (acceptable). Re-posting the
same ancillaryOrderNo is an idempotent upsert (latest wins).
"""
from typing import Any, Dict, Optional


class StandardizedBpiOrderStore:
    def __init__(self):
        self._orders: Dict[str, dict] = {}

    def upsert(self, order_no: str, record: Dict[str, Any]) -> dict:
        self._orders[order_no] = record
        return record

    def get(self, order_no: str) -> Optional[dict]:
        return self._orders.get(order_no)

    def clear(self):
        self._orders.clear()


store = StandardizedBpiOrderStore()
