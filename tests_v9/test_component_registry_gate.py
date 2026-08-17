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
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load_compiler()
REG = json.loads(REGISTRY.read_text(encoding="utf-8"))

# قياس متّسق اصطناعيّ مشتقّ من السجلّ نفسه — أساس التحوير في كلّ اختبار سلبيّ.
_CONSISTENT = {
    cid: {
        "deployment_units": list(e["deployment_units"]),
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
        "deployment_units": [],
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


def test_declared_deployment_units_must_match_measured() -> None:
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["deployment_units"] = ["wrong-unit"]
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "deployment_units" in f for f in failures)


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
        assert r["deployment_units"] == "|".join(entry["deployment_units"]), r["component_id"]


def test_shipped_csv_header_is_the_s1a_schema() -> None:
    catalog = json.loads((ROOT / "platform_catalog.generated.json").read_text(encoding="utf-8"))
    header = MOD._components_csv(catalog).splitlines()[0]
    assert header.split(",")[:6] == [
        "component_id",
        "component_kind",
        "deployment_units",
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


def test_missing_required_field_is_a_measured_failure_not_a_crash() -> None:
    """مفتاح غائب في صفّ السجلّ يفشل بالاسم — لا KeyError يُقرأ عطلَ أداة."""
    registry = copy.deepcopy(REG)
    del registry["components"]["auth"]["component_kind"]
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "حقول إلزاميّة غائبة" in f for f in failures)


def test_unclassified_domain_is_a_measured_failure() -> None:
    """domain جزء من عقد «صفر غير مصنَّف» — الفراغ أو unclassified يفشل لا يسقط صامتاً."""
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["domain"] = "unclassified"
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "domain" in f for f in failures)
    registry["components"]["auth"]["domain"] = ""
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("auth" in f and "domain" in f for f in failures)


def test_overrides_no_longer_carry_classification() -> None:
    """السقوط الصامت لا يعود من بابه القديم: overrides بلا type/domain لأيّ مكوّن."""
    import yaml

    data = yaml.safe_load(
        (ROOT / "config" / "platform_catalog_overrides.yml").read_text(encoding="utf-8")
    )
    assert data["components"] == {}
    for extra in data["extra_components"]:
        assert "type" not in extra and "domain" not in extra


# ── ARCH-S2: حقيقة الاعتماد — قياس البناء يحلّ الوحدات، والإغلاق تامّ ─


def _measured_units() -> dict[str, list[str]]:
    return {cid: list(m["deployment_units"]) for cid, m in _CONSISTENT.items()}


def _measured_infra() -> list[str]:
    return list(REG["infrastructure_units"])


def test_s2_consistent_truth_yields_zero_failures() -> None:
    assert MOD.dependency_truth_failures(REG, _measured_units(), _measured_infra(), {}) == []


def test_s2_unresolved_compose_unit_is_a_measured_failure() -> None:
    """خدمة تُبنى من مصدرٍ لا مكوّن له لا تمرّ صامتة — صنف اليتيمَين المقيسَين."""
    failures = MOD.dependency_truth_failures(
        REG, _measured_units(), _measured_infra(), {"sahool-ghost": "services/ghost"}
    )
    assert any("unresolved compose unit: sahool-ghost" in f for f in failures)


def test_s2_undeclared_infrastructure_is_a_measured_failure() -> None:
    failures = MOD.dependency_truth_failures(
        REG, _measured_units(), _measured_infra() + ["sahool-new-infra"], {}
    )
    assert any("sahool-new-infra" in f for f in failures)


def test_s2_stale_infrastructure_declaration_is_a_measured_failure() -> None:
    infra = [u for u in _measured_infra() if u != "sahool-postgres"]
    failures = MOD.dependency_truth_failures(REG, _measured_units(), infra, {})
    assert any("sahool-postgres" in f for f in failures)


def test_s2_declared_units_must_match_measured() -> None:
    units = _measured_units()
    units["sahool-platform"] = [u for u in units["sahool-platform"] if u != "sahool-platform"]
    failures = MOD.dependency_truth_failures(REG, units, _measured_infra(), {})
    assert any("sahool-platform" in f and "deployment_units" in f for f in failures)


def test_s2_build_source_resolution_is_measured_not_guessed() -> None:
    """dockerfile يسمّي المصدر؛ context حين لا يكون الجذر؛ image-only ⇒ None."""
    assert (
        MOD.resolve_build_source({"build": {"context": ".", "dockerfile": "services/x/Dockerfile"}})
        == "services/x"
    )
    assert (
        MOD.resolve_build_source({"build": {"context": "services/model-registry-adapter"}})
        == "services/model-registry-adapter"
    )
    assert MOD.resolve_build_source({"build": {"context": "./frontend"}}) == "frontend"
    assert MOD.resolve_build_source({"image": "redis:7-alpine"}) is None


def test_build_source_strips_only_one_dot_slash_prefix() -> None:
    assert MOD.resolve_build_source({"build": "./services/foo"}) == "services/foo"


@pytest.mark.parametrize(
    "build",
    [
        {"context": "../outside"},
        {"context": "../../outside"},
        {"context": "/absolute/outside"},
        {"context": ".", "dockerfile": "../outside/Dockerfile"},
        {"context": ".", "dockerfile": "/abs/Dockerfile"},
    ],
)
def test_s2_build_source_cannot_escape_repository(build) -> None:
    """حكم المالك على #863: الهروب من الشجرة يُرفض برفعٍ صريح قبل أيّ تطبيع —
    لا تصحيحَ صامتاً يجعل الخارجيّ يبدو داخليّاً. الحماية على context
    وdockerfile معاً (ثقب dockerfile وجده تدقيق المالك لا مراجعة Copilot)."""
    with pytest.raises(ValueError, match="repository"):
        MOD.resolve_build_source({"build": build})


def test_duplicate_component_source_path_fails_closed() -> None:
    """سلطة المصدر واحدة: مكوّنان بsource_path نفسه تنازعٌ يُحسم بالفشل لا بصمت القاموس."""
    registry = copy.deepcopy(REG)
    registry["components"]["auth"]["source_path"] = registry["components"][
        "field-management-service"
    ]["source_path"]
    failures = MOD.component_classification_failures(registry, copy.deepcopy(_CONSISTENT))
    assert any("duplicate source_path" in f for f in failures)


def test_catalog_loads_compose_once(monkeypatch) -> None:
    """عقد اللقطة الواحدة: docker-compose.v9.yml يُقرأ مرّةً لكلّ تصريف —
    قراءةٌ ثانية تكسر اتّساق القياس لا الأداء فقط."""
    calls = 0
    original = MOD._load_yaml

    def counted(rel):
        nonlocal calls
        if rel == "docker-compose.v9.yml":
            calls += 1
        return original(rel)

    monkeypatch.setattr(MOD, "_load_yaml", counted)
    MOD.build()
    assert calls == 1


def test_s2_former_orphans_are_now_classified_components() -> None:
    """اليتيمان المقيسان من compose دخلا الجرد بدل إخفائهما."""
    assert REG["components"]["telegram-bot"]["source_path"] == "bots/telegram"
    assert REG["components"]["notification-agent"]["source_path"] == "agents/notification"
    catalog = json.loads((ROOT / "platform_catalog.generated.json").read_text(encoding="utf-8"))
    ids = {c["component_id"] for c in catalog["components"]}
    assert {"telegram-bot", "notification-agent"} <= ids


def test_s2_full_compose_closure_on_the_shipped_tree() -> None:
    """الإغلاق التامّ: كلّ خدمة compose وحدةُ مكوّن أو بنية تحتيّة معلَنة — لا ثالث."""
    import yaml

    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    all_units = set(compose["services"])
    component_units = {u for e in REG["components"].values() for u in e["deployment_units"]}
    infra = set(REG["infrastructure_units"])
    assert component_units | infra == all_units
    assert not component_units & infra
