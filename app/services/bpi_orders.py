"""In-memory BPI order store, keyed by client-supplied auxiliaryOrderNo.

Consistent with orders.py: lost on restart (acceptable). Same auxiliaryOrderNo
ordered twice is an idempotent upsert (latest wins).
"""
from typing import Any, Dict, List, Optional


class BpiOrderStore:
    def __init__(self):
        self._orders: Dict[str, dict] = {}

    def upsert(self, aux_no: str, is_cross: int, passenger_auxes: List[Dict[str, Any]]) -> dict:
        order = {
            "auxiliaryOrderNo": aux_no,
            "isCross": is_cross,
            # Each entry: {passengerInfo, segment, weight, basePrice}
            "passengerAuxes": passenger_auxes,
        }
        self._orders[aux_no] = order
        return order

    def get(self, aux_no: str) -> Optional[dict]:
        return self._orders.get(aux_no)

    def clear(self):
        self._orders.clear()


store = BpiOrderStore()
