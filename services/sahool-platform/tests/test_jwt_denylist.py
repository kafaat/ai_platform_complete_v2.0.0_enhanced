"""اختبارات فحص إبطال JWT (jti denylist) — offline بـbackend ذاكرة.

يتحقّق من: الإبطال/الفحص، انتهاء المهلة، jti الغائب، backend الغائب (ميزة معطّلة)،
وfail-open عند فشل الـbackend (لا قفل المستخدم).
"""

from core.jwt_denylist import (
    JTI_REVOKED_KEY,
    InMemoryDenylist,
    is_token_revoked,
)


def test_revoked_jti_is_detected():
    b = InMemoryDenylist()
    b.revoke("j1", ttl_seconds=60)
    assert is_token_revoked(b, "j1") is True


def test_unrevoked_jti_passes():
    assert is_token_revoked(InMemoryDenylist(), "j-unknown") is False


def test_expired_revocation_no_longer_blocks():
    b = InMemoryDenylist()
    b.revoke("j2", ttl_seconds=0)  # منتهٍ فوراً
    assert is_token_revoked(b, "j2") is False


def test_missing_jti_is_not_revoked():
    b = InMemoryDenylist()
    b.revoke("j3", ttl_seconds=60)
    assert is_token_revoked(b, None) is False
    assert is_token_revoked(b, "") is False


def test_no_backend_means_feature_disabled():
    # backend None ⇒ الميزة غير مُفعَّلة ⇒ لا إبطال (توافق خلفي).
    assert is_token_revoked(None, "any") is False


def test_fail_open_on_backend_error():
    class _Boom:
        def is_revoked(self, jti):
            raise RuntimeError("redis down")

        def revoke(self, jti, ttl_seconds):
            pass

    # fail-open: تعذّر الفحص لا يقفل المستخدم (لا يرفع، يُرجِع False).
    assert is_token_revoked(_Boom(), "j4") is False


def test_key_scheme_matches_auth_service():
    # نفس مخطّط مفتاح خدمة auth (sahool:jti:revoked:{jti}) — لا مخطّط موازٍ.
    assert JTI_REVOKED_KEY.format(jti="abc") == "sahool:jti:revoked:abc"
