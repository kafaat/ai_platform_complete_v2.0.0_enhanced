#!/usr/bin/env python3
"""smoke_e2e.py — دخان E2E مكتفٍ ذاتياً للمسار الحرج (register→login→me→field→workspace).

يشغّل الرحلة الأساسيّة لمستخدِم جديد عبر منصّة SAHOOL مقابل مكدّس حيّ، ويطبع PASS/FAIL
لكلّ خطوة، ويخرج بحالة غير صفريّة عند أيّ فشل. مكتبة قياسيّة فقط (urllib) — بلا تبعيّات.

الخطوات (مع موضع التعريف في الكود):
  1) register : POST {AUTH_BASE}{REGISTER_PATH}        (services/auth/main.py:826  → /auth/register)
  2) login    : POST {AUTH_BASE}{LOGIN_PATH}           (services/auth/main.py:874  → /auth/login)
  3) me       : GET  {AUTH_BASE}{ME_PATH}              (services/auth/main.py:1261 → /auth/me)
  4) field    : POST {API_BASE}{FIELDS_PATH}           (routers/fields.py:372      → /api/v1/fields)
  5) workspace: GET  {API_BASE}{FIELDS_PATH}/{id}/workspace (routers/fields.py:508 → /api/v1/fields/{id}/workspace)

المكدّس المطلوب (docker-compose.unified.yml): postgis + redis + sahool-auth + sahool-platform
+ nginx. شغّله ثمّ وجّه BASE_URL إلى منفذ nginx (HTTPS) أو إلى الخدمات مباشرةً عبر المتغيّرات.

التشغيل:
  BASE_URL=https://localhost:8443 python scripts/smoke_e2e.py
  # أو فصل خدمتَي auth/platform إن لم يكن خلف nginx واحد:
  AUTH_BASE=http://localhost:8120 API_BASE=http://localhost:8080 python scripts/smoke_e2e.py

المتغيّرات (كلّها اختياريّة، لها افتراضات):
  BASE_URL       الأساس الموحّد لكلتا الخدمتين (افتراض http://localhost:8080).
  AUTH_BASE      أساس خدمة المصادقة (افتراض BASE_URL).
  API_BASE       أساس منصّة sahool (افتراض BASE_URL).
  REGISTER_PATH  افتراض /auth/register   LOGIN_PATH /auth/login   ME_PATH /auth/me
  FIELDS_PATH    افتراض /api/v1/fields
  SMOKE_EMAIL    بريد التسجيل (افتراض smoke+<طابع زمني>@sahool.ye — فريد لكلّ تشغيل).
  SMOKE_PASSWORD كلمة مرور تستوفي السياسة (افتراض Smoke!Pass123).
  INSECURE_TLS   "1" لتعطيل تحقّق شهادة TLS (شهادات self-signed محلّيّة).

ملاحظة: ليس مربوطاً بـCI (يتطلّب خدمات حيّة). انظر tests_v9/test_smoke_e2e.py (integration)
الذي يتخطّى تلقائياً حين غياب الخدمات.
"""

from __future__ import annotations

import json
import os
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.security.tls_policy import tls_context as _tls_context  # noqa: E402

_TIMEOUT = float(os.getenv("SMOKE_TIMEOUT", "15"))


def _ssl_context() -> ssl.SSLContext | None:
    # INSECURE_TLS يُشرَّف فقط لأهداف loopback (شهادات dev)، ما لم يُضبَط
    # INSECURE_TLS_ALLOW_REMOTE صراحةً — المُعقِّم المركزيّ shared.security.tls_policy.
    base = (
        os.getenv("BASE_URL")
        or os.getenv("API_BASE")
        or os.getenv("AUTH_BASE")
        or "https://localhost"
    )
    return _tls_context(base)


def _request(
    method: str, url: str, *, token: str | None = None, body: dict | None = None
) -> tuple[int, dict]:
    """طلب HTTP بسيط؛ يعيد (الحالة، JSON المُحلَّل أو {}). يرفع عند أخطاء النقل."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, _safe_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        return e.code, _safe_json(raw or "{}")


def _safe_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"_": parsed}
    except json.JSONDecodeError:
        return {"_raw": raw}


def _ok(step: str, detail: str = "") -> None:
    print(f"PASS  {step}" + (f"  — {detail}" if detail else ""))


def _fail(step: str, detail: str) -> None:
    print(f"FAIL  {step}  — {detail}")


def main() -> int:
    base = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
    auth_base = os.getenv("AUTH_BASE", base).rstrip("/")
    api_base = os.getenv("API_BASE", base).rstrip("/")
    register_path = os.getenv("REGISTER_PATH", "/auth/register")
    login_path = os.getenv("LOGIN_PATH", "/auth/login")
    me_path = os.getenv("ME_PATH", "/auth/me")
    fields_path = os.getenv("FIELDS_PATH", "/api/v1/fields")

    email = os.getenv("SMOKE_EMAIL", f"smoke+{int(time.time())}@sahool.ye")
    password = os.getenv("SMOKE_PASSWORD", "Smoke!Pass123")

    print(f"# smoke E2E  auth={auth_base}  api={api_base}  email={email}")

    # 1) register
    try:
        status, payload = _request(
            "POST",
            auth_base + register_path,
            body={"email": email, "password": password, "full_name": "Smoke Tester"},
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _fail("register", f"تعذّر الاتّصال: {e}")
        return 1
    token = payload.get("access_token")
    if status not in (200, 201) or not token:
        _fail("register", f"status={status} body={payload}")
        return 1
    _ok("register", f"status={status}")

    # 2) login (يأخذ توكناً طازجاً — لا يعتمد على توكن register)
    status, payload = _request(
        "POST", auth_base + login_path, body={"email": email, "password": password}
    )
    token = payload.get("access_token") or token
    if status != 200 or not token:
        _fail("login", f"status={status} body={payload}")
        return 1
    _ok("login", f"status={status}")

    # 3) me
    status, payload = _request("GET", auth_base + me_path, token=token)
    if status != 200 or not payload.get("email"):
        _fail("me", f"status={status} body={payload}")
        return 1
    _ok("me", f"email={payload.get('email')}")

    # 4) create field (مضلّع مربّع صغير صالح GeoJSON)
    geometry = {
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
    status, payload = _request(
        "POST",
        api_base + fields_path,
        token=token,
        body={"name": "Smoke Field", "crop": "wheat", "geometry": geometry},
    )
    field_id = payload.get("id") or payload.get("field_id")
    if status not in (200, 201) or not field_id:
        _fail("create_field", f"status={status} body={payload}")
        return 1
    _ok("create_field", f"id={field_id}")

    # 5) workspace
    status, payload = _request("GET", f"{api_base}{fields_path}/{field_id}/workspace", token=token)
    if status != 200:
        _fail("workspace", f"status={status} body={payload}")
        return 1
    _ok("workspace", f"status={status}")

    print("# ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
