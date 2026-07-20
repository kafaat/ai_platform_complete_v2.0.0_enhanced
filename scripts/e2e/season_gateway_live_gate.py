#!/usr/bin/env python3
"""بوّابة برهان حيّة لبوّابة إدخال الموسم (SEASON-RECORD-ENTRY-01، المهمّة #225).

تُثبِت حدّ الثقة الإنتاجيّ الذي لا يعطيه أيّ اختبار وحدة (يحتاج nginx+auth+scout-ingest حيّة):

  المتصفّح ─► nginx /api/v1/seasons/{id}/accept ─► auth_request /_auth_edge_sign
            (auth يوقّع HMAC مقيَّد الوجهة) ─► scout-ingest accept (يعيد الحساب من طلبه هو)

البراهين الثلاثة (من runbooks/season-record-entry.md §3):
  (أ) ترويسات هويّة/تصديق/قانونيّة **مزوَّرة** من العميل بلا جلسة مُراجِع ⇒ **401** (التزوير مطموس؛
      لا توقيع صالح لهذا الطلب) — البرهان السلبيّ الأساسيّ.
  (ب) مُراجِع شرعيّ (owner/expert) يقبل موسمه ⇒ **200** (المسار السعيد حيًّا) — يُحوّل الموسم accepted.
  (ج) إعادة القبول على موسم مقبول ⇒ **409** `season_already_accepted` (لا قبول مزدوج).

⚠ تحذير: البرهان (ب) **يُحوّل** الموسم إلى accepted (لا رجعة — سجلّ append-only). استخدم موسم مسودّة
مخصَّصاً للاختبار. تشغيل واحد لكلّ SID.

البيئة:
  SEASON_BASE_URL=https://staging.sahool.ye     أصل البوّابة (nginx)
  SEASON_COOKIE="sahool_at=<جلسة owner/expert صالحة>"   كوكي جلسة المُراجِع (للبرهانَين ب/ج)
  SEASON_SID=<uuid موسم مسودّة بمرفق دفتر جاهز للقبول>

الخروج: 0 إن نجحت البراهين الثلاثة؛ غير-صفر مع تشخيص إن فشل أيّ منها.
TLS: يتحقّق افتراضاً؛ INSECURE_TLS=1 يعطّل التحقّق **فقط لأهداف loopback** (شهادات dev)،
وإلّا يبقى التحقّق مُفعَّلاً (لا تعطيل صامت ضد مضيف بعيد).
"""

from __future__ import annotations

import os
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

BASE = os.getenv("SEASON_BASE_URL", "https://localhost").rstrip("/")

_TRUE = {"1", "true", "yes", "on"}
_LOOPBACK = {"localhost", "127.0.0.1", "::1", ""}


def _tls_context(base_url: str) -> ssl.SSLContext | None:
    """سياق TLS: http⇒None · https loopback+INSECURE_TLS⇒بلا تحقّق · https غير ذلك⇒تحقّق."""
    if not base_url.lower().startswith("https://"):
        return None
    host = (urlparse(base_url).hostname or "").lower()
    insecure = os.getenv("INSECURE_TLS", "").strip().lower() in _TRUE
    if insecure and (host in _LOOPBACK or host.endswith(".localhost")):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


COOKIE = os.getenv("SEASON_COOKIE", "").strip()
SID = os.getenv("SEASON_SID", "").strip()
_TIMEOUT = float(os.getenv("SEASON_TIMEOUT", "15"))


def _post_accept(*, cookie: str | None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    """POST /api/v1/seasons/{SID}/accept — يعيد (رمز الحالة، جسم مقتطع للتشخيص)."""
    url = f"{BASE}/api/v1/seasons/{SID}/accept"
    req = urllib.request.Request(url, method="POST", data=b"")
    if cookie:
        req.add_header("Cookie", cookie)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_tls_context(BASE)) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "replace")
    except urllib.error.URLError as e:
        return 0, f"URLError: {e.reason}"


def _report(name: str, ok: bool, got: int, want: str, body: str) -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}: got HTTP {got}, expected {want}")
    if not ok and body:
        print(f"       body: {body.strip()[:200]}")
    return ok


def main() -> int:
    if not SID:
        print("SEASON_SID is required (uuid of a draft season with a logbook attachment).")
        return 2
    if not COOKIE:
        print("SEASON_COOKIE is required (a valid owner/expert session cookie) for proofs (ب)/(ج).")
        return 2

    print(f"── SEASON gateway live proofs — BASE={BASE} SID={SID} ──")
    results: list[bool] = []

    # (أ) البرهان السلبيّ: ترويسات مزوَّرة + بلا جلسة مُراجِع ⇒ 401 (fail-closed).
    forged = {
        "X-Canonical-Path": "/internal/seasons/OTHER/accept",
        "X-User-Id": "attacker",
        "X-Roles": "owner,season-reviewer",
        "X-Edge-Attestation": "deadbeef",
        "X-Edge-Timestamp": "9999999999",
    }
    code_a, body_a = _post_accept(cookie=None, headers=forged)
    # المطلوب fail-closed: 401 (أو 403) — المرفوض هو 200/قبول.
    ok_a = code_a in (401, 403)
    results.append(
        _report("(أ) forged headers, no reviewer session ⇒ deny", ok_a, code_a, "401/403", body_a)
    )
    if code_a == 200:
        print(
            "       ⚠ CRITICAL: forged/unauthenticated accept SUCCEEDED — edge attestation NOT enforced."
        )

    # (ب) المسار السعيد: مُراجِع شرعيّ يقبل موسمه ⇒ 200.
    code_b, body_b = _post_accept(cookie=COOKIE)
    ok_b = code_b == 200
    results.append(_report("(ب) reviewer accepts own draft ⇒ 200", ok_b, code_b, "200", body_b))
    _hint(code_b, body_b)

    # (ج) القبول المزدوج: إعادة القبول ⇒ 409 season_already_accepted.
    code_c, body_c = _post_accept(cookie=COOKIE)
    ok_c = code_c == 409
    results.append(
        _report("(ج) double-accept ⇒ 409 season_already_accepted", ok_c, code_c, "409", body_c)
    )

    passed = all(results)
    print(
        f"── {'ALL PROOFS PASSED ✅' if passed else 'SOME PROOFS FAILED ❌'} "
        f"({sum(results)}/{len(results)}) ──"
    )
    if passed:
        print(
            "Next: mark SEASON-EDGE-LIVE-PROOF ✅ on the owner runbook at the staging SHA, "
            "close the gap in gaps/registry.md, and close task #225."
        )
    return 0 if passed else 1


def _hint(code: int, body: str) -> None:
    """تلميحات تشخيص من جدول استكشاف الأعطال في الرنبوك."""
    b = body.lower()
    if code == 404:
        print("       hint: /api/v1/seasons 404 ⇒ SEASON_ENTRY_ENABLED != 1 on scout-ingest.")
    elif code == 503 and "edge signing not configured" in b:
        print("       hint: SEASON_EDGE_HMAC_KEY not set in auth (Category-B secret).")
    elif code == 503 and "service_token" in b:
        print("       hint: SEASON_ENTRY_SERVICE_TOKEN not set on scout-ingest (must match nginx).")
    elif code == 401 and "edge_unattested" in b:
        print("       hint: SEASON_EDGE_HMAC_KEY mismatch between auth and scout-ingest.")
    elif code == 403 and "reviewer_role_required" in b:
        print("       hint: user is not owner/expert (admin is deliberately excluded).")


if __name__ == "__main__":
    raise SystemExit(main())
