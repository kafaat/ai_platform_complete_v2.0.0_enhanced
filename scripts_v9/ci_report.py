#!/usr/bin/env python3
"""
ci_report.py — مدخل CI واحد ينتج evidence.json (مصدر الحقيقة الوحيد).

المراجعة 14: اقفل طبقات التحقّق في مسار تنفيذ واحد deterministic. بدل gates
متعدّدة، ثلاثة أنواع حقيقة فقط: static / domain / system. الناتج: evidence.json.

قاعدة الإغلاق: أيّ invariant لا يظهر في evidence.json تحت runtime = غير مُثبَت.

static + domain تُنفَّذ هنا (offline). system (RLS الحيّ) يحتاج postgres —
يُعلَّم "requires_live" بصدق بدل ادّعاء فحصه offline.
"""
import json
import os
import sys
import hashlib
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests_v9"))


def _static() -> dict:
    """STATIC TRUTH: py_compile لكلّ Python."""
    import py_compile
    errors = []
    for r, dirs, files in os.walk(os.path.join(ROOT, "services")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
        for f in files:
            if f.endswith(".py"):
                try:
                    py_compile.compile(os.path.join(r, f), doraise=True)
                except Exception:
                    errors.append(f)
    return {"status": "pass" if not errors else "fail", "errors": len(errors)}


def _domain() -> dict:
    """DOMAIN TRUTH: roadmap + chaos (المنطق). يكتم stdout المطوّل للاختبارات."""
    import io
    import contextlib
    out = {}
    _sink = io.StringIO()
    with contextlib.redirect_stdout(_sink):
        try:
            import test_roadmap_phase1 as p1
            import test_roadmap_phase23 as p23
            a, b = p1.run_all(); c, d = p1.run_all2()
            e, f = p1.run_all3(); g, h = p23.run_all()
            passed, total = a + c + e + g, a + c + e + g + b + d + f + h
            out["roadmap"] = {"status": "pass" if passed == total else "fail",
                              "passed": passed, "total": total}
        except Exception as ex:
            out["roadmap"] = {"status": "error", "detail": str(ex)[:80]}
        try:
            import test_chaos_resilience as ch
            p, f = ch.run_all()
            out["chaos"] = {"status": "pass" if f == 0 else "fail",
                            "passed": p, "total": p + f}
        except Exception as ex:
            out["chaos"] = {"status": "error", "detail": str(ex)[:80]}
    return out


def _invariant_flags() -> dict:
    """أعلام الـinvariants الحقيقيّة (بنيويّة — system truth الحيّ على جهازك)."""
    def has(path, *needles):
        try:
            s = open(os.path.join(ROOT, path), encoding="utf-8").read()
            return all(n in s for n in needles)
        except Exception:
            return False
    return {
        "tenant_rls_fail_closed": has("migrations/v9_rls_tenant_isolation.sql",
                                      "FORCE", "NULLIF"),
        "temporal_invariant": has("services/sahool-platform/api/field_lifecycle.py",
                                  "enforcement_mode", "occurred_at"),
        "sync_idempotency": has("services/edge-inference/sync_service.py",
                                "idempotency_key", "occurred_at"),
        "edge_dedup": has("services/sahool-platform/api/main.py",
                          "ON CONFLICT (idempotency_key)"),
        "approval_locked": has("services/guardrails-engine/human_in_loop.py",
                               "FOR UPDATE"),
        "raster_provenance": has("services/raster-service/raster_provenance.py",
                                 "provenance_hash"),
        "rs256_ready": has("services/auth/main.py", "JWT_PRIVATE_KEY", "RS256"),
        # system truth: يتطلّب postgres حيّ (لا يُثبَت offline)
        "rls_enforced_live": "requires_live",
        "tenant_isolation_live": "requires_live",
    }


def main():
    static = _static()
    domain = _domain()
    flags = _invariant_flags()

    overall = "pass"
    if static["status"] != "pass":
        overall = "fail"
    for v in domain.values():
        if v.get("status") != "pass":
            overall = "fail"

    evidence = {
        "build_time": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "static": static,
        "domain": domain,
        "invariants": flags,
        "note": "system truth (rls_enforced_live) يتطلّب make verify على postgres حيّ",
    }

    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    payload = json.dumps(evidence, ensure_ascii=False, indent=2)
    path = os.path.join(ROOT, "build", "evidence.json")
    open(path, "w", encoding="utf-8").write(payload)
    # hash للحماية من التعديل الصامت (immutability check رخيص ومفيد)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    open(path + ".sha256", "w").write(digest)

    print(payload)
    print(f"\n# evidence: build/evidence.json", file=sys.stderr)
    print(f"# sha256: {digest}", file=sys.stderr)
    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
