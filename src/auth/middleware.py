from __future__ import annotations

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    api_key: str | None = Security(_api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> None:
    settings = request.app.state.settings
    if not settings.auth.enabled:
        return

    if api_key and api_key in settings.auth.api_keys:
        return

    if credentials and settings.auth.jwt_secret:
        try:
            from jose import jwt, JWTError
            jwt.decode(
                credentials.credentials,
                settings.auth.jwt_secret,
                algorithms=[settings.auth.jwt_algorithm],
            )
            return
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid or missing credentials")
