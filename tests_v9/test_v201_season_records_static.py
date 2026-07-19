"""حارس ساكن لسجلّ الموسم المُدار (SEASON-RECORD-01 / v201) + براهين سلبيّة.

يفرض قرارات المواصفة + شروط قبول انحراف الـVIEW الثلاثة (ملاحظة المالك):
  ① **`security_invoker = true` إلزاميّ** على الـVIEW — وإلّا يتخطّى RLS ويسرّب الأهليّة عبر المستأجرين (فخّ v198).
  ② **لا عمود `calibration_eligible` قابل للكتابة** في أيّ من الجداول الخمسة — الـVIEW نقطة القراءة الوحيدة (مصدر حقيقة واحد).
  ③ **الانحراف موثَّق في رأس الهجرة** (المواصفة طلبت عموداً مُولَّداً؛ نُفّذ VIEW لأنّ GENERATED لا يعبر الجداول — النيّة محفوظة).

وقرارات المواصفة الأساسيّة:
  • خمسة جداول بـtenant_id + RLS + FORCE + سياسة عزل — نمط v197/v199.
  • append-only: **لا DELETE أبداً** — يُنزَع في كلا المُشغّلَين (bootstrap/apply) — برهان سلبيّ.
  • قيود النزاهة (لا مستقبل · مدى · حصاد-بعد-زراعة trigger · ساعات معدّة موجبة · دليل طاقة).
  • تعدّد عملات آمن (ISO 4217 CHECK، YER افتراضيّة).
  • الهندسة ليست هنا (field_id FK لا polygon).
  • الملكيّة: scout-ingest-service كاتب واحد للخمسة (Q1) + مسجَّل في المُشغّلَين.

فحص ساكن صرف — ``pytest -m unit`` (لا PostGIS/قاعدة).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
MIG = (_ROOT / "migrations" / "v201_season_records.sql").read_text(encoding="utf-8")
BOOTSTRAP = (_ROOT / "migrations" / "bootstrap_postgres.sh").read_text(encoding="utf-8")
APPLY = (_ROOT / "migrations" / "apply_in_compose.sh").read_text(encoding="utf-8")
RUN_MIG = (_ROOT / "scripts_v9" / "run_migrations.sql").read_text(encoding="utf-8")
MANIFEST = (_ROOT / "migrations" / "MANIFEST.txt").read_text(encoding="utf-8")
DB_OWNERSHIP = (_ROOT / "docs" / "architecture" / "db_ownership.yml").read_text(encoding="utf-8")

_TABLES = ["season_records", "season_crop", "season_events", "season_harvest", "season_cost_items"]


def test_five_tables_created_with_tenant_id():
    for t in _TABLES:
        assert re.search(rf"CREATE TABLE IF NOT EXISTS {t}\b", MIG), f"جدول {t} مفقود"
        assert re.search(
            rf"CREATE TABLE IF NOT EXISTS {t}\b[\s\S]*?tenant_id\s+UUID NOT NULL", MIG
        ), f"{t} بلا tenant_id NOT NULL — العزل مستحيل"


def test_rls_force_and_policy_on_all_five():
    """RLS + FORCE + سياسة العزل تُطبَّق على الجداول الخمسة (حلقة DO)."""
    assert "FORCE ROW LEVEL SECURITY" in MIG
    assert "ENABLE ROW LEVEL SECURITY" in MIG
    assert "POLICY tenant_isolation" in MIG
    assert "current_setting(''app.current_tenant''" in MIG  # سياسة العزل القانونيّة
    for t in _TABLES:
        assert re.search(rf"'{t}'", MIG), f"{t} غير مذكور في حلقة RLS"


def test_no_geometry_here_field_id_fk():
    """الهندسة ملك سجلّ الحقول — field_id FK، لا عمود geometry/geom في جداول المواسم."""
    assert re.search(r"field_id\s+UUID NOT NULL REFERENCES fields\(id\)", MIG)
    assert "geometry(" not in MIG and re.search(r"\bgeom\b\s+geometry", MIG) is None


# ── الشرط ① — security_invoker=true إلزاميّ على الـVIEW ──
def test_calibration_view_has_security_invoker():
    """① بدون security_invoker يعمل الـVIEW بصلاحيّات المالك ⇒ يتخطّى RLS ويسرّب الأهليّة عبر المستأجرين."""
    assert re.search(
        r"CREATE OR REPLACE VIEW season_calibration_eligibility\s+WITH \(security_invoker = true\)",
        MIG,
    ), "الـVIEW يجب أن يُنشأ WITH (security_invoker = true) — وإلّا تسريب عبر المستأجرين (فخّ v198)"


# ── الشرط ② — لا عمود calibration_eligible قابل للكتابة في أيّ جدول (مصدر حقيقة واحد) ──
def test_no_writable_calibration_column_anywhere():
    """② الـVIEW هو نقطة القراءة الوحيدة؛ لا عمود مطابق في CREATE TABLE (وإلّا مصدرا حقيقة)."""
    # نلتقط أجسام CREATE TABLE فقط (لا الـVIEW الذي يُنتِج العمود كتعبير مُشتقّ).
    table_bodies = re.findall(r"CREATE TABLE IF NOT EXISTS \w+\s*\((.*?)\n\);", MIG, re.S)
    assert table_bodies, "لم تُلتقَط أجسام الجداول"
    for body in table_bodies:
        assert "calibration_eligible" not in body, (
            "عمود calibration_eligible مخزَّن = مصدر حقيقة ثانٍ محظور (②)"
        )


# ── الشرط ③ — توثيق الانحراف في رأس الهجرة ──
def test_deviation_documented_in_header():
    """③ يُفهَم لاحقاً أنّ المواصفة تُرجِمت بأمانة (VIEW بدل عمود مُولَّد لأنّ GENERATED لا يعبر الجداول)."""
    head = MIG[:2600]
    assert "GENERATED" in head and "VIEW" in head and "يعبر" in head, (
        "انحراف الـVIEW غير موثَّق في الرأس"
    )


def test_append_only_no_delete_in_both_runners():
    """append-only: تُنزَع DELETE على الجداول الخمسة في كلا المُشغّلَين (يبقى INSERT/UPDATE للقبول)."""
    for runner_name, runner in (("bootstrap", BOOTSTRAP), ("apply", APPLY)):
        for t in _TABLES:
            assert re.search(rf"REVOKE DELETE ON {t} FROM", runner), (
                f"{t}: DELETE غير مُنزَع في {runner_name} — الـappend-only غير مضمون"
            )
        # لا يُنزَع INSERT/UPDATE (القبول untrusted→accepted يحتاج UPDATE)
        assert "REVOKE INSERT, UPDATE, DELETE ON season_records" not in runner


def test_integrity_constraints_present():
    assert "season_records_no_future" in MIG and "observed_at_to <= submitted_at::date" in MIG
    assert "season_records_range" in MIG
    assert "season_events_machinery_positive" in MIG and "machinery_hours > 0" in MIG
    assert "season_events_energy_evidence" in MIG
    # حصاد بعد زراعة (يعبر جدولين ⇒ trigger)
    assert "season_harvest_after_sowing" in MIG and "RAISE EXCEPTION" in MIG
    assert "BEFORE INSERT OR UPDATE ON season_harvest" in MIG


def test_currency_multi_iso4217_safe():
    """تعدّد عملات آمن: YER افتراضيّة + CHECK ISO 4217 (3 أحرف كبيرة)."""
    assert re.search(
        r"currency\s+TEXT NOT NULL DEFAULT 'YER' CHECK \(currency ~ '\^\[A-Z\]\{3\}\$'\)", MIG
    )


def test_trust_gate_and_yield_calibration_point():
    assert re.search(r"trust_status\s+TEXT NOT NULL DEFAULT 'untrusted'", MIG)
    assert "'untrusted', 'accepted', 'quarantined'" in MIG
    assert re.search(
        r"yield_kg_ha\s+NUMERIC CHECK \(yield_kg_ha IS NULL OR yield_kg_ha >= 0\)", MIG
    )


def test_ownership_scout_ingest_single_writer():
    """Q1: الجداول الخمسة يملكها scout-ingest-service (كاتب واحد)."""
    for t in _TABLES:
        block = re.search(rf"  {t}:\n(.*?)(?=\n  \w|\Z)", DB_OWNERSHIP, re.S)
        assert block, f"{t} غير مسجَّل في db_ownership.yml"
        assert "owner: scout-ingest-service" in block.group(1)
        assert "writers: [scout-ingest-service]" in block.group(1)
        assert "migrations/v201_season_records.sql" in block.group(1)


def test_registered_in_both_runners():
    assert "v201_season_records.sql" in MANIFEST
    assert "v201_season_records.sql" in RUN_MIG
