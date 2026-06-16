"""core/prod_readiness.py — مُدقّق جاهزيّة الإنتاج (fail-closed config validation).

دالّة نقيّة تقيّم لقطة إعدادات (env dict) مقابل قائمة فحص أمنيّة/تشغيليّة، فتُرجع
بنوداً حاجبة (blockers) وتحذيرات (warnings). في الإنتاج (SAHOOL_ENV=production) تُعدّ
البنود الحرجة حاجبة (يجب ألّا يُنشَر بها)؛ في التطوير تُخفَّض إلى تحذيرات. لا I/O ولا
os.getenv داخلها (المُنادي يمرّر اللقطة) فتكون حتميّة وقابلة للاختبار offline.

صدق: لا تُلفّق نجاحاً؛ الإعداد غير المعروف/الناقص يُعلَن تحذيراً صريحاً لا تمريراً.
"""

from __future__ import annotations

_DEFAULT_DEV_SECRET = "dev-secret-CHANGE-IN-PRODUCTION"
_MIN_SECRET_LEN = 32
_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in _TRUTHY


def evaluate_readiness(env: dict) -> dict:
    """يقيّم جاهزيّة الإنتاج من لقطة إعدادات — انظر docstring الوحدة.

    يُرجع {ready, is_production, blockers, warnings, checks} حيث checks قائمة
    {key, status: ok|warn|block, detail_ar}. block يُحسب حاجباً في الإنتاج فقط؛
    في التطوير يُسجَّل كتحذير (السلوك مُعلَن، لا مفاجآت).
    """
    is_prod = (env.get("SAHOOL_ENV", "development") or "").strip().lower() == "production"
    checks: list[dict] = []

    def add(key: str, ok: bool, *, block_in_prod: bool, detail_ar: str) -> None:
        if ok:
            status = "ok"
        elif block_in_prod and is_prod:
            status = "block"
        else:
            status = "warn"
        checks.append({"key": key, "status": status, "detail_ar": detail_ar})

    # ── سرّ JWT: موجود، غير الافتراضيّ، ≥32 محرفاً ──
    secret = (env.get("SAHOOL_JWT_SECRET", "") or "").strip()
    strong_secret = (
        bool(secret) and secret != _DEFAULT_DEV_SECRET and len(secret) >= _MIN_SECRET_LEN
    )
    add(
        "jwt_secret_strength",
        strong_secret,
        block_in_prod=True,
        detail_ar=(
            "سرّ JWT قويّ (≥32 محرفاً وغير افتراضيّ)"
            if strong_secret
            else "سرّ JWT ضعيف/مفقود/افتراضيّ — يجب ضبط سرّ عشوائيّ ≥32 محرفاً قبل النشر"
        ),
    )

    # ── RS256: مفتاح عامّ مضبوط (توصية أمنيّة فوق HS256 المشترك) — تحذير لا حجب ──
    has_rs256 = bool((env.get("JWT_PUBLIC_KEY", "") or "").strip())
    add(
        "rs256_public_key",
        has_rs256,
        block_in_prod=False,  # توصية: لا نحجب دون بنية مفاتيح، لكن نوصي بشدّة
        detail_ar=(
            "RS256 مُفعَّل (مفتاح عامّ مضبوط) — توقيع غير متماثل أقوى"
            if has_rs256
            else "يُوصى باعتماد RS256 (ضبط JWT_PUBLIC_KEY) بدل السرّ المشترك HS256 في الإنتاج"
        ),
    )

    # ── تجاوز مصادقة التطوير يجب أن يكون مُطفأً في الإنتاج ──
    dev_auth_off = not _truthy(env.get("SAHOOL_DEV_AUTH"))
    add(
        "dev_auth_disabled",
        dev_auth_off,
        block_in_prod=True,
        detail_ar=(
            "تجاوز مصادقة التطوير مُطفأ"
            if dev_auth_off
            else "SAHOOL_DEV_AUTH مُفعَّل — تجاوز مصادقة خطير في الإنتاج، يجب إطفاؤه"
        ),
    )

    # ── إعادة التحميل/التنقيح يجب أن تكون مُطفأة في الإنتاج ──
    reload_is_dev = (env.get("SAHOOL_ENV", "production") or "").strip().lower() == "development"
    debug_on = _truthy(env.get("SAHOOL_DEBUG")) or (is_prod and reload_is_dev)
    add(
        "no_debug_reload",
        not debug_on,
        block_in_prod=True,
        detail_ar=(
            "وضع التنقيح/إعادة التحميل مُطفأ"
            if not debug_on
            else "وضع التنقيح/إعادة التحميل مُفعَّل — يجب إطفاؤه في الإنتاج"
        ),
    )

    # ── حدّ المعدّل مُفعَّل (>0) — تحذير ──
    try:
        rate = int(env.get("SAHOOL_RATE_LIMIT_PER_MIN", "120"))
    except (TypeError, ValueError):
        rate = 0
    add(
        "rate_limiting_enabled",
        rate > 0,
        block_in_prod=False,
        detail_ar=(
            f"حدّ المعدّل مُفعَّل ({rate}/دقيقة)"
            if rate > 0
            else "حدّ المعدّل مُعطَّل (≤0) — يُوصى بتفعيله لمنع إساءة الاستخدام"
        ),
    )

    # ── قاعدة البيانات مُهيّأة — حجب في الإنتاج (لا منصّة بلا قاعدة) ──
    has_db = bool(
        (env.get("DATABASE_URL", "") or "").strip() or (env.get("POSTGRES_HOST", "") or "").strip()
    )
    add(
        "database_configured",
        has_db,
        block_in_prod=True,
        detail_ar=(
            "قاعدة البيانات مُهيّأة"
            if has_db
            else "لا إعداد قاعدة بيانات (DATABASE_URL/POSTGRES_HOST) — مطلوب للإنتاج"
        ),
    )

    blockers = [c for c in checks if c["status"] == "block"]
    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "ready": (len(blockers) == 0) if is_prod else True,
        "is_production": is_prod,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "note_ar": (
            "الجاهزيّة تُحجَب في الإنتاج إن وُجد أيّ blocker. في التطوير الحرِجُ "
            "يُخفَّض إلى تحذير (ready=True) — السلوك مُعلَن لا مفاجآت."
        ),
    }
