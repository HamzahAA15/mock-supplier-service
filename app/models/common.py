"""Shared request-model plumbing.

All request models are deliberately permissive (every field optional, extra
allowed): the contract returns business result codes in an HTTP-200 envelope,
so validation happens in the routers, never as a FastAPI 422.

Passenger/contact payloads are typed as raw dicts on purpose — the echo
principle (DESIGN.md section 3.1) requires reflecting them back verbatim.
"""
from pydantic import BaseModel, ConfigDict


class PermissiveModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
