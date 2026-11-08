"""حارس ساكن v240 — مرورٌ واحد على MANIFEST == مروران، عقدُ الملفّ بلا قاعدة.

المقيس على قاعدة فارغة (PG 16، c966fd0b2): 55 سطراً من ``pg_dump -s`` المُطبَّع تفرق بين مرّة
ومرّتين، كلّها كائناتٌ يُنشئها ملفٌّ مبكّر مشروطةً بجدولٍ يُنشئه ملفٌّ لاحق. البرهان الحيّ في
``test_v240_first_pass_convergence_live_pg.py``؛ هنا ما يجب ألّا ينجرف نصّيّاً:

* مُسجَّل في المُشغّلَين **مباشرةً** قبل v206 (v206 آخِراً) — بعده تعود الهجرةُ اللاحقة مصدرَ
  اعتمادِ مسارٍ جديد.
* يُسمّي كلَّ كائنٍ مُتقارَب (5 فهارس + قيدان + 46 فهرس tenant_id) — والقائمة مُسنَدة بالسبب:
  جدولُ كلٍّ منها يُنشأ في MANIFEST **بعد** الملفّ الذي يُنشئ الكائن مشروطاً.
* كلُّ DDL مسبوقٌ بفحص كتالوج، فلا قفلَ على قاعدةٍ أُعيد عليها البيان (الإنتاج).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_MIGDIR = _ROOT / "migrations"
_MIG = _MIGDIR / "v240_converge_first_pass_schema.sql"
_MANIFEST = _MIGDIR / "MANIFEST.txt"
_RUNNER = _ROOT / "scripts_v9" / "run_migrations.sql"

# (الكائن، جدوله، الملفّ الذي يُنشئه مشروطاً، الملفّ الذي يُنشئ جدوله)
CONVERGED_NON_TENANT: tuple[tuple[str, str, str, str], ...] = (
    ("idx_edge_results_brin", "edge_results", "v9_foundation.sql", "v9_new_tables.sql"),
    ("chk_confidence_range", "agent_queries", "v9_foundation.sql", "v9_new_tables.sql"),
    ("chk_risk_levels", "guardrails_log", "v9_foundation.sql", "v9_new_tables.sql"),
    ("idx_ft_source_event", "field_tasks", "v9_foundation.sql", "v9_new_tables.sql"),
    ("idx_workflow_expires", "approval_workflows", "v9_foundation.sql", "v9_new_tables.sql"),
    (
        "idx_market_listings_crop_status",
        "market_sales_listings",
        "v9_new_tables.sql",
        "v9_market.sql",
    ),
    (
        "idx_market_listings_tenant_status",
        "market_sales_listings",
        "v9_new_tables.sql",
        "v9_market.sql",
    ),
)

# idx_<t>_tenant يُنشئه v57_rls_dynamic_indexes للجداول الموجودة عند تشغيله فقط.
CONVERGED_TENANT_TABLES: tuple[str, ...] = (
    "actuator_command_outbox",
    "agent_proposals",
    "autonomous_execution_plan",
    "digital_twin_scenarios",
    "execution_verification_event",
    "external_ingest_sources",
    "farm_energy_records",
    "farm_equipment_records",
    "farm_labor_records",
    "farm_production_units",
    "farm_season_projects",
    "federated_policy_experiments",
    "field_feature_store_candidate",
    "gis_collaboration_events",
    "irrigation_battery_systems",
    "irrigation_energy_loads",
    "irrigation_generators",
    "irrigation_grid_connections",
    "irrigation_hybrid_inverters",
    "irrigation_hydraulic_nodes",
    "irrigation_pv_arrays",
    "irrigation_runs",
    "irrigation_sprinkler_packages",
    "irrigation_sprinkler_zones",
    "irrigation_water_samples",
    "market_procurement_items",
    "market_suppliers",
    "marketplace_plugin_output_validations",
    "mfa_audit_events",
    "mfa_recovery_codes",
    "model_experiment_assignment",
    "ogc_conformance_runs",
    "outbox_delivery_attempts",
    "plugin_permission_audit",
    "runtime_event_outbox",
    "season_cost_items",
    "season_crop",
    "season_events",
    "season_harvest",
    "soil_learning_attributions",
    "soil_outcome_records",
    "soil_reconciliation_checkpoints",
    "soil_reconciliation_deferrals",
    "soil_verification_records",
    "webhook_deliveries",
    "yield_stability_maps",
)
_V57 = "v57_rls_dynamic_indexes.sql"


def _code(path: Path) -> str:
    return "\n".join(
        line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
    )


def _entries() -> list[str]:
    return [
        ln.strip()
        for ln in _MANIFEST.read_text(encoding="utf-8").splitlines()
        if ln.strip().endswith(".sql") and not ln.lstrip().startswith("#")
    ]


def _first_creator(table: str, entries: list[str]) -> str | None:
    pat = re.compile(
        rf"CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?\"?{table}\"?\s*\(",
        re.IGNORECASE,
    )
    for name in entries:
        if pat.search(_code(_MIGDIR / name)):
            return name
    return None


def test_registered_immediately_before_v206_in_both_runners() -> None:
    entries = _entries()
    assert entries[-1] == "v206_rls_final_hardening.sql"
    assert entries[-2] == _MIG.name, "v240 must stay directly before v206 (see file header)"
    included = re.findall(r"^\\i migrations/(\S+)$", _RUNNER.read_text(encoding="utf-8"), re.M)
    assert included[-2:] == [_MIG.name, "v206_rls_final_hardening.sql"]


def test_atomic() -> None:
    code = _code(_MIG)
    assert code.lstrip().startswith("BEGIN;") and code.rstrip().endswith("COMMIT;")


def test_every_converged_object_is_named_and_catalog_guarded() -> None:
    code = _code(_MIG)
    for obj, table, _src, _tbl in CONVERGED_NON_TENANT:
        assert re.search(rf"\b{obj}\b", code), f"{obj} not converged"
        assert re.search(rf"to_regclass\('public\.{table}'\) IS NOT NULL", code), table
        if obj.startswith("idx_"):
            assert f"to_regclass('public.{obj}') IS NULL" in code, (
                f"{obj}: DDL without catalog check"
            )
        else:
            assert f"conname = '{obj}'" in code, f"{obj}: DDL without catalog check"
    listed = re.search(r"tables text\[\] := ARRAY\[(.*?)\];", code, re.S)
    assert listed, "tenant table array missing"
    in_file = re.findall(r"'([a-z_0-9]+)'", listed.group(1))
    assert tuple(in_file) == CONVERGED_TENANT_TABLES
    # الشرط حرفُ شرط v57: صدارة tenant_id في أيّ فهرسٍ قائم ⇒ تخطٍّ.
    assert "a.attnum = ix.indkey[0]" in code and "a.attname = 'tenant_id'" in code
    assert "'idx_' || t || '_tenant'" in code


def test_each_converged_object_is_still_deferred_by_its_source_migration() -> None:
    """السبب ما زال قائماً: المُنشِئ قبل جدوله في MANIFEST، وما زال يُنشئ الكائن مشروطاً."""
    entries = _entries()
    for obj, table, src, tbl_src in CONVERGED_NON_TENANT:
        assert obj in _code(_MIGDIR / src), f"{obj} no longer created by {src}"
        assert _first_creator(table, entries) == tbl_src, table
        assert entries.index(src) < entries.index(tbl_src), (obj, src, tbl_src)
    v57_pos = entries.index(_V57)
    late = {t: _first_creator(t, entries) for t in CONVERGED_TENANT_TABLES}
    assert all(late.values()), {t: c for t, c in late.items() if c is None}
    early = {t: c for t, c in late.items() if entries.index(c) < v57_pos}
    assert not early, f"created before v57 (v57 indexes them on pass one): {early}"


def test_no_explicit_tenant_index_duplicates_the_convergence() -> None:
    """إن صار أحد الجداول يُنشئ فهرسه tenant_id بنفسه، فمكانه خارج قائمة التقارب."""
    entries = _entries()
    for t in CONVERGED_TENANT_TABLES:
        src = _code(_MIGDIR / str(_first_creator(t, entries)))
        own = re.search(
            rf"CREATE\s+(?:UNIQUE\s+)?INDEX[^;]*?\bON\s+(?:public\.)?{t}\s*(?:USING\s+\w+\s*)?\(\s*tenant_id\b",
            src,
            re.IGNORECASE,
        )
        assert own is None, f"{t} now declares its own tenant-leading index: {own.group(0)!r}"
