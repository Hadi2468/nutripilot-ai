from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import API_TOKEN


# ============================================================
# Authentication
# ============================================================

security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    token = credentials.credentials

    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return token