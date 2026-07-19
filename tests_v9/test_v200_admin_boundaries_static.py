"""حارس ساكن لطبقة الحدود الإداريّة المرجعيّة (A7 / v200) + برهان سلبيّ.

يفرض قرارات المالك الخمسة + الشرط الإضافيّ:
  • **مرجع مشترك:** لا ``tenant_id`` (قراءة عامّة لكلّ المستأجرين، لا بيانات مستأجِر) — أوّل جدول shared-reference معلَن.
  • **قراءة-عامّة/كتابة-محمِّل:** sahool_app **SELECT فقط** (REVOKE INSERT/UPDATE/DELETE في كلا المُشغّلَين) —
    لا كتابة مستأجِر، ولا UPDATE/DELETE إلّا عبر المُحمِّل الإداريّ (طبقة مرجعيّة تتغيّر بلا provenance = انجراف صامت).
  • **لا حدّ بلا مصدر:** provenance مطلوب (source/version/license/url/retrieved_at)؛ FK إلزاميّ.
  • **سلامة الهندسة:** trigger يرفض هندسة غير صالحة (برهان سلبيّ)؛ المُحمِّل يُصلِح بـST_MakeValid ويسجّل العدد.
  • **الملكيّة:** gis-workflow-service كاتب/مالك؛ القراءة ["*"] (ملكيّة الكتابة لا حكر القراءة).

فحص ساكن صرف — ``pytest -m unit`` (لا PostGIS/قاعدة).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = (ROOT / "migrations" / "v200_admin_boundaries.sql").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "migrations" / "bootstrap_postgres.sh").read_text(encoding="utf-8")
APPLY = (ROOT / "migrations" / "apply_in_compose.sh").read_text(encoding="utf-8")
LOADER = (ROOT / "services" / "gis-workflow-service" / "load_admin_boundaries.py").read_text(
    encoding="utf-8"
)
DB_OWNERSHIP = (ROOT / "docs" / "architecture" / "db_ownership.yml").read_text(encoding="utf-8")


def test_shared_reference_has_no_tenant_id():
    """مرجع مشترك: قراءة عامّة، بلا عزل مستأجِر (لا معنى له لطبقة عامّة)."""
    # جسم CREATE TABLE admin_boundaries لا يحمل tenant_id.
    m = re.search(r"CREATE TABLE IF NOT EXISTS admin_boundaries\s*\((.*?)\n\);", MIG, re.S)
    assert m and "tenant_id" not in m.group(1)


def test_table_shape_and_provenance_fk():
    assert re.search(r"admin_level\s+SMALLINT NOT NULL CHECK \(admin_level IN \(1, 2\)\)", MIG)
    assert re.search(r"geom\s+geometry\(MultiPolygon, 4326\) NOT NULL", MIG)
    assert "USING GIST (geom)" in MIG
    assert "REFERENCES admin_boundaries_source(source_id)" in MIG  # لا حدّ بلا مصدر
    assert "UNIQUE (admin_level, admin_code)" in MIG  # idempotent
    # provenance: كلّ حقول المرجعيّة إلزاميّة.
    for col in ("source", "dataset_version", "license_title", "license_url", "url", "retrieved_at"):
        assert re.search(rf"\b{col}\b\s+\w.*NOT NULL", MIG), f"provenance {col} ليس NOT NULL"


def test_geometry_validity_trigger_negative_proof():
    """برهان سلبيّ: هندسة غير صالحة تُرفَض بنيويّاً (trigger)، لا تمرّ صامتة فتلوّث downstream."""
    assert "admin_boundaries_require_valid_geom" in MIG
    assert "NOT ST_IsValid(NEW.geom)" in MIG and "RAISE EXCEPTION" in MIG
    assert "BEFORE INSERT OR UPDATE ON admin_boundaries" in MIG


@pytest.mark.parametrize("runner", [BOOTSTRAP, APPLY])
def test_app_role_is_select_only_on_reference(runner: str):
    """قراءة-عامّة/كتابة-محمِّل: sahool_app تُنزَع منه INSERT/UPDATE/DELETE على الجدولين."""
    assert re.search(r"REVOKE INSERT, UPDATE, DELETE ON admin_boundaries FROM", runner), (
        "REVOKE الكتابة عن app على admin_boundaries مفقود"
    )
    assert re.search(r"REVOKE INSERT, UPDATE, DELETE ON admin_boundaries_source FROM", runner), (
        "REVOKE الكتابة عن app على admin_boundaries_source مفقود"
    )


def test_ownership_gis_workflow_public_read():
    block = DB_OWNERSHIP.split("admin_boundaries:", 1)[1].split("agent_authority", 1)[0]
    assert "owner: gis-workflow-service" in block and "writers: [gis-workflow-service]" in block
    assert 'readers: ["*"]' in block  # قراءة عامّة (ملكيّة الكتابة لا حكر القراءة)


def test_loader_validates_geometry_and_captures_provenance():
    """المُحمِّل: ST_IsValid + ST_MakeValid + عدّ المُصلَّح + التقاط الرخصة/الإصدار/وقت الجلب."""
    assert "ST_IsValid" in LOADER and "ST_MakeValid" in LOADER
    assert "invalid_geometry_fixed" in LOADER and "fixed += 1" in LOADER
    for f in ("license_title", "license_url", "dataset_version", "retrieved_at"):
        assert f in LOADER, f"المُحمِّل لا يلتقط {f}"
    assert "ON CONFLICT (admin_level, admin_code)" in LOADER  # idempotent
    # لا صفّ حدّ بلا source (source_id مطلوب في INSERT).
    assert "source_id" in LOADER


def test_no_app_path_writes_admin_boundaries():
    """لا مسار خدمة تطبيقيّ يكتب admin_boundaries (الكتابة عبر المُحمِّل الإداريّ فقط)."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        parts = path.parts
        if "__pycache__" in parts or path.name.startswith("test_"):
            continue
        if path.name == "load_admin_boundaries.py":  # المُحمِّل الموثَّق هو الكاتب الوحيد
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"INSERT\s+INTO\s+admin_boundaries|UPDATE\s+admin_boundaries\b", text, re.I):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"كتابة admin_boundaries من خارج المُحمِّل: {offenders}"


def test_registered_in_manifest_and_runner():
    assert "v200_admin_boundaries.sql" in (ROOT / "migrations" / "MANIFEST.txt").read_text(
        encoding="utf-8"
    )
    assert "v200_admin_boundaries.sql" in (ROOT / "scripts_v9" / "run_migrations.sql").read_text(
        encoding="utf-8"
    )
