"""Security Tests — SAHOOL v9.1.0

تدقيق 2026-11-01 (Q1): كانت ``TestJWTSecurity`` تفكّ توكن ``conftest.make_token`` بـPyJWT
مباشرةً — أي تختبر المكتبة ومساعِد الاختبار لا مُتحقِّق الإنتاج — و``TestHTTPSecurity``
تنادي خدمات حيّة على ``127.0.0.1`` فتتخطّى دائماً في CI. الآن كلّها تمرّ عبر ``main.py``
الحقيقيّ لـauth وlocal-ai-rag (``real_app_probe``)، فلا تخطّي ولا اختبار للمكتبة وحدها.
"""

import os

import pytest
from real_app_probe import probe_auth, probe_rag


@pytest.fixture(scope="module")
def auth_probe() -> dict:
    return probe_auth()


@pytest.fixture(scope="module")
def rag_probe() -> dict:
    return probe_rag()


class TestJWTSecurity:
    """مُتحقِّق الإنتاج (``get_current_user`` في auth) — لا ``jwt.decode`` في الاختبار."""

    @pytest.mark.unit
    @pytest.mark.security
    def test_algorithm_confusion(self, auth_probe):
        """توكن alg=none بلا توقيع يُرفَض من خدمة auth نفسها."""
        assert auth_probe["me_alg_none"] == 401

    @pytest.mark.unit
    @pytest.mark.security
    def test_weak_secret_rejected(self, auth_probe):
        """توكن موقَّع بسرّ آخر يُرفَض؛ ومُصدِرٌ خارج القائمة يُرفَض."""
        assert auth_probe["me_wrong_secret"] == 401
        assert auth_probe["me_foreign_issuer"] == 401

    @pytest.mark.unit
    @pytest.mark.security
    def test_jti_claim_present(self, auth_probe):
        """المُصدِر الحقيقيّ (create_access_token) يضع jti، وإبطالُه يُسقط التوكن."""
        assert auth_probe["issued_has_jti"] is True
        assert auth_probe["me_issued_token"] == 200  # شاهدٌ موجب قبل الإبطال
        assert auth_probe["me_revoked_token"] == 401

    @pytest.mark.unit
    @pytest.mark.security
    def test_nbf_claim_present(self, auth_probe):
        assert auth_probe["issued_has_nbf"] is True
        assert auth_probe["issued_header_alg"] in {"HS256", "RS256"}


class TestHTTPSecurity:
    @pytest.mark.unit
    @pytest.mark.security
    def test_auth_endpoint_requires_auth(self, auth_probe):
        """Protected endpoints must return 401 without token."""
        assert auth_probe["me_no_token"] == 401

    @pytest.mark.unit
    @pytest.mark.security
    def test_rate_limiting_login(self, auth_probe):
        """بعد MAX_LOGIN_ATTEMPTS فشلاً يُقفَل الحساب (429) — حتى لكلمة المرور الصحيحة."""
        n = auth_probe["max_login_attempts"]
        seq = auth_probe["lockout_sequence"]
        assert seq[:n] == [401] * n, seq
        assert seq[n:] == [429] * (len(seq) - n), seq
        assert auth_probe["login_correct_while_locked"] == 429

    @pytest.mark.unit
    @pytest.mark.security
    def test_rag_requires_auth(self, rag_probe):
        """RAG ``/v1/query`` يرفض بلا توكن وبتوكن مزوَّر، ويقبل الصالح (503 = تجاوز الحارس)."""
        assert rag_probe["query_no_token"] == 401
        assert rag_probe["query_alg_none"] == 401
        assert rag_probe["query_wrong_secret"] == 401
        assert rag_probe["query_foreign_issuer"] == 401
        assert rag_probe["query_valid_token"] == 503


class TestDockerSecurity:
    @pytest.mark.unit
    @pytest.mark.security
    def test_no_default_passwords_in_compose(self):
        """Compose files must not contain weak default passwords."""
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

    @pytest.mark.unit
    @pytest.mark.security
    def test_db_ports_not_publicly_exposed(self):
        """DB ports must be bound to localhost only."""
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
