#!/usr/bin/env python3
"""tools/sahool_inspector.py — Sahool Inspector: فاحص الجاهزية التشغيليّة (ساكن).

أداة قابلة للتشغيل تكشف الفجوات البنيويّة الحقيقيّة في المنصّة **دون تشغيل الخدمات** —
تُكمّل اختبارات الوحدة (التي تثبت منطقاً) بفحص تكامل النظام (هل يعمل كنظام موحّد؟).
كلّ فحص يُصدِر PASS / WARN / FAIL مع أدلّة `file:line`، والمحصّلة الإجماليّة + رمز خروج
(0 لـPASS/WARN، 1 لأيّ FAIL) — صالحة لـCI ولبيئة المطوّر.

الفحوصات الساكنة (تعمل هنا بلا docker):
  1. RLS coverage      — كلّ جدول بمستأجِر له ENABLE+FORCE + سياسة current_setting.
  2. router wiring      — لا راوتر يتيم (مُستورَد + مُضمَّن في main).
  3. NATS subjects      — بادئة sahool.، وكشف المواضيع اليتيمة (نشر بلا اشتراك/عكسه).
  4. endpoint authz     — كلّ نقطة /api/v1 لها تبعيّة مصادقة/تفويض.
  5. migration manifest — تطابق ملفّات الهجرات مع MANIFEST، وترقيم متّسق.

الفحوصات الحيّة (محجوزة لبيئتك — تتطلّب الخدمات قيد التشغيل): انظر LIVE_CHECKS أدناه.
تُطبَع كـSKIPPED مع توضيح أنّها تتطلّب docker/الخدمات — صدقاً لا نزعم PASS لما لم يُشغَّل.

الاستخدام:
    python tools/sahool_inspector.py            # تقرير نصّيّ + رمز خروج
    python tools/sahool_inspector.py --json      # JSON للأتمتة
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "migrations"
ROUTERS = REPO / "services" / "sahool-platform" / "api" / "routers"
MAIN = REPO / "services" / "sahool-platform" / "api" / "main.py"
SERVICES = REPO / "services"

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# الفحوصات الحيّة المؤجَّلة لبيئة التشغيل (لا تُشغَّل ساكناً — صدقاً لا PASS مزيّف).
LIVE_CHECKS = (
    "User→nginx→Service→DB (تنفيذ تدفّق حقيقيّ)",
    "تدفّق رسائل NATS وقت التشغيل (نشر/استهلاك فعليّ)",
    "RLS فعليّاً على Postgres حيّ (محاولة تسرّب بين مستأجِرين)",
    "Replay Determinism (إعادة بناء الحالة من الأحداث ومطابقتها)",
    "رحلة الإشعار حتّى موبايل Flutter",
)


@dataclass
class Result:
    name: str
    status: str
    summary: str
    findings: list[str] = field(default_factory=list)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _lineno(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


# ════════════════════════════════════════════════════════════
# 1. RLS coverage — الجداول المُضافة بعد «propagate» يجب أن تحمل RLS صريحاً
# ════════════════════════════════════════════════════════════
# ملاحظة صدق: RLS الأساسيّ يُطبَّق عبر دالّة مساعِدة (_sahool_apply_tenant_rls) و«propagate»
# في v70 على *كلّ* جداول المستأجِر ديناميكيّاً — لا يُحلّ ساكناً. التحقّق السلطويّ الكامل
# هو Integration Tests (قاعدة حيّة + test_tenant_policy_uses_current_setting). هنا نلتقط
# الخطر الساكن الحقيقيّ فقط: جدول مستأجِر يُنشَأ في هجرة **بعد** propagate بلا RLS صريح
# خاصّ به (لن يغطّيه propagate الذي جرى سابقاً).
def _manifest_order() -> list[str]:
    man = _read(MIGRATIONS / "MANIFEST.txt")
    return [ln.strip() for ln in man.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def check_rls_coverage() -> Result:
    order = _manifest_order()
    propagate_idx = next((i for i, f in enumerate(order) if "rls" in f and "propagate" in f), None)
    create_re = re.compile(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\n\)", re.S | re.I)
    findings: list[str] = []
    propagate_note = (
        "RLS الأساسيّ عبر helper + propagate (v70) على كلّ جداول المستأجِر — "
        "التحقّق السلطويّ في Integration Tests."
    )
    if propagate_idx is None:
        return Result("RLS coverage", WARN, "لم يُعثَر على آليّة propagate — تحقّق يدويّ مطلوب", [])

    checked_after = 0
    for fname in order[propagate_idx + 1 :]:
        sql = _read(MIGRATIONS / fname)
        new_tenant_tables = [
            t for t, body in create_re.findall(sql) if re.search(r"\btenant_id\b", body)
        ]
        for t in new_tenant_tables:
            checked_after += 1
            has_force = bool(re.search(r"FORCE ROW LEVEL SECURITY", sql))
            has_cs = "current_setting" in sql
            if not (has_force and has_cs):
                miss = []
                if not has_force:
                    miss.append("FORCE")
                if not has_cs:
                    miss.append("current_setting policy")
                findings.append(
                    f"CRITICAL جدول `{t}` (في {fname}، بعد propagate) بلا RLS صريح: {', '.join(miss)} مفقود"
                )

    status = FAIL if findings else PASS
    summary = (
        f"{propagate_note} فُحِص {checked_after} جدول مستأجِر مُضاف بعد propagate؛ "
        f"{len(findings)} بلا RLS صريح"
    )
    return Result("RLS coverage", status, summary, findings)


# ════════════════════════════════════════════════════════════
# 2. router wiring — لا راوتر يتيم
# ════════════════════════════════════════════════════════════
def check_router_wiring() -> Result:
    # التسجيل مُستخرَج إلى api/router_registry.py (register_routers) ويُستدعى من main.py.
    # نقرأ كليهما معاً: الحلقة/الاستثناء/التضمين الصريح صارت في router_registry.
    main_src = _read(MAIN)
    registry = MAIN.parent / "router_registry.py"
    wiring_src = main_src + "\n" + (_read(registry) if registry.exists() else "")
    findings: list[str] = []
    names = sorted(p.stem for p in ROUTERS.glob("*.py") if p.name != "__init__.py")

    # التسجيل التلقائيّ (auto-registration): تُضمَّن كلّ وحدة في api/routers/ عبر حلقة
    # pkgutil.iter_modules + app.include_router (في router_registry، يستدعيها main.py عبر
    # register_routers). عند وجوده، تُعدّ كلّ وحدة مُضمَّنة آليّاً عدا ما في الاستثناء.
    auto_reg = bool(
        re.search(r"iter_modules\(\s*_routers_pkg\.__path__", wiring_src)
        and re.search(r"app\.include_router\(\s*_?router_obj", wiring_src)
        and re.search(r"register_routers\s*\(\s*app\s*\)", main_src)
    )
    excl_match = re.search(r"_?ROUTER_AUTOREG_EXCLUDE\s*=\s*\{([^}]*)\}", wiring_src)
    excluded = set(re.findall(r'"(\w+)"', excl_match.group(1))) if excl_match else set()

    for name in names:
        if auto_reg and name not in excluded:
            continue  # مُضمَّن آليّاً عبر حلقة التسجيل
        # نمط واعٍ بالتعليقات والالتفاف متعدّد الأسطر (مطابق لحارس التفكيك):
        #   from api.routers.<name> import (  «تعليق E402»\n    router as <alias>,\n)
        imp = re.search(
            rf"from api\.routers\.{re.escape(name)} import\s*\(?[ \t]*(?:#[^\n]*)?\s*router as (\w+)",
            wiring_src,
        )
        if not imp:
            findings.append(f"HIGH راوتر يتيم: `{name}` غير مُستورَد (main/router_registry)")
            continue
        alias = imp.group(1)
        if not re.search(rf"app\.include_router\(\s*{re.escape(alias)}\b", wiring_src):
            findings.append(f"HIGH راوتر مُستورَد بلا include: `{name}` ({alias})")
    status = FAIL if findings else PASS
    return Result("router wiring", status, f"{len(names)} راوتر؛ {len(findings)} مشكلة", findings)


# ════════════════════════════════════════════════════════════
# 3. NATS subjects — بادئة sahool. + المواضيع اليتيمة
# ════════════════════════════════════════════════════════════
def check_nats_subjects() -> Result:
    pub_re = re.compile(r'\.publish\(\s*["\']([^"\']+)["\']')
    sub_re = re.compile(r'\.subscribe\(\s*["\']([^"\']+)["\']')
    published: dict[str, str] = {}
    subscribed: dict[str, str] = {}
    for py in SERVICES.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        src = _read(py)
        rel = py.relative_to(REPO)
        for m in pub_re.finditer(src):
            published.setdefault(m.group(1), f"{rel}:{_lineno(src, m.start())}")
        for m in sub_re.finditer(src):
            subscribed.setdefault(m.group(1), f"{rel}:{_lineno(src, m.start())}")

    findings: list[str] = []
    # بادئة sahool. (نتجاهل القوالب ذات المتغيّرات؛ نفحص الحرفيّة فقط)
    for subj, loc in sorted({**published, **subscribed}.items()):
        if not subj.startswith("sahool.") and "." in subj and " " not in subj:
            findings.append(f"CRITICAL موضوع بلا بادئة sahool.: `{subj}` ({loc})")

    # يتيمة: نشر بلا اشتراك (تجاهل القوالب بالـ* والمتغيّرات)
    def _concrete(s: str) -> bool:
        return s.startswith("sahool.") and "*" not in s and ">" not in s

    for subj, loc in sorted(published.items()):
        if _concrete(subj) and subj not in subscribed:
            findings.append(f"WARN موضوع منشور بلا مشترِك (حدث طريق مسدود): `{subj}` ({loc})")
    status = (
        FAIL if any(f.startswith("CRITICAL") for f in findings) else (WARN if findings else PASS)
    )
    summary = f"{len(published)} منشور / {len(subscribed)} مُشترَك؛ {len(findings)} ملاحظة"
    return Result("NATS subjects", status, summary, findings)


# ════════════════════════════════════════════════════════════
# 4. endpoint authz — كلّ نقطة لها تبعيّة مصادقة/تفويض
# ════════════════════════════════════════════════════════════
def check_endpoint_authz() -> Result:
    # صدق الخطورة: نقطة عامّة بلا مصادقة تحسب بيانات مرجعيّة نقيّة (أمثال/أقاليم) ليست
    # ثغرة بحدّ ذاتها. الخطر الحقيقيّ = نقطة **تمسّ قاعدة/مستأجِر** بلا مصادقة (تسرّب).
    findings: list[str] = []  # HIGH فقط (تمسّ قاعدة/مستأجِر)
    info: list[str] = []  # عامّة نقيّة (للعلم لا للإخفاق)
    total = 0
    db_markers = (
        "tenant_connection",
        "get_pool",
        "conn.",
        "await conn",
        ".fetch",
        ".execute",
        "_DB_POOL",
    )
    ep_re = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']', re.S)
    body_re = re.compile(r"\n(async def|def)\s+(\w+)\s*\((.*?)\)\s*:(.*?)(?=\n@router\.|\Z)", re.S)
    for py in sorted(ROUTERS.glob("*.py")):
        if py.name == "__init__.py":
            continue
        src = _read(py)
        rel = py.relative_to(REPO)
        decorators = list(ep_re.finditer(src))
        bodies = list(body_re.finditer(src))
        for dm in decorators:
            method, path = dm.group(1), dm.group(2)
            total += 1
            # طابِق جسم الدالّة التالي للديكور
            body = next((b for b in bodies if b.start() > dm.start()), None)
            if body is None:
                continue
            sig, fnbody = body.group(3), body.group(4)
            fn = body.group(2)
            has_auth = "get_current_user" in sig or "require_permission" in sig
            if has_auth:
                continue
            # الخطر الحقيقيّ = وصول قاعدة فعليّ في الجسم؛ وجود وسيط field_id وحده لا يكفي
            # (نقاط حسابيّة نقيّة تأخذ field_id كوسم فقط — تحقّقنا: field/operational-state).
            touches_db = any(mk in sig + fnbody for mk in db_markers)
            loc = f"{rel}:{_lineno(src, dm.start())} — {fn}"
            if touches_db:
                findings.append(
                    f"HIGH نقطة تمسّ قاعدة/مستأجِر بلا مصادقة: {method.upper()} {path} ({loc})"
                )
            else:
                info.append(
                    f"INFO نقطة عامّة (بيانات مرجعيّة نقيّة) بلا مصادقة: {method.upper()} {path} ({loc})"
                )
    status = FAIL if findings else (WARN if info else PASS)
    summary = (
        f"{total} نقطة؛ {len(findings)} تمسّ قاعدة/مستأجِر بلا مصادقة (خطر)، "
        f"{len(info)} عامّة نقيّة بلا مصادقة (للعلم)"
    )
    # نُظهِر HIGH أوّلاً ثمّ عيّنة من INFO (لا نُغرِق).
    return Result("endpoint authz", status, summary, findings + info[:8])


# ════════════════════════════════════════════════════════════
# 5. migration manifest — تطابق الملفّات مع MANIFEST
# ════════════════════════════════════════════════════════════
def check_migration_manifest() -> Result:
    manifest = _read(MIGRATIONS / "MANIFEST.txt")
    listed = {
        ln.strip() for ln in manifest.splitlines() if ln.strip() and not ln.strip().startswith("#")
    }
    # ملفّات *.down.sql نصوص تراجع (rollback) — لا تُدرَج في MANIFEST الأماميّ عمداً.
    on_disk = {p.name for p in MIGRATIONS.glob("*.sql") if not p.name.endswith(".down.sql")}
    findings: list[str] = []
    for missing in sorted(on_disk - listed):
        findings.append(f"HIGH هجرة على القرص بلا إدراج في MANIFEST: `{missing}`")
    for ghost in sorted(listed - on_disk):
        findings.append(f"CRITICAL إدراج في MANIFEST بلا ملفّ: `{ghost}`")
    status = FAIL if findings else PASS
    summary = f"{len(on_disk)} ملفّ / {len(listed)} مُدرَج؛ {len(findings)} تباين"
    return Result("migration manifest", status, summary, findings)


CHECKS = (
    check_rls_coverage,
    check_router_wiring,
    check_nats_subjects,
    check_endpoint_authz,
    check_migration_manifest,
)


def run() -> tuple[list[Result], str]:
    results = [c() for c in CHECKS]
    overall = (
        FAIL
        if any(r.status == FAIL for r in results)
        else (WARN if any(r.status == WARN for r in results) else PASS)
    )
    return results, overall


def _print_text(results: list[Result], overall: str) -> None:
    icon = {PASS: "✅", WARN: "⚠️ ", FAIL: "❌", SKIP: "⏭️ "}
    print("═" * 64)
    print("  Sahool Inspector — فحص الجاهزية التشغيليّة (ساكن)")
    print("═" * 64)
    for r in results:
        print(f"\n{icon[r.status]} [{r.status}] {r.name} — {r.summary}")
        for f in r.findings:
            print(f"      • {f}")
    print("\n" + "─" * 64)
    print("  فحوصات حيّة محجوزة لبيئتك (تتطلّب الخدمات قيد التشغيل):")
    for lc in LIVE_CHECKS:
        print(f"   {icon[SKIP]}[SKIP] {lc}")
    print("─" * 64)
    print(f"\n  المحصّلة الإجماليّة: {icon[overall]} {overall}\n")


def main(argv: list[str]) -> int:
    results, overall = run()
    if "--json" in argv:
        print(
            json.dumps(
                {
                    "overall": overall,
                    "checks": [vars(r) for r in results],
                    "live_checks_skipped": list(LIVE_CHECKS),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_text(results, overall)
    return 1 if overall == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
