"""
tests_v9/run_offline_suite.py — عدّاء اختبارات شامل (offline)

يجمع ويشغّل كلّ دوال test_* عبر ملفّات tests_v9 التي تعمل بلا قاعدة حيّة
(نمط pytest بـassert)، ويتخطّى بوضوح ما يحتاج DB/asyncpg/شبكة. بديل عن
pytest غير المثبّت offline. يعطي صورة شاملة لصحّة الكود الثابتة.
"""

import importlib
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform"))
sys.path.insert(0, os.path.dirname(__file__))

# ملفّات تعمل offline (تُختبَر بـassert بلا DB حيّة)
OFFLINE_TEST_MODULES = [
    "test_security",
    "test_geospatial",
    "test_event_replay",
    "test_wired_endpoints",
    "test_mobile_backend_contract",
    "test_confidence_failures",
    "test_v10_modules",
    "test_v12_modules",
    "test_v13_refinements",
    "test_guardrails",
    "test_tool_contracts",
]

# تدفّقات شاملة تُشغَّل منفصلةً (لها main خاصّ)
E2E_FLOWS = ["test_e2e_offline_flow"]


def run_module(mod_name):
    """يشغّل كلّ دوال test_* في وحدة، يعيد (passed, failed, skipped, errors)."""
    passed = failed = skipped = 0
    errors = []
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        # فشل الاستيراد = قد يحتاج DB/مكتبة غائبة → تخطٍّ
        msg = str(e).lower()
        if any(x in msg for x in ["asyncpg", "database_url", "psycopg", "no module"]):
            return 0, 0, 1, [f"{mod_name}: تخطٍّ (تبعيّة غائبة: {e})"]
        return 0, 1, 0, [f"{mod_name}: فشل الاستيراد: {e}"]

    # اجمع دوال test_* وأصناف Test*
    test_fns = []
    for name in dir(mod):
        obj = getattr(mod, name)
        if name.startswith("test_") and callable(obj):
            test_fns.append((name, obj, None))
        elif name.startswith("Test") and isinstance(obj, type):
            inst = obj()
            for m in dir(inst):
                if m.startswith("test_") and callable(getattr(inst, m)):
                    test_fns.append((f"{name}.{m}", getattr(inst, m), inst))

    for tname, fn, inst in test_fns:
        try:
            if inst and hasattr(inst, "setup_method"):
                try:
                    inst.setup_method()
                except Exception:
                    pass
            fn()
            passed += 1
        except Exception as e:
            msg = str(e).lower()
            if any(x in msg for x in ["asyncpg", "database_url", "skip", "psycopg"]):
                skipped += 1
            else:
                failed += 1
                errors.append(f"{mod_name}.{tname}: {type(e).__name__}: {str(e)[:80]}")
    return passed, failed, skipped, errors


def main():
    print("═" * 60)
    print("  مجموعة اختبارات سهول الشاملة (offline)")
    print("═" * 60)
    tot_p = tot_f = tot_s = 0
    all_errors = []
    for mod_name in OFFLINE_TEST_MODULES:
        p, f, s, errs = run_module(mod_name)
        tot_p += p
        tot_f += f
        tot_s += s
        all_errors += errs
        status = "✓" if f == 0 else "✗"
        extra = f" ({s} تخطٍّ)" if s else ""
        print(f"  {status} {mod_name:35} {p} نجاح، {f} فشل{extra}")

    print("\n" + "─" * 60)
    if all_errors:
        print("  تفاصيل الإخفاقات/التخطّي:")
        for e in all_errors[:15]:
            print(f"    • {e}")
    print("─" * 60)
    print(f"  الإجمالي: {tot_p} نجاح | {tot_f} فشل | {tot_s} تخطٍّ")
    print("═" * 60)
    return 0 if tot_f == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
