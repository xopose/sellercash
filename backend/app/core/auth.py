from __future__ import annotations

import time

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)
_jwks_cache: dict[str, object] = {"keys": [], "expires_at": 0.0}
_JWKS_TTL_SECONDS = 300


def _realm_base_url() -> str:
    settings = get_settings()
    return f"{settings.keycloak_server_url.rstrip('/')}/realms/{settings.keycloak_realm}"


def _fetch_jwks() -> list[dict]:
    now = time.time()
    if _jwks_cache["keys"] and now < float(_jwks_cache["expires_at"]):
        return list(_jwks_cache["keys"])  # shallow copy for safety

    jwks_url = f"{_realm_base_url()}/protocol/openid-connect/certs"
    response = httpx.get(jwks_url, timeout=8.0)
    response.raise_for_status()
    payload = response.json()
    keys = payload.get("keys", [])
    if not isinstance(keys, list):
        keys = []

    _jwks_cache["keys"] = keys
    _jwks_cache["expires_at"] = now + _JWKS_TTL_SECONDS
    return keys


def _resolve_signing_key(kid: str | None) -> dict | None:
    if not kid:
        return None
    try:
        keys = _fetch_jwks()
    except Exception:
        return None

    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


def verify_access_token(token: str) -> dict:
    settings = get_settings()

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed access token",
        ) from exc

    signing_key = _resolve_signing_key(header.get("kid"))
    if signing_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to resolve token signing key",
        )

    issuer = settings.keycloak_issuer or _realm_base_url()
    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "issuer": issuer,
        "options": {"verify_aud": settings.keycloak_verify_aud},
    }
    if settings.keycloak_verify_aud and settings.keycloak_audience:
        decode_kwargs["audience"] = settings.keycloak_audience

    try:
        claims = jwt.decode(token, signing_key, **decode_kwargs)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from exc

    return claims


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    settings = get_settings()
    if not settings.auth_enabled:
        return None

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_access_token(credentials.credentials)
