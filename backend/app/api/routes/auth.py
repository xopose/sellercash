from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthTokenRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None


@router.post("/token", response_model=AuthTokenResponse)
async def get_access_token(request: AuthTokenRequest) -> AuthTokenResponse:
    settings = get_settings()
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled on backend",
        )

    token_url = (
        f"{settings.keycloak_server_url.rstrip('/')}"
        f"/realms/{settings.keycloak_realm}/protocol/openid-connect/token"
    )
    payload = {
        "client_id": settings.keycloak_frontend_client_id,
        "grant_type": "password",
        "username": request.username,
        "password": request.password,
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth provider is unavailable",
        ) from exc

    body = response.json() if response.content else {}
    if response.status_code >= 400:
        message = (
            body.get("error_description")
            or body.get("error")
            or "Authentication failed"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    access_token = body.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Auth provider response has no access token",
        )

    return AuthTokenResponse(
        access_token=access_token,
        token_type=str(body.get("token_type") or "bearer"),
        expires_in=body.get("expires_in"),
    )
