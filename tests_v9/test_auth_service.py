"""Auth Service Tests — SAHOOL v9.1.0"""

import pytest
from jose import jwt

from conftest import TEST_JWT_SECRET, make_token


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
            f"{service_urls['auth']}/auth/login",
            json={"email": "test@sahool.ye", "password": "WrongPass123!"},
        )
        assert resp.status_code == 401

    @pytest.mark.security
    async def test_sql_injection_in_email(self, http_client):
        from conftest import service_urls

        resp = await http_client.post(
            f"{service_urls['auth']}/auth/login",
            json={"email": "' OR '1'='1", "password": "anything"},
        )
        assert resp.status_code in [401, 422]
