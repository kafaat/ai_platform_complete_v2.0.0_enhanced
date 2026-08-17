"""بوّابة ARCH-S1a: سجلّ المكوّنات القانونيّ الواحد — صفر مكوّنات غير مصنَّفة.

قبل الشريحة كان التصنيف يسكن ``config/platform_catalog_overrides.yml`` ويسقط
افتراضيّاً إلى ``service`` لكلّ مكوّن غير مذكور — فالمكوّن غير المصنَّف كان يمرّ
صامتاً. الآن التصنيف إعلان مُحكَّم في ``docs/architecture/component_registry.json``،
والمُصرِّف يُثبته تقاطعيّاً ضدّ الواقع المقيس (compose/الجرد/ملكيّة الجداول)
ويفشل على أيّ فجوة. هذه الاختبارات تستجوب **الدالّة** لا نصّها — الصنف
``STABLE_WRONG_TEST`` وقع أربع مرّات في هذا المستودع وكلّها كانت مطابقات نصّيّة.
"""

from __future__ import annotations

import copy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "scripts" / "architecture" / "build_platform_catalog.py"
REGISTRY = ROOT / "docs" / "architecture" / "component_registry.json"


def _load_compiler():
    spec = importlib.util.spec_from_file_location("platform_catalog_compiler_s1a", COMPILER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


MOD = _load_compiler()
REG = json.loads(REGISTRY.read_text(encoding="utf-8"))

# قياس متّسق اصطناعيّ مشتقّ من السجلّ نفسه — أساس التحوير في كلّ اختبار سلبيّ.
_CONSISTENT = {
    cid: {
        "deployment_unit": e["deployment_unit"],
        "source_path": e["source_path"],
        "owns_tables": e["authority_kind"] == "system_of_record",
    }
    for cid, e in REG["components"].items()
}


# ── طبقة الدالّة: أصناف الفشل الأربعة + الاتّساق ─────────────────


def test_consistent_declaration_yields_zero_failures() -> None:
    assert MOD.component_classification_failures(REG, copy.deepcopy(_CONSISTENT)) == []


def test_unclassified_component_is_a_measured_failure() -> None:
    """المكوّن المكتشَف بلا صفّ سجلّ لا يسقط إلى service صامتاً — يفشل بالاسم."""
    measured = copy.deepcopy(_CONSISTENT)
    measured["ghost-service"] = {
        "deployment_unit": None,
        "source_path": "services/ghost-service",
        "owns_tables": False,
    }
    failures = MOD.component_classification_failures(REG, measured)
    assert any("unclassified component: ghost-service" in f for f in failures)


def test_stale_registry_entry_is_a_measured_failure() -> None:
    """صفّ سجلّ بلا مكوّن مكتشَف = جرد كاذب — يفشل بالاسم لا يُقرأ تغطيةً."""
    measured = copy.deepcopy(_CONSISTENT)
    del measured["auth"]
    failures = MOD.component_classification_failures(REG, measured)
    assert any("stale registry entry: auth" in f for f in failures)


def test_declared_deployment_unit_must_match_measured() -> None:
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["deployment_unit"] = "wrong-unit"
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "deployment_unit" in f for f in failures)


def test_declared_source_path_must_match_measured() -> None:
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["source_path"] = "services/nowhere"
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "source_path" in f for f in failures)


def test_component_kind_outside_vocabulary_fails() -> None:
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["component_kind"] = "microservice"
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "component_kind" in f for f in failures)


def test_authority_kind_must_agree_with_measured_table_ownership() -> None:
    """إعلان system_of_record بلا جداول مملوكة (أو العكس) كذبُ سلطة — يفشل."""
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["authority_kind"] = "system_of_record"
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "authority_kind" in f for f in failures)


def test_presentation_components_are_exempt_from_table_ownership_check() -> None:
    """frontend/mobile لا تملك جداول بالبناء — سلطتها presentation لا تُقاس بالجداول."""
    assert MOD.component_classification_failures(REG, copy.deepcopy(_CONSISTENT)) == []
    assert REG["components"]["frontend"]["authority_kind"] == "presentation"
    assert REG["components"]["mobile"]["authority_kind"] == "presentation"


# ── طبقة الشجرة المشحونة: السجلّ والإسقاطات متقاربة فعلاً ────────


def test_shipped_component_inventory_matches_the_registry() -> None:
    """إسقاط CSV يحمل مخطّط S1a وصفوفه تطابق السجلّ هويّةً وتصنيفاً."""
    with (ROOT / "component_inventory.generated.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert {r["component_id"] for r in rows} == set(REG["components"])
    for r in rows:
        entry = REG["components"][r["component_id"]]
        assert r["component_kind"] == entry["component_kind"], r["component_id"]
        assert r["authority_kind"] == entry["authority_kind"], r["component_id"]
        assert r["domain"] == entry["domain"], r["component_id"]
        assert r["source_path"] == entry["source_path"], r["component_id"]
        assert r["deployment_unit"] == (entry["deployment_unit"] or ""), r["component_id"]


def test_shipped_csv_header_is_the_s1a_schema() -> None:
    catalog = json.loads((ROOT / "platform_catalog.generated.json").read_text(encoding="utf-8"))
    header = MOD._components_csv(catalog).splitlines()[0]
    assert header.split(",")[:6] == [
        "component_id",
        "component_kind",
        "deployment_unit",
        "domain",
        "authority_kind",
        "source_path",
    ]


def test_every_kind_in_use_is_in_the_adjudicated_vocabulary() -> None:
    kinds = set(REG["component_kinds"])
    used = {e["component_kind"] for e in REG["components"].values()}
    assert used <= kinds
    # الموروث المهاجَر لا يعود: المفردات القديمة ليست في المعجم ولا في الاستعمال.
    assert not {"adapter", "job", "batch-job-tool"} & (kinds | used)


def test_registry_is_a_governed_manifest() -> None:
    """يدخل سجلّ البيانات المُحكَّمة: schema + version + adjudicated_on إلزاميّة."""
    assert REG["schema"] == "sahool.component_registry"
    assert isinstance(REG["version"], int)
    assert REG["adjudicated_on"]
    manifest = json.loads(
        (ROOT / "docs" / "architecture" / "manifest_registry.json").read_text(encoding="utf-8")
    )
    entry = next(e for e in manifest["entries"] if e["path"].endswith("component_registry.json"))
    assert entry["kind"] == "governed"


def test_catalog_governance_carries_the_s1a_gate() -> None:
    """بوّابة S1a جزء من حوكمة الكتالوج نفسها — فشلُها يُفشِل البناء والفحص معاً."""
    catalog = json.loads((ROOT / "platform_catalog.generated.json").read_text(encoding="utf-8"))
    gate = catalog["governance"]["s1a_component_classification"]
    assert gate["passed"] is True and gate["failures"] == []
    assert catalog["certification"]["checks"]["s1a_component_classification_passed"] is True


def test_overrides_no_longer_carry_classification() -> None:
    """السقوط الصامت لا يعود من بابه القديم: overrides بلا type/domain لأيّ مكوّن."""
    import yaml

    data = yaml.safe_load(
        (ROOT / "config" / "platform_catalog_overrides.yml").read_text(encoding="utf-8")
    )
    assert data["components"] == {}
    for extra in data["extra_components"]:
        assert "type" not in extra and "domain" not in extra
