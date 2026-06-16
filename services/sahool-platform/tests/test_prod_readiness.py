"""اختبارات مُدقّق جاهزيّة الإنتاج (core.prod_readiness) — دالّة نقيّة offline."""

import pytest
from core.prod_readiness import evaluate_readiness

pytestmark = pytest.mark.unit

_STRONG = "x" * 40  # سرّ قويّ (≥32، غير افتراضيّ)

_HARDENED_PROD = {
    "SAHOOL_ENV": "production",
    "SAHOOL_JWT_SECRET": _STRONG,
    "JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----...",
    "SAHOOL_DEV_AUTH": "false",
    "SAHOOL_DEBUG": "false",
    "SAHOOL_RATE_LIMIT_PER_MIN": "120",
    "DATABASE_URL": "postgres://x",
}


def _by_key(report):
    return {c["key"]: c["status"] for c in report["checks"]}


def test_hardened_production_is_ready():
    r = evaluate_readiness(_HARDENED_PROD)
    assert r["is_production"] is True
    assert r["ready"] is True
    assert r["blockers"] == []


def test_weak_production_blocks_with_expected_blockers():
    r = evaluate_readiness(
        {"SAHOOL_ENV": "production", "SAHOOL_JWT_SECRET": "short", "SAHOOL_DEV_AUTH": "true"}
    )
    assert r["is_production"] is True
    assert r["ready"] is False
    keys = {b["key"] for b in r["blockers"]}
    assert "jwt_secret_strength" in keys  # سرّ ضعيف ⇒ حاجب
    assert "dev_auth_disabled" in keys  # تجاوز مصادقة مُفعَّل ⇒ حاجب
    assert "database_configured" in keys  # لا قاعدة ⇒ حاجب


def test_dev_env_weak_secret_is_warning_not_blocker():
    # في التطوير: الحرِج يُخفَّض إلى تحذير ⇒ ready True، لا blockers.
    r = evaluate_readiness({"SAHOOL_ENV": "development", "SAHOOL_JWT_SECRET": "short"})
    assert r["is_production"] is False
    assert r["ready"] is True
    assert r["blockers"] == []
    assert _by_key(r)["jwt_secret_strength"] == "warn"


def test_rs256_absence_is_warning_not_blocker_even_in_prod():
    env = dict(_HARDENED_PROD)
    env.pop("JWT_PUBLIC_KEY")
    r = evaluate_readiness(env)
    assert _by_key(r)["rs256_public_key"] == "warn"
    assert r["ready"] is True  # توصية لا حجب
    assert all(b["key"] != "rs256_public_key" for b in r["blockers"])


def test_default_secret_is_weak():
    r = evaluate_readiness(
        {
            "SAHOOL_ENV": "production",
            "SAHOOL_JWT_SECRET": "dev-secret-CHANGE-IN-PRODUCTION",
            "SAHOOL_DEV_AUTH": "false",
            "DATABASE_URL": "x",
        }
    )
    assert _by_key(r)["jwt_secret_strength"] == "block"


def test_rate_limit_disabled_is_warning():
    env = dict(_HARDENED_PROD)
    env["SAHOOL_RATE_LIMIT_PER_MIN"] = "0"
    r = evaluate_readiness(env)
    assert _by_key(r)["rate_limiting_enabled"] == "warn"
    # تحذير لا حجب ⇒ يبقى ready.
    assert r["ready"] is True


def test_every_check_has_key_and_arabic_detail():
    r = evaluate_readiness(_HARDENED_PROD)
    for c in r["checks"]:
        assert c["key"] and c["status"] in ("ok", "warn", "block")
        assert c["detail_ar"]
