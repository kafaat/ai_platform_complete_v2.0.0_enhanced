#!/usr/bin/env python3
"""spatial_flows.py — E2E harness لتدفّقات الخرائط المكانيّة في SAHOOL.

يشغّل التدفّقات المكانيّة الأربعة التي تكشفها الميزات المدموجة (v96 سلامة الهندسة:
سجلّ مراجعات + إبطال كاش + حقول محوريّة + تزامن تفاؤليّ) مقابل **مكدّس حيّ**، يطبع
PASS/FAIL لكلّ خطوة، ويخرج بحالة غير صفريّة عند أيّ فشل. مكتبة قياسيّة فقط (urllib)
— بلا تبعيّات جديدة.

عند تعذّر الوصول للأساس (لا مكدّس حيّ هنا — بصدق) يطبع «SKIPPED (no live stack)»
ويخرج بصفر، فيبقى آمناً في أيّ تشغيل offline/CI.

التدفّقات (مع موضع الكود الحقيقيّ):
  1) رسم/هندسة: إنشاء حقل بمضلّع → تعديل الهندسة → التحقّق من تسجيل مراجعة جديدة في
     ``field_geometry_history`` (عبر GET …/geometry/history) → التحقّق أنّ مضلّعاً غير
     صالح يُرفَض 422 (حارس الهندسة).
       create  : POST  /api/v1/fields                         (routers/fields.py:414)
       edit    : PATCH /api/v1/fields/{id}                    (routers/fields.py:640)
       history : GET   /api/v1/fields/{id}/geometry/history   (routers/fields.py:869)
  2) محوريّ: إنشاء حقل محوريّ (center/radius) → التحقّق أنّ الهندسة مُشتقّة (≥12 رأساً)
     → محاولة PATCH مضلّع خام على الحقل المحوريّ ⇒ 422 ``pivot_polygon_drift_forbidden``
     (api/pivot_geometry.py:116 resolve_pivot_update_geometry).
  3) إبطال راستر: تعديل حدّ الحقل ⇒ إصدار ``FIELD_GEOMETRY_CHANGED`` + تعليم الكاش
     بائتاً (mark_raster_cache_stale). الإصدار جانبيّ غير مقروء مباشرةً عبر REST، فنرصده
     best-effort: نؤكّد أنّ تعديل الهندسة أنتج مراجعة جديدة في السجلّ (الإشارة نفسها
     تُكتب في المعاملة ذاتها — routers/fields.py:837)، ونوثّق ما يُفحَص يدويّاً.
  4) تعارض/offline: PATCH بـ``base_version`` قديم ⇒ 409 (تزامن تفاؤليّ، v61
     routers/fields.py:723).

ملاحظة على المسارات: تُركّب خدمة auth تحت ``/auth/*`` (البوّابة تُمرّر /auth/login).
الافتراض هنا ``LOGIN_PATH=/auth/login`` يطابق المكدّس الحقيقيّ؛ غيّره عبر المتغيّر
لو ركّبت auth خلف بادئة ``/api/v1/auth`` في بوّابتك.

التشغيل:
  docker compose -f docker-compose.v9.yml up -d
  BASE_URL=http://localhost python scripts/e2e/spatial_flows.py
  # أو فصل auth/platform إن لم يكونا خلف بوّابة واحدة:
  AUTH_BASE=http://localhost:8120 API_BASE=http://localhost:8080 \
      python scripts/e2e/spatial_flows.py

المتغيّرات (كلّها اختياريّة، لها افتراضات):
  BASE_URL       الأساس الموحّد لكلتا الخدمتين (افتراض http://localhost).
  AUTH_BASE      أساس خدمة المصادقة (افتراض BASE_URL).
  API_BASE       أساس منصّة sahool (افتراض BASE_URL).
  REGISTER_PATH  افتراض /auth/register   LOGIN_PATH /auth/login   ME_PATH /auth/me
  FIELDS_PATH    افتراض /api/v1/fields
  E2E_EMAIL      بريد التسجيل (افتراض spatial+<طابع زمني>@sahool.ye — فريد لكلّ تشغيل).
  E2E_PASSWORD   كلمة مرور تستوفي السياسة (افتراض Spatial!Pass123).
  E2E_TIMEOUT    مهلة الطلب بالثواني (افتراض 15).
  INSECURE_TLS   "1" لتعطيل تحقّق شهادة TLS (شهادات self-signed محلّيّة).

ليس مربوطاً ببوّابة الوحدات (يتطلّب مكدّساً حيّاً). انظر
tests_v9/test_spatial_e2e_smoke.py (integration) الذي يتخطّى تلقائيّاً حين غياب المكدّس.
"""

from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from json import JSONDecodeError, dumps, loads

_TIMEOUT = float(os.getenv("E2E_TIMEOUT", "15"))

# مضلّع مربّع صغير صالح GeoJSON داخل اليمن (lon,lat) — يحلق (أوّل=آخر).
_VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [44.20, 15.35],
            [44.21, 15.35],
            [44.21, 15.36],
            [44.20, 15.36],
            [44.20, 15.35],
        ]
    ],
}
# مضلّع مُزاح قليلاً (للتعديل) — يبقى داخل اليمن ولا يتداخل ذاتيّاً.
_VALID_POLYGON_EDITED = {
    "type": "Polygon",
    "coordinates": [
        [
            [44.30, 15.45],
            [44.31, 15.45],
            [44.31, 15.46],
            [44.30, 15.46],
            [44.30, 15.45],
        ]
    ],
}
# مضلّع غير صالح: حلقة بنقطتين فقط — يرفضها حارس الهندسة (422).
_INVALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44.20, 15.35], [44.21, 15.36]]],
}
# بارامترات حقل محوريّ canonical (المصدر: مركز/نصف قطر — لا مضلّع مُحرَّر).
_PIVOT_PARAMS = {
    "center": {"lon": 44.50, "lat": 15.50},
    "radius_m": 400.0,
}


def _ssl_context() -> ssl.SSLContext | None:
    if os.getenv("INSECURE_TLS", "").strip().lower() in {"1", "true", "yes", "on"}:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def _safe_json(raw: str) -> dict:
    try:
        parsed = loads(raw)
    except JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_": parsed}


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
    """طلب HTTP بسيط؛ يعيد (الحالة، JSON المُحلَّل أو {}). يرفع عند أخطاء النقل."""
    data = dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(  # noqa: S310 — http(s) فقط من BASE_URL يضبطه المشغّل
        url, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — أعلاه؛ المضيف من بيئة موثوقة محلّيّة
            req, timeout=_TIMEOUT, context=_ssl_context()
        ) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, _safe_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        return e.code, _safe_json(raw or "{}")


def _ok(step: str, detail: str = "") -> None:
    print(f"PASS  {step}" + (f"  — {detail}" if detail else ""))


def _fail(step: str, detail: str) -> None:
    print(f"FAIL  {step}  — {detail}")


def stack_reachable(base: str) -> bool:
    """True لو الأساس استجاب بأيّ شيء (حتى 401/404) ⇒ خدمة حيّة. False لو تعذّر النقل."""
    try:
        urllib.request.urlopen(  # noqa: S310 — http(s) محلّيّ فقط (فحص حيويّة)
            urllib.request.Request(base.rstrip("/") + "/", method="GET"),
            timeout=min(_TIMEOUT, 5),
            context=_ssl_context(),
        )
    except urllib.error.HTTPError:
        return True  # استجاب الخادم (حتى خطأ HTTP) ⇒ المكدّس حيّ
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return True


def _authenticate(auth_base: str, register_path: str, login_path: str) -> str | None:
    """يسجّل مستخدِماً جديداً ثمّ يسجّل دخوله؛ يعيد توكن الوصول أو None عند الفشل."""
    email = os.getenv("E2E_EMAIL", f"spatial+{int(time.time())}@sahool.ye")
    password = os.getenv("E2E_PASSWORD", "Spatial!Pass123")
    status, payload = _request(
        "POST",
        auth_base + register_path,
        body={"email": email, "password": password, "full_name": "Spatial E2E"},
    )
    token = payload.get("access_token")
    if status not in (200, 201) or not token:
        _fail("auth.register", f"status={status} body={payload}")
        return None
    _ok("auth.register", f"status={status} email={email}")
    status, payload = _request(
        "POST", auth_base + login_path, body={"email": email, "password": password}
    )
    token = payload.get("access_token") or token
    if status != 200 or not token:
        _fail("auth.login", f"status={status} body={payload}")
        return None
    _ok("auth.login", f"status={status}")
    return token


def flow_drawing(api_base: str, fields_path: str, token: str) -> tuple[bool, str | None]:
    """التدفّق 1: رسم → تعديل → مراجعة جديدة في السجلّ → رفض مضلّع غير صالح (422)."""
    ok = True
    # 1.a إنشاء حقل بمضلّع صالح.
    status, payload = _request(
        "POST",
        api_base + fields_path,
        token=token,
        body={
            "name": f"Draw E2E {int(time.time())}",
            "crop": "wheat",
            "geometry": _VALID_POLYGON,
        },
    )
    field_id = payload.get("field_id") or payload.get("id")
    if status not in (200, 201) or not field_id:
        _fail("draw.create", f"status={status} body={payload}")
        return False, None
    _ok("draw.create", f"id={field_id}")

    # 1.b تعديل الهندسة (PATCH مضلّع مختلف).
    status, payload = _request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"geometry": _VALID_POLYGON_EDITED},
    )
    if status != 200:
        _fail("draw.edit_geometry", f"status={status} body={payload}")
        ok = False
    else:
        _ok("draw.edit_geometry", f"status={status}")

    # 1.c التحقّق من مراجعة جديدة في field_geometry_history (≥2: إنشاء + تعديل).
    status, payload = _request(
        "GET", f"{api_base}{fields_path}/{field_id}/geometry/history", token=token
    )
    revisions = payload.get("revisions", []) if isinstance(payload, dict) else []
    if status != 200:
        _fail("draw.geometry_history", f"status={status} body={payload}")
        ok = False
    elif len(revisions) < 2:
        _fail("draw.geometry_history", f"توقّعنا ≥2 مراجعة، وجدنا {len(revisions)}: {payload}")
        ok = False
    else:
        _ok("draw.geometry_history", f"revisions={len(revisions)}")

    # 1.d رفض مضلّع غير صالح (حارس الهندسة ⇒ 422).
    status, payload = _request(
        "POST",
        api_base + fields_path,
        token=token,
        body={"name": f"Bad Geom {int(time.time())}", "geometry": _INVALID_POLYGON},
    )
    if status != 422:
        _fail("draw.reject_invalid", f"توقّعنا 422، حصلنا status={status} body={payload}")
        ok = False
    else:
        _ok("draw.reject_invalid", "status=422 (geometry guard)")

    return ok, field_id


def flow_pivot(api_base: str, fields_path: str, token: str) -> bool:
    """التدفّق 2: حقل محوريّ مُشتقّ من center/radius → رفض PATCH مضلّع خام (422 drift)."""
    ok = True
    # 2.a إنشاء حقل محوريّ — الهندسة تُشتقّ من البارامترات في الخادم.
    status, payload = _request(
        "POST",
        api_base + fields_path,
        token=token,
        body={
            "name": f"Pivot E2E {int(time.time())}",
            "crop": "alfalfa",
            "irrigation_type": "pivot",
            "pivot": _PIVOT_PARAMS,
            # هندسة بديل صغيرة؛ الخادم يستبدلها بالمُشتقّ من pivot (canonical).
            "geometry": _VALID_POLYGON,
        },
    )
    field_id = payload.get("field_id") or payload.get("id")
    if status not in (200, 201) or not field_id:
        _fail("pivot.create", f"status={status} body={payload}")
        return False
    geometry = payload.get("geometry") or {}
    ring = (geometry.get("coordinates") or [[]])[0] if isinstance(geometry, dict) else []
    if len(ring) < 12:
        _fail(
            "pivot.derived_geometry",
            f"توقّعنا ≥12 رأساً مُشتقّاً، وجدنا {len(ring)}: {geometry}",
        )
        ok = False
    else:
        _ok("pivot.derived_geometry", f"vertices={len(ring)} (مُشتقّ من center/radius)")

    # 2.b محاولة PATCH مضلّع خام على الحقل المحوريّ (بلا بارامترات) ⇒ 422 drift.
    status, payload = _request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"geometry": _VALID_POLYGON_EDITED},
    )
    detail = payload.get("detail")
    code = detail.get("code") if isinstance(detail, dict) else None
    if status != 422:
        _fail("pivot.reject_raw_polygon", f"توقّعنا 422، حصلنا status={status} body={payload}")
        ok = False
    elif code != "pivot_polygon_drift_forbidden":
        _fail(
            "pivot.reject_raw_polygon",
            f"422 لكن code={code} (توقّعنا pivot_polygon_drift_forbidden)",
        )
        ok = False
    else:
        _ok("pivot.reject_raw_polygon", "status=422 code=pivot_polygon_drift_forbidden")

    return ok


def flow_raster_invalidation(api_base: str, fields_path: str, token: str, field_id: str) -> bool:
    """التدفّق 3: تعديل حدّ ⇒ إشارة إبطال راستر/FieldGeometryChanged رصداً best-effort.

    الإشارة (mark_raster_cache_stale + FIELD_GEOMETRY_CHANGED) جانبيّة تُكتب في معاملة
    تعديل الهندسة نفسها ولا تُقرأ مباشرةً عبر REST. نرصدها best-effort بأنّ تعديل الحدّ
    أنتج مراجعة جديدة (نفس المعاملة)، ونوثّق ما يُفحَص يدويّاً على المكدّس الحيّ.
    """
    status, hist_before = _request(
        "GET", f"{api_base}{fields_path}/{field_id}/geometry/history", token=token
    )
    before = len(hist_before.get("revisions", [])) if status == 200 else 0

    # تعديل الحدّ مجدّداً (عكس الإزاحة) ⇒ يجب أن يُصدِر الإشارة + مراجعة جديدة.
    status, payload = _request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"geometry": _VALID_POLYGON},
    )
    if status != 200:
        _fail("raster.edit_boundary", f"status={status} body={payload}")
        return False

    status, hist_after = _request(
        "GET", f"{api_base}{fields_path}/{field_id}/geometry/history", token=token
    )
    after = len(hist_after.get("revisions", [])) if status == 200 else 0
    if after <= before:
        _fail(
            "raster.invalidation_signal",
            f"لم تُسجَّل مراجعة جديدة بعد تعديل الحدّ (before={before} after={after}) "
            "⇒ إشارة الإبطال غالباً لم تُصدَر.",
        )
        return False
    _ok(
        "raster.invalidation_signal",
        f"مراجعة جديدة (before={before} after={after}); افحص يدويّاً على المكدّس: "
        "events.event_type='FIELD_GEOMETRY_CHANGED' و raster_cache_invalidations "
        "لـ field_id هذا (إصدار جانبيّ غير مقروء عبر REST).",
    )
    return True


def flow_conflict(api_base: str, fields_path: str, token: str, field_id: str) -> bool:
    """التدفّق 4: PATCH بـbase_version قديم ⇒ 409 (تزامن تفاؤليّ، كشف تعديل offline متباعد)."""
    # base_version=1 قديم بالتأكيد بعد عدّة تعديلات سابقة على نفس الحقل.
    status, payload = _request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"name": "Stale Update Attempt", "base_version": 1},
    )
    if status != 409:
        _fail("conflict.stale_base_version", f"توقّعنا 409، حصلنا status={status} body={payload}")
        return False
    _ok("conflict.stale_base_version", "status=409 (optimistic concurrency)")
    return True


def main() -> int:
    base = os.getenv("BASE_URL", "http://localhost").rstrip("/")
    auth_base = os.getenv("AUTH_BASE", base).rstrip("/")
    api_base = os.getenv("API_BASE", base).rstrip("/")
    register_path = os.getenv("REGISTER_PATH", "/auth/register")
    login_path = os.getenv("LOGIN_PATH", "/auth/login")
    fields_path = os.getenv("FIELDS_PATH", "/api/v1/fields")

    print(f"# spatial E2E  auth={auth_base}  api={api_base}")

    # تخطٍّ نظيف بلا مكدّس حيّ — يخرج بصفر (لا فشل offline/CI).
    if not (stack_reachable(auth_base) and stack_reachable(api_base)):
        print("SKIPPED (no live stack)  — تعذّر الوصول للأساس؛ شغّل المكدّس ثمّ أعد المحاولة.")
        return 0

    token = _authenticate(auth_base, register_path, login_path)
    if not token:
        return 1

    results: list[bool] = []

    drawing_ok, field_id = flow_drawing(api_base, fields_path, token)
    results.append(drawing_ok)

    results.append(flow_pivot(api_base, fields_path, token))

    if field_id:
        results.append(flow_raster_invalidation(api_base, fields_path, token, field_id))
        results.append(flow_conflict(api_base, fields_path, token, field_id))
    else:
        _fail("raster.invalidation_signal", "تخطّي — لا field_id من تدفّق الرسم")
        _fail("conflict.stale_base_version", "تخطّي — لا field_id من تدفّق الرسم")
        results.extend([False, False])

    if all(results):
        print("# ALL SPATIAL FLOWS PASSED")
        return 0
    print(f"# FAILED — {sum(1 for r in results if not r)}/{len(results)} flow(s) failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
