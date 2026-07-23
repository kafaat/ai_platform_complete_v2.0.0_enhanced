#!/usr/bin/env python3
"""live_full_e2e.py — مسار E2E حي كامل لمنصة SAHOOL GIS.

يغطي المسار الإنتاجي الأساسي بدون تبعيات خارجية:
  1) اكتشاف حياة المكدس.
  2) تسجيل/دخول مستخدم اختبار.
  3) إنشاء حقل Polygon.
  4) تعديل الهندسة.
  5) قراءة geometry/history وحساب مقارنة Timeline محلياً.
  6) اختبار تعارض base_version قديم.
  7) رفض هندسة فاسدة.

السلوك الآمن: إن لم توجد بيئة حية، يطبع SKIPPED ويخرج 0 حتى لا يكسر CI offline.
لإجبار الفشل عند غياب البيئة: REQUIRE_LIVE_E2E=1.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request
from json import dumps, loads
from math import isfinite

TIMEOUT = float(os.getenv("E2E_TIMEOUT", "15"))

VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[44.20, 15.35], [44.21, 15.35], [44.21, 15.36], [44.20, 15.36], [44.20, 15.35]]
    ],
}
EDITED_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[44.20, 15.35], [44.215, 15.35], [44.215, 15.365], [44.20, 15.365], [44.20, 15.35]]
    ],
}
INVALID_POLYGON = {"type": "Polygon", "coordinates": [[[44.20, 15.35], [44.21, 15.36]]]}


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.security.tls_policy import tls_context as _tls_context  # noqa: E402


def ssl_context():
    # INSECURE_TLS يُشرَّف فقط لأهداف loopback عبر المُعقِّم المركزيّ (shared.security.tls_policy).
    base = (
        os.getenv("BASE_URL")
        or os.getenv("API_BASE")
        or os.getenv("AUTH_BASE")
        or "https://localhost"
    )
    return _tls_context(base)


def request(method: str, url: str, *, token: str | None = None, body: dict | None = None):
    data = dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl_context()) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8") or "{}"
            try:
                payload = loads(raw)
            except Exception:
                payload = {"_raw": raw}
            return resp.status, payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            payload = loads(raw or "{}")
        except Exception:
            payload = {"_raw": raw}
        return e.code, payload


def reachable(base: str) -> bool:
    try:
        urllib.request.urlopen(
            urllib.request.Request(base.rstrip("/") + "/", method="GET"),
            timeout=min(TIMEOUT, 5),
            context=ssl_context(),
        )  # noqa: S310
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
    return True


def area_degrees2(poly: dict) -> float:
    """Shoelace تقريبي فقط للمقارنة النسبية داخل E2E؛ ليس بديلاً عن PostGIS/Turf."""
    ring = ((poly or {}).get("coordinates") or [[]])[0]
    if len(ring) < 4:
        return 0.0
    acc = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def pass_step(name: str, detail: str = ""):
    print(f"PASS  {name}" + (f" — {detail}" if detail else ""))


def fail_step(name: str, detail: str):
    print(f"FAIL  {name} — {detail}")


def main() -> int:
    base = os.getenv("BASE_URL", "http://localhost").rstrip("/")
    auth_base = os.getenv("AUTH_BASE", base).rstrip("/")
    api_base = os.getenv("API_BASE", base).rstrip("/")
    fields_path = os.getenv("FIELDS_PATH", "/api/v1/fields")
    email = os.getenv("E2E_EMAIL", f"live-full+{int(time.time())}@sahool.ye")
    password = os.getenv("E2E_PASSWORD", "LiveFull!Pass123")

    print(f"# live full E2E auth={auth_base} api={api_base}")
    if not (reachable(auth_base) and reachable(api_base)):
        print("SKIPPED (no live stack)")
        return 1 if os.getenv("REQUIRE_LIVE_E2E") == "1" else 0

    ok = True
    status, payload = request(
        "POST",
        auth_base + os.getenv("REGISTER_PATH", "/auth/register"),
        body={"email": email, "password": password, "full_name": "Live Full E2E"},
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if status not in (200, 201) or not token:
        fail_step("auth.register", f"status={status} body={payload}")
        return 1
    pass_step("auth.register", email)

    status, payload = request(
        "POST",
        auth_base + os.getenv("LOGIN_PATH", "/auth/login"),
        body={"email": email, "password": password},
    )
    token = payload.get("access_token") or token
    if status != 200 or not token:
        fail_step("auth.login", f"status={status} body={payload}")
        return 1
    pass_step("auth.login")

    status, payload = request(
        "POST",
        api_base + fields_path,
        token=token,
        body={
            "name": f"Timeline Full {int(time.time())}",
            "crop": "wheat",
            "geometry": VALID_POLYGON,
        },
    )
    field_id = payload.get("field_id") or payload.get("id") if isinstance(payload, dict) else None
    if status not in (200, 201) or not field_id:
        fail_step("field.create", f"status={status} body={payload}")
        return 1
    pass_step("field.create", f"id={field_id}")

    status, payload = request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"geometry": EDITED_POLYGON},
    )
    if status != 200:
        fail_step("field.patch_geometry", f"status={status} body={payload}")
        ok = False
    else:
        pass_step("field.patch_geometry")

    status, payload = request(
        "GET", f"{api_base}{fields_path}/{field_id}/geometry/history", token=token
    )
    revisions = payload.get("revisions", []) if isinstance(payload, dict) else []
    if status != 200 or len(revisions) < 2:
        fail_step("timeline.history", f"status={status} revisions={len(revisions)} body={payload}")
        ok = False
    else:
        pass_step("timeline.history", f"revisions={len(revisions)}")
        newest = revisions[0].get("geometry") if isinstance(revisions[0], dict) else None
        oldest = revisions[-1].get("geometry") if isinstance(revisions[-1], dict) else None
        delta = area_degrees2(newest) - area_degrees2(oldest)
        if not isfinite(delta):
            fail_step("comparison.area_delta", "non-finite delta")
            ok = False
        else:
            pass_step("comparison.area_delta", f"delta_degrees2={delta:.10f}")

    status, payload = request(
        "PATCH",
        f"{api_base}{fields_path}/{field_id}",
        token=token,
        body={"name": "stale", "base_version": 1},
    )
    if status != 409:
        fail_step("conflict.stale_base_version", f"expected 409 got {status} body={payload}")
        ok = False
    else:
        pass_step("conflict.stale_base_version")

    status, payload = request(
        "POST",
        api_base + fields_path,
        token=token,
        body={"name": "invalid geometry", "geometry": INVALID_POLYGON},
    )
    if status != 422:
        fail_step("geometry.reject_invalid", f"expected 422 got {status} body={payload}")
        ok = False
    else:
        pass_step("geometry.reject_invalid")

    print("# ALL LIVE FULL E2E STEPS PASSED" if ok else "# LIVE FULL E2E FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
