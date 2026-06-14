from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.middleware import require_auth
from config.settings import AuthConfig


def make_app(auth: AuthConfig) -> FastAPI:
    from fastapi import Depends

    app = FastAPI()

    mock_settings = MagicMock()
    mock_settings.auth = auth
    app.state.settings = mock_settings

    @app.get("/v1/protected", dependencies=[Depends(require_auth)])
    async def protected():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


class TestRequireAuth:
    def test_auth_disabled_allows_any_request(self):
        client = TestClient(make_app(AuthConfig(enabled=False)))
        assert client.get("/v1/protected").status_code == 200

    def test_valid_api_key_passes(self):
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"])
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected", headers={"X-API-Key": "sk-good"}).status_code == 200

    def test_invalid_api_key_returns_401(self):
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"])
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected", headers={"X-API-Key": "sk-wrong"}).status_code == 401

    def test_missing_key_returns_401(self):
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"])
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected").status_code == 401

    def test_health_route_not_protected(self):
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"])
        client = TestClient(make_app(cfg))
        assert client.get("/health").status_code == 200

    def test_multiple_valid_keys(self):
        cfg = AuthConfig(enabled=True, api_keys=["key-a", "key-b"])
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected", headers={"X-API-Key": "key-a"}).status_code == 200
        assert client.get("/v1/protected", headers={"X-API-Key": "key-b"}).status_code == 200

    def test_valid_jwt_passes(self):
        from jose import jwt

        secret = "test-secret"
        token = jwt.encode({"sub": "user1"}, secret, algorithm="HS256")
        cfg = AuthConfig(enabled=True, api_keys=[], jwt_secret=secret)
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    def test_invalid_jwt_returns_401(self):
        cfg = AuthConfig(enabled=True, api_keys=[], jwt_secret="real-secret")
        client = TestClient(make_app(cfg))
        assert client.get(
            "/v1/protected", headers={"Authorization": "Bearer not-a-real-token"}
        ).status_code == 401

    def test_jwt_wrong_secret_returns_401(self):
        from jose import jwt

        token = jwt.encode({"sub": "user1"}, "wrong-secret", algorithm="HS256")
        cfg = AuthConfig(enabled=True, api_keys=[], jwt_secret="real-secret")
        client = TestClient(make_app(cfg))
        assert client.get("/v1/protected", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_no_jwt_secret_rejects_bearer(self):
        from jose import jwt

        token = jwt.encode({"sub": "user1"}, "some-secret", algorithm="HS256")
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"], jwt_secret=None)
        client = TestClient(make_app(cfg))
        # Bearer token not accepted when no jwt_secret configured
        assert client.get("/v1/protected", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_api_key_takes_precedence_over_invalid_jwt(self):
        cfg = AuthConfig(enabled=True, api_keys=["sk-good"], jwt_secret="s")
        client = TestClient(make_app(cfg))
        # Valid API key + garbage JWT → should pass (key checked first)
        assert client.get(
            "/v1/protected",
            headers={"X-API-Key": "sk-good", "Authorization": "Bearer garbage"},
        ).status_code == 200
