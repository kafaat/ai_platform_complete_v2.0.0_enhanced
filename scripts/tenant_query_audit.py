#!/usr/bin/env python3
"""scripts/tenant_query_audit.py — تعداد شامل لاستعلامات القاعدة وتصنيف عزلها.

ينتقل من «فحصتُ عيّنة» إلى «كلّ استعلام محسوب»: يَمسح **كلّ** موقع نداء قاعدة
(execute/fetch/fetchrow/fetchval) في كلّ الخدمات، يستخرج الجداول المُشار إليها، ويصنّف
كلّ استعلام يلمس **جدولاً مُستأجَراً** (يحوي tenant_id) حسب طريقة ضبط سياق العزل:

  • RLS_CONN   — داخل دالّة تستعمل tenant_connection/tenant_connection_for ⇒ RLS مضبوط.
  • EXPLICIT   — الدالّة تضبط سياق المستأجِر صراحةً **بنطاقٍ يحيا حتّى الاستعلام**.
                 ضبطٌ بنطاق المعاملة (set_config ..., true) خارج أيّ معاملة **لا يُمنَح**
                 EXPLICIT — الوجود ليس النطاق، والضبط يضيع قبل الاستعلام التالي.
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
    # P1 decomposition: العامل الخلفيّ نفسه انتقل من main.py إلى actuator_runtime.py —
    # نُبقي المفتاح القديم (غير ضارّ) ونضيف الجديد بنفس التبرير (نمط soil-service أعلاه).
    "services/actuator-service/actuator_runtime.py::automation_rules": (
        "background scene-linkage worker; moved from main.py in P1 decomposition"
    ),
    # توحيد main↔cert: soil مُفكَّكة (main #570) فالمفتاح بمسار routers؛ نُبقي مفتاح cert
    # القديم (services/soil-service/main.py::soil_readings) لأنّه غير ضارّ (مسار غير موجود).
    "services/soil-service/routers/readings.py::soil_readings": "soil ingestion service (sensor-scoped); handler moved to routers/ in router decomposition",
    # جسر القرار→التنفيذ (Shard 3، default-OFF): مُستهلِك خلفيّ يطالب الطابور ذرّيّاً
    # (FOR UPDATE SKIP LOCKED) ويُنهيه بـdecision_id. لا تسرّب فيزيائيّ عابر للمستأجرين:
    # _device_belongs_to_tenant يحرس النشر (fail-closed) فلا أمر إلّا لجهاز مستأجِر القرار.
    "services/actuator-service/main.py::dispatch_decisions": (
        "background dispatch consumer (default-OFF); device-ownership guard fail-closes cross-tenant actuation"
    ),
    "services/soil-service/main.py::soil_readings": "soil ingestion service (sensor-scoped)",
    # عمّال/مخزن runtime للمراحل 9-12: يضبطون app.current_tenant + app.tenant_id
    # transaction-locally (set_config) قبل كلّ كتابة خام ⇒ تخضع لـRLS فعليّاً (لا تجاوز).
    # outbox/dispatch مسارات خلفيّة موسومة بالمستأجِر؛ لا تسرّب فيزيائيّ عابر.
    "services/sahool-platform/api/phase_runtime_store.py::marketplace_installations": (
        "phase runtime store: sets app.current_tenant/app.tenant_id tx-locally before write (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::runtime_event_outbox": (
        "phase runtime worker: tenant GUC set tx-locally before write (RLS-scoped outbox)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::marketplace_plugin_runtime_events": (
        "phase runtime worker: tenant GUC set tx-locally before write (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::model_rollback_history_runtime": (
        "phase runtime worker: tenant GUC set tx-locally before write (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::events": (
        "water-deficit bridge timeline event: tenant GUC already set tx-locally per field; "
        "insert carries explicit tenant_id + dedup_key (RLS-scoped canonical events)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::water_ledger": (
        "water-ledger auto worker: tenant GUC set tx-locally per field before read/upsert (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::soil_lab_tests,water_ledger": (
        "water-ledger auto worker: tenant GUC set tx-locally per field before reads (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::irrigation_runs,soil_lab_tests": (
        "water-ledger auto worker: tenant GUC set tx-locally per field before reads (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::irrigation_runs": (
        "water-ledger auto worker: tenant GUC set tx-locally per field before read (RLS-scoped)"
    ),
    "services/sahool-platform/api/phase_runtime_workers.py::iot_command_dispatch": (
        "phase runtime worker: tenant GUC set tx-locally before write (RLS-scoped dispatch)"
    ),
    # عامل إبطال كاش الراستر (FINDING-005): طابور raster_cache_invalidations عابر
    # بالتصميم — يطالب الصفوف ذرّيّاً (FOR UPDATE SKIP LOCKED) بدور JOBS (BYPASSRLS)
    # وينهيها بـid (لا سياق مستأجِر لتحديث الحالة). لا تسرّب فيزيائيّ: العمل الوحيد
    # حذف بلاطات دليل الحقل المُعقَّم + وسم raster_assets stale بفلتر tenant_id صريح.
    "services/raster-service/cache_invalidation_worker.py::raster_cache_invalidations": (
        "background invalidation queue consumer (JOBS role); claims by id via FOR UPDATE SKIP LOCKED"
    ),
    # عامل فحص backfill (v5/v6): يطالب backfill_runs العابر بدور JOBS (FOR UPDATE SKIP
    # LOCKED) ويُحدّثه بـid؛ كتابة backfill_run_items لكلّ مستأجِر تضبط app.current_tenant
    # tx-locally قبلها (RLS-scoped)؛ preflight على raster_assets بفلتر tenant_id صريح.
    "services/raster-service/backfill_scan_worker.py::backfill_runs": (
        "background backfill scan consumer (JOBS role); claims/updates runs by id"
    ),
    "services/raster-service/backfill_scan_worker.py::backfill_run_items,backfill_runs": (
        "backfill scan worker: tenant GUC set tx-locally before per-tenant run_items write (RLS-scoped)"
    ),
    # v9-F4/v10-F5/v10-F6: وسم run_item بـprocessing+job_id (وبعده persisted/failed) داخل
    # معاملة تضبط app.current_tenant tx-locally أوّلاً (RLS-scoped) — تتبّع run_item→job.
    "services/raster-service/backfill_scan_worker.py::backfill_run_items": (
        "backfill scan worker: per-item processing/job_id + terminal status; tenant GUC set tx-locally (RLS-scoped)"
    ),
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
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
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
                elif "_apply_tenant_guc" in ctx or "_tenant_conn(" in ctx:
                    cls = "EXPLICIT"
                elif "set_config('app.current_tenant'" in ctx:
                    # **الوجود ليس النطاق** (`GUC-SCOPE-GUARD-SEES-ONE-FILE-01`):
                    # `set_config(..., true)` يضبط بنطاق **المعاملة**، وasyncpg بلا معاملة
                    # صريحة في autocommit ⇒ الضبط يضيع قبل الاستعلام التالي فيُرجِع RLS
                    # صفراً. ومنحُ `EXPLICIT` لمجرّد رؤية الاستدعاء كان يُعطي كلّ موضعٍ
                    # معيبٍ **شهادة سلامة** — وهو أسوأ من عدم التصنيف، لأنّه يُسكِت السؤال.
                    # فالضبط بنطاق المعاملة لا يُصنَّف `EXPLICIT` إلّا إن وقع داخل واحدة.
                    _scoped_local = re.search(
                        r"set_config\(\s*'app\.current_tenant'\s*,[^,]*,\s*true\s*\)", ctx
                    )
                    _in_tx = re.search(r"async\s+with\s+[\w.]*\.?(transaction|begin)\(", ctx)
                    cls = "EXPLICIT" if (not _scoped_local or _in_tx) else "RAW"
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


# ══════════════════════════════════════════════════════════════════════════════
# دَينٌ **كشفه تصحيح المُصنِّف** — وليس allowlist، والفرق ليس لفظيّاً.
#
# `_ALLOWLIST_JUSTIFIED` يقول «هذا صحيح ولهذا السبب». وهذا السجلّ يقول عكسه تماماً:
# «هذا **عيبٌ قائم**، مقيسٌ ومرئيّ، ولم يُصلَح بعد». خلطُهما كان سيُحوّل عطلاً إلى
# تبرير — وهو ما فعله المُصنِّف القديم حين منح `EXPLICIT` لمجرّد وجود `set_config`.
#
# **ولماذا لم تُصلَح هنا:** قاعدة المالك — «أيّ فشل يكشف عيباً إنتاجيّاً يُسجَّل
# ويوقف الملفّ المعنيّ؛ لا يُصلَح ضمن الشريحة تلقائيّاً». وإصلاحها يمسّ مسارات
# استعلام في خدمات لم تُقَس حيّاً، فتسجيلُها أصدق من لمسها على عمًى.
#
# **يتقلّص ولا ينمو:** موضعٌ جديد يُفشِل البوّابة؛ وموضعٌ أُصلِح يُحذَف من هنا.
# مُسجَّل في `sahool-brain/gaps/registry.md` تحت `GUC-SCOPE-GUARD-SEES-ONE-FILE-01`.
_REVEALED_SCOPE_DEBT: dict[str, str] = {
    "services/soil-service/soil_store.py::soil_observations": (
        "revealed by scope-aware EXPLICIT: set_config(...,true) outside a transaction"
    ),
    "services/mcp_servers/market_server.py::market_sales_listings": (
        "revealed by scope-aware EXPLICIT: 12/12 set_config sites outside a transaction"
    ),
    "services/mcp_servers/market_db_authz.py::inventory_batches": (
        "revealed by scope-aware EXPLICIT: helper contract does not itself open a transaction"
    ),
}


def raw_violations(rows: list[dict]) -> list[dict]:
    """استعلامات RAW على جداول مُستأجَرة خارج الـallowlist (تستوجب تصنيفاً).

    والدَّين المكشوف (`_REVEALED_SCOPE_DEBT`) يُستثنى من **الحجب** لا من **الرؤية**:
    يبقى `RAW` في الجرد والإحصاء، ويُطبَع بوصفه ديناً — فلا يُقرأ صمتُه سلامةً.
    """
    out = []
    for r in rows:
        if r["class"] != "RAW":
            continue
        key = f"{r['loc'].rsplit(':', 1)[0]}::{r['tables']}"
        if key in ALLOWLIST or r["loc"] in ALLOWLIST:
            continue
        if key in _REVEALED_SCOPE_DEBT:
            continue
        out.append(r)
    return out


def revealed_debt(rows: list[dict]) -> list[dict]:
    """الدَّين المكشوف القائم — يُطبَع ليبقى مرئيّاً، ويُقاس ليتقلّص."""
    out = []
    for r in rows:
        if r["class"] != "RAW":
            continue
        key = f"{r['loc'].rsplit(':', 1)[0]}::{r['tables']}"
        if key in _REVEALED_SCOPE_DEBT:
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
    debt = revealed_debt(rows)
    if debt:
        print(f"\n⚠ دَينٌ مكشوف بتصحيح المُصنِّف ({len(debt)}) — عيبٌ قائم لا تبرير:")
        for r in debt:
            print(f"  {r['loc']}  [{r['tables']}]")
        print("  GUC-SCOPE-GUARD-SEES-ONE-FILE-01 · يتقلّص ولا ينمو")
    print("\n✓ كلّ استعلام مُستأجَر إمّا RLS_CONN/EXPLICIT أو RAW مُدرَج عمداً أو دَينٌ مُعلَن")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
