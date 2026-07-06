import uuid
from typing import Any, Optional

from fastapi import APIRouter, Body

router = APIRouter()

TOKEN_SCOPE = "search preOrderVerify ancillarySearch order pay orderDetail"


@router.post("/uaa/oauth/token")
def token(payload: Optional[Any] = Body(None)):
    # Basic auth header and grantType are accepted but not validated in v1.
    return {
        "accessToken": str(uuid.uuid4()),
        "tokenType": "Bearer",
        "expiresIn": 3600,
        "scope": TOKEN_SCOPE,
    }
