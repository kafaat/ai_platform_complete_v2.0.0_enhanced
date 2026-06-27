#!/usr/bin/env python3
"""
verify_invariants.py — مشغّل manifest الـinvariants لـSAHOOL.

يقرأ invariants.yaml ويشغّل المتحقّقات **الفعليّة** (لا stubs). المستويات
static تُنفَّذ هنا (offline)؛ المستويات live يُبلّغ عنها كـ"تحتاج جهازك"
(postgres حيّ) بدل ادّعاء فحصها.

ليس محرّك DSL عامّاً — مشغّل رفيع يربط الـmanifest بالاختبارات الموجودة.
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
# مسار الاختبارات: scripts_v9/ بجانب tests_v9/ تحت جذر المشروع
_ROOT = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(_ROOT, "tests_v9"))


def _load_manifest():
    """قراءة بسيطة لبنية الطبقات (بلا اعتماد على PyYAML — قد لا يتوفّر)."""
    path = os.path.join(_ROOT, "invariants.yaml")
    if not os.path.exists(path):
        return None
    layers = []
    cur = None
    for line in open(path, encoding="utf-8"):
        s = line.rstrip()
        if s.lstrip().startswith("- id:") and "  - id:" in line[:8] or s.startswith("  - id:"):
            cur = {"id": s.split("id:")[1].strip(), "type": "?", "rules": 0}
            layers.append(cur)
        elif cur is not None and s.strip().startswith("type:"):
            cur["type"] = s.split("type:")[1].strip()
        elif cur is not None and s.strip().startswith("- id:"):
            cur["rules"] += 1
    return layers


def run_static() -> bool:
    """يشغّل المستويات static الفعليّة (L0-L2)."""
    ok = True

    # L0: syntax
    print("═══ L0_SYNTAX — py_compile ═══")
    e = 0
    for root, dirs, files in os.walk(os.path.join(_ROOT, "services")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
        for f in files:
            if f.endswith(".py"):
                try:
                    import py_compile
                    py_compile.compile(os.path.join(root, f), doraise=True)
                except Exception:
                    e += 1
    print(f"  {'✓' if e == 0 else '✗'} {e} خطأ ترجمة")
    ok = ok and e == 0

    # L1: roadmap tests
    print("═══ L1_LOGIC — roadmap (376) ═══")
    sys.path.insert(0, os.path.join(_ROOT, "tests_v9"))
    try:
        import test_roadmap_phase1 as p1
        import test_roadmap_phase23 as p23
        a, b = p1.run_all()
        c, d = p1.run_all2()
        ee, f = p1.run_all3()
        g, h = p23.run_all()
        passed, total = a + c + ee + g, a + c + ee + g + b + d + f + h
        print(f"  {'✓' if passed == total else '✗'} {passed}/{total}")
        ok = ok and passed == total
    except Exception as ex:
        print(f"  ✗ خطأ: {ex}")
        ok = False

    # L2: chaos
    print("═══ L2_FAIL_CLOSED — chaos ═══")
    try:
        import test_chaos_resilience as ch
        p, f = ch.run_all()
        print(f"  {'✓' if f == 0 else '✗'} {p}/{p+f}")
        ok = ok and f == 0
    except Exception as ex:
        print(f"  ✗ خطأ: {ex}")
        ok = False

    return ok


def report_live():
    """يُبلّغ عن المستويات live (لا يدّعي فحصها — تحتاج جهازك)."""
    print("═══ L3_DB_LIVE — يحتاج postgres حيّ (جهازك) ═══")
    print("  ⏳ شغّل: psql ... -f scripts_v9/test_tenant_isolation.sql")
    print("     (كـnon-superuser sahool_user — وإلّا RLS يُتجاوَز)")
    print("═══ FREEZE — بعد نجاح L3 الحيّ ═══")


def main():
    layers = _load_manifest()
    if layers:
        print(f"manifest: {len(layers)} طبقات\n")
    static_ok = run_static()
    print()
    report_live()
    print()
    if static_ok:
        print("✔ STATIC INVARIANTS CLOSED — للحلقة الكاملة: make verify (جهازك)")
        return 0
    print("✗ STATIC INVARIANTS FAILED — أصلح قبل المتابعة")
    return 1


if __name__ == "__main__":
    sys.exit(main())
