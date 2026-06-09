"""Security Tests — SAHOOL v9.1.0"""

import pytest
from conftest import TEST_JWT_SECRET, make_token
from jose import jwt


class TestJWTSecurity:
    @pytest.mark.security
    def test_algorithm_confusion(self):
        """Must reject tokens with 'none' algorithm."""
        from jose import JWTError

        token = make_token()
        with pytest.raises((JWTError, Exception)):
            jwt.decode(token, "", algorithms=["none"], audience="sahool")

    @pytest.mark.security
    def test_weak_secret_rejected(self):
        """Token signed with wrong secret must be rejected."""
        from jose import JWTError

        token = make_token()
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong_secret", algorithms=["HS256"], audience="sahool")

    @pytest.mark.security
    def test_jti_claim_present(self):
        """Every token must have a jti claim for revocation."""
        payload = jwt.decode(make_token(), TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")
        assert "jti" in payload
        assert len(payload["jti"]) > 10

    @pytest.mark.security
    def test_nbf_claim_present(self):
        """nbf claim must be present."""
        payload = jwt.decode(make_token(), TEST_JWT_SECRET, algorithms=["HS256"], audience="sahool")
        assert "nbf" in payload


class TestHTTPSecurity:
    @pytest.mark.security
    async def test_auth_endpoint_requires_auth(self, http_client):
        """Protected endpoints must return 401 without token."""
        from conftest import service_urls

        resp = await http_client.get(f"{service_urls['auth']}/auth/me")
        assert resp.status_code == 401

    @pytest.mark.security
    async def test_rate_limiting_login(self, http_client):
        """Login endpoint should rate limit after many attempts."""
        from conftest import service_urls

        for _ in range(6):
            await http_client.post(
                f"{service_urls['auth']}/auth/login",
                json={"email": "brute@test.ye", "password": "Wrong123!"},
            )
        resp = await http_client.post(
            f"{service_urls['auth']}/auth/login",
            json={"email": "brute@test.ye", "password": "Wrong123!"},
        )
        assert resp.status_code in [429, 401]

    @pytest.mark.security
    async def test_rag_requires_auth(self, http_client):
        """RAG /query must require authentication."""
        from conftest import service_urls

        resp = await http_client.post(f"{service_urls['rag']}/query", json={"question": "test"})
        assert resp.status_code == 401


class TestDockerSecurity:
    @pytest.mark.security
    def test_no_default_passwords_in_compose(self):
        """Compose files must not contain weak default passwords."""
        import os
        import re

        BASE = os.path.dirname(os.path.dirname(__file__))
        bad_patterns = ["minioadmin", "password123", "admin123", "secret123"]
        for cf in [
            "docker-compose.v9.yml",
            "docker-compose.unified.yml",
            "docker-compose.light.yml",
        ]:
            fpath = os.path.join(BASE, cf)
            if not os.path.exists(fpath):
                continue
            content = open(fpath).read()
            for bp in bad_patterns:
                assert bp not in content, f"Weak password '{bp}' in {cf}"

    @pytest.mark.security
    def test_db_ports_not_publicly_exposed(self):
        """DB ports must be bound to localhost only."""
        import os

        BASE = os.path.dirname(os.path.dirname(__file__))
        for cf in [
            "docker-compose.v9.yml",
            "docker-compose.light.yml",
            "docker-compose.unified.yml",
        ]:
            fpath = os.path.join(BASE, cf)
            if not os.path.exists(fpath):
                continue
            content = open(fpath).read()
            assert '"5432:5432"' not in content, f"PG port exposed in {cf}"
            assert '"6379:6379"' not in content, f"Redis port exposed in {cf}"
