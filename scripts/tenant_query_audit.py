#!/usr/bin/env python3
"""scripts/tenant_query_audit.py — تعداد شامل لاستعلامات القاعدة وتصنيف عزلها.

ينتقل من «فحصتُ عيّنة» إلى «كلّ استعلام محسوب»: يَمسح **كلّ** موقع نداء قاعدة
(execute/fetch/fetchrow/fetchval) في كلّ الخدمات، يستخرج الجداول المُشار إليها، ويصنّف
كلّ استعلام يلمس **جدولاً مُستأجَراً** (يحوي tenant_id) حسب طريقة ضبط سياق العزل:

  • RLS_CONN   — داخل دالّة تستعمل tenant_connection/tenant_connection_for ⇒ RLS مضبوط.
  • EXPLICIT   — الدالّة تضبط app.current_tenant صراحةً (set_config) ⇒ سياق صريح.
  • RAW        — لا هذا ولا ذاك ⇒ يعتمد على fail-closed (تحت NOBYPASSRLS يُرجِع صفر
                 صفوف بلا سياق) — يجب أن يكون عمداً (نظام/تعداد عابر) ومُدرَجاً في
                 الـallowlist، وإلّا فهو إمّا تسرّب محتمل (لو الدور يتجاوز RLS) أو عطل صامت.
  • GLOBAL     — الجدول غير مُستأجَر (لا tenant_id) ⇒ خارج نطاق العزل.

التصنيف نقيّ (تحليل نصّيّ، لا تشغيل). يُستعمَل لتوليد جدول الأدلّة + كبوّابة CI: أيّ
استعلام RAW جديد على جدول مُستأجَر خارج الـallowlist يُرصَد.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIG = ROOT / "migrations"
SCAN = ("services",)

_CALL = re.compile(r"\.(?:execute|executemany|fetch|fetchrow|fetchval)\s*\(")
_TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_]\w*)", re.I)
_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+\w+")

# مواقع RAW مُتحقَّقة فرديّاً (تعداد عزل المستأجرين الشامل) — كلٌّ مُبرَّر بفئته. المفتاح
# "ملفّ::جدول". أيّ مفتاح جديد (استعلام raw جديد على جدول مُستأجَر) يُفشِل البوّابة حتى
# يُصنَّف هنا أو يُحوَّل إلى tenant_connection. التبرير لكلّ فئة:
_ALLOWLIST_JUSTIFIED: dict[str, str] = {
    # خدمة الهويّة (الجذر): تبحث users بالبريد/المعرّف **قبل/عبر** سياق المستأجِر (تسجيل
    # دخول، إعادة كلمة مرور، إدارة admin). عالميّة بالتصميم — لا سياق مستأجِر عند الهويّة.
    "services/auth/main.py::users": "auth identity-root: global user lookup pre-tenant",
    # موافقة الخبراء المركزيّة: تعمل بـworkflow_id (UUID غير قابل للتخمين) + دور expert/admin
    # (دور عابر مركزيّ بالتصميم). العزل بالقدرة (المعرّف) + الصلاحيّة، لا بـRLS.
    "services/guardrails-engine/human_in_loop.py::approval_workflows": (
        "centralized expert approval by unguessable workflow_id + privileged role"
    ),
    # سقالة غير موصَّلة بمسار طلب (موثَّق في الكود): تمرّر tenant_id صراحةً من صفّ الـlifecycle،
    # لا عبر GUC. إن وُصِّلت لمسار طلب لاحقاً تُحوَّل لضبط GUC (_apply_tenant_guc).
    "services/sahool-platform/api/field_lifecycle.py::field_lifecycle": (
        "scaffold not wired to request path; explicit tenant_id"
    ),
    # إعادة تشغيل الأحداث (نظام): اتّصال bus._acquire، RLS مُطبَّق حين يُمرَّر conn بسياق؛
    # ومسارات الـreplay عابرة بالتصميم (تُعيد بناء حالة كلّ مستأجِر موسومةً).
    "services/sahool-platform/api/event_replay.py::field_state_snapshots": "system replay via bus conn",
    "services/sahool-platform/api/event_replay.py::commands,events": "system replay (cross-tenant outbox)",
    "services/sahool-platform/api/event_replay.py::events": "system replay (cross-tenant outbox)",
    # عمّال خلفيّون (أتمتة): تحت sahool_app (NOBYPASSRLS) يرتدّون fail-closed؛ يحتاجون دوراً
    # خدميّاً مخصّصاً عند النشر (موثَّق) — لا تسرّب، تحديث مُنطَّق بـfield_id/sensor_id.
    "services/sahool-platform/api/imagery_automation.py::imagery_automation_fields": (
        "background automation worker (fail-closed under sahool_app)"
    ),
    "services/actuator-service/main.py::automation_rules": "background scene-linkage worker",
    "services/soil-service/routers/readings.py::soil_readings": "soil ingestion service (sensor-scoped); handler moved to routers/ in router decomposition",
}
ALLOWLIST: set[str] = set(_ALLOWLIST_JUSTIFIED)


def tenant_tables() -> set[str]:
    """الجداول التي تحوي tenant_id (من الهجرات) — مرآة test_rls_tenant_coverage."""
    sql = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(MIG.glob("*.sql"))
        if not p.name.endswith(".down.sql")
    )
    t: set[str] = set()
    for m in re.finditer(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_]\w*)\s*\((.*?)\n\)\s*;", sql, re.S | re.I
    ):
        if re.search(r"\btenant_id\b", m.group(2), re.I):
            t.add(m.group(1).lower())
    for m in re.finditer(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?([A-Za-z_]\w*)\s+ADD COLUMN"
        r"(?:\s+IF NOT EXISTS)?\s+tenant_id\b",
        sql,
        re.I,
    ):
        t.add(m.group(1).lower())
    return t


def _enclosing_function(lines: list[str], idx: int) -> tuple[int, int]:
    """يُرجِع (بداية، نهاية) أسطر الدالّة الحاوية لسطر idx (بالمسافة البادئة)."""
    start = idx
    indent = None
    for i in range(idx, -1, -1):
        m = _DEF.match(lines[i])
        if m:
            start = i
            indent = len(m.group(1))
            break
    if indent is None:
        return max(0, idx - 20), min(len(lines), idx + 5)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j]
        if s.strip() and (len(s) - len(s.lstrip())) <= indent and _DEF.match(s) is None:
            if not s.lstrip().startswith(("#", '"', "'", ")", "]", "}")):
                end = j
                break
    return start, end


def _tables_in_call(lines: list[str], idx: int) -> set[str]:
    """يستخرج الجداول من نصّ الاستعلام بدءاً من سطر النداء (يمسح حتى 12 سطراً)."""
    blob = "\n".join(lines[idx : idx + 12])
    return {m.group(1).lower() for m in _TABLE.finditer(blob)}


def audit() -> list[dict]:
    tt = tenant_tables()
    rows: list[dict] = []
    for d in SCAN:
        for path in (ROOT / d).rglob("*.py"):
            if path.name.startswith("test_") or "tests" in path.parts:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            rel = str(path.relative_to(ROOT))
            for i, line in enumerate(lines):
                if not _CALL.search(line):
                    continue
                tables = _tables_in_call(lines, i)
                hit = tables & tt
                if not hit:
                    continue  # GLOBAL أو لا جدول معروف — خارج نطاق العزل
                fs, fe = _enclosing_function(lines, i)
                ctx = "\n".join(lines[fs:fe])
                sig = lines[fs] if fs < len(lines) else ""
                if re.search(r"tenant_connection(_for)?\(", ctx):
                    cls = "RLS_CONN"
                elif "set_config('app.current_tenant'" in ctx or "_apply_tenant_guc" in ctx:
                    cls = "EXPLICIT"
                elif re.search(r"\bconn\b", sig) and not re.search(
                    r"\.acquire\(\)|get_pool\(\)", ctx
                ):
                    # الدالّة تستقبل conn كمعامل ولا تكتسب اتّصالها ⇒ السياق مسؤوليّة المُنادي.
                    cls = "DELEGATED"
                elif re.search(r"\.acquire\(\)|get_pool\(\)", ctx):
                    # تكتسب اتّصالها بنفسها بلا RLS؛ إن رشّحت بـtenant_id ⇒ عزل تطبيقيّ.
                    blob = "\n".join(lines[i : i + 12])
                    cls = "APP_FILTER" if re.search(r"\btenant_id\b", blob) else "RAW"
                else:
                    cls = "DELEGATED"
                rows.append(
                    {
                        "loc": f"{rel}:{i + 1}",
                        "tables": ",".join(sorted(hit)),
                        "class": cls,
                    }
                )
    return rows


def raw_violations(rows: list[dict]) -> list[dict]:
    """استعلامات RAW على جداول مُستأجَرة خارج الـallowlist (تستوجب تصنيفاً)."""
    out = []
    for r in rows:
        if r["class"] != "RAW":
            continue
        key = f"{r['loc'].rsplit(':', 1)[0]}::{r['tables']}"
        if key in ALLOWLIST or r["loc"] in ALLOWLIST:
            continue
        out.append(r)
    return out


def main() -> int:
    rows = audit()
    from collections import Counter

    counts = Counter(r["class"] for r in rows)
    print(f"استعلامات على جداول مُستأجَرة: {len(rows)}")
    for k in ("RLS_CONN", "EXPLICIT", "DELEGATED", "APP_FILTER", "RAW"):
        print(f"  {k}: {counts.get(k, 0)}")
    viol = raw_violations(rows)
    if viol:
        print(f"\n⚠ RAW على جدول مُستأجَر خارج الـallowlist ({len(viol)}):")
        for r in viol:
            print(f"  {r['loc']}  [{r['tables']}]")
        return 1
    print("\n✓ كلّ استعلام مُستأجَر إمّا RLS_CONN/EXPLICIT أو RAW مُدرَج عمداً")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
