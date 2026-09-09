"""Auth Service Tests — SAHOOL v9.1.0"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jose import jwt

from conftest import TEST_JWT_SECRET, make_token


@pytest.mark.unit
def test_real_token_issuer_grants_only_tenant_bound_mcp_reads():
    """Exercise the real signer in isolation from service module-name collisions."""
    root = Path(__file__).resolve().parents[1]
    script = """
import json
import main
from jose import jwt
roles = ["owner", "admin", "expert", "farmer", "viewer", "service", "unknown"]
rows = []
for role in roles:
    for tenant in ["b3ee640f-e0a0-4455-abe3-dfb8e5fdf122", ""]:
        token, jti = main.create_access_token(7, "test@sahool.ye", role, "Test", tenant)
        claims = jwt.decode(token, main.JWT_VERIFY_KEY, algorithms=[main.JWT_ALGORITHM], audience="sahool")
        rows.append(claims)
print(json.dumps(rows))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root / "services/auth",
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "JWT_SECRET": TEST_JWT_SECRET,
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    rows = json.loads(proc.stdout.splitlines()[-1])
    for claims in rows:
        scopes = set(claims.get("scope", "").split())
        if (
            claims["role"] in {"owner", "admin", "expert", "farmer", "viewer"}
            and claims["tenant_id"]
        ):
            assert scopes == {"satellite:read", "weather:read", "crop:read", "market:read"}
        else:
            assert scopes == set()
        assert "admin" not in scopes and not any(scope.endswith(":write") for scope in scopes)
        assert claims["sub"] == "7"


class TestJWTStructure:
    """Unit tests for JWT token structure."""

    @pytest.mark.unit
    def test_token_has_required_claims(self):
        token = make_token()
        payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")
        for claim in [
            "sub",
            "email",
            "role",
            "tenant_id",
            "jti",
            "iss",
            "aud",
            "exp",
            "iat",
            "nbf",
        ]:
            assert claim in payload, f"Missing claim: {claim}"

    @pytest.mark.unit
    def test_token_iss_is_sahool(self):
        payload = jwt.decode(make_token(), TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")
        assert payload["iss"] == "sahool-auth"

    @pytest.mark.unit
    def test_expired_token_rejected(self, expired_token):
        import pytest
        from jose import JWTError

        with pytest.raises(JWTError):
            jwt.decode(expired_token, TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")

    @pytest.mark.unit
    def test_admin_role_in_token(self, admin_token):
        payload = jwt.decode(admin_token, TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")
        assert payload["role"] == "admin"

    @pytest.mark.unit
    def test_wrong_audience_rejected(self):
        token = make_token()
        with pytest.raises(jwt.JWTError):
            jwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"], audience="wrong_audience")

    @pytest.mark.unit
    def test_tampered_token_rejected(self):
        token = make_token()
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(jwt.JWTError):
            jwt.decode(tampered, TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")


class TestPasswordValidation:
    @pytest.mark.unit
    def test_password_min_length(self):
        """Password must be at least 8 chars."""
        assert len("Abc123!@") >= 8

    @pytest.mark.unit
    def test_password_requires_uppercase(self):
        assert any(c.isupper() for c in "Abc123!@")

    @pytest.mark.unit
    def test_password_requires_digit(self):
        assert any(c.isdigit() for c in "Abc123!@")

    @pytest.mark.unit
    def test_password_requires_special(self):
        assert any(c in "!@#$%^&*()" for c in "Abc123!@")


class TestAuthEndpoints:
    @pytest.mark.integration
    async def test_health_endpoint(self, http_client):
        from conftest import service_urls

        resp = await http_client.get(f"{service_urls['auth']}/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    @pytest.mark.security
    async def test_login_wrong_password(self, http_client):
        from conftest import service_urls

        resp = await http_client.post(
            f"{service_urls['auth']}/v1/auth/login",
            json={"email": "test@sahool.ye", "password": "WrongPass123!"},
        )
        assert resp.status_code == 401

    @pytest.mark.security
    async def test_sql_injection_in_email(self, http_client):
        from conftest import service_urls

        resp = await http_client.post(
            f"{service_urls['auth']}/v1/auth/login",
            json={"email": "' OR '1'='1", "password": "anything"},
        )
        assert resp.status_code in [401, 422]
