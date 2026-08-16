"""A′-4b — تقارب الكتّاب: الحقول canonical-owned تُكتَب من مالكها وحده.

الشاهد المقيس حيّاً: بعد إسقاط سلطة الكتابة من الرابط وتشغيل المُسقِط، اختفت
هويّات INT-004 الثلاث من المرصود فأحمرّ الراتشِت بالأساس البائت — بالضبط كما
تنبّأ المالك («هذا سيكون دليلًا ممتازًا أن A′-4 حقيقية وليست cosmetic») —
ثمّ خُفِّض الأساس 3→0.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_projection_sync.py"


def _load():
    spec = importlib.util.spec_from_file_location("capability_projection_sync_under_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture(root: Path, canonical_rows: list[dict], legacy_rows: list[dict]) -> None:
    policy = {
        "schema": "sahool.capability-field-authority/v1",
        "field_authority": {
            "id": {"authority": "canonical_capability_definition"},
            "domain": {"authority": "canonical_capability_definition"},
            "dependencies": {"authority": "canonical_capability_definition"},
            "maturity": {"authority": "canonical_capability_definition"},
            "evidence_level": {"authority": "canonical_capability_definition"},
            "owner": {"authority": "canonical_capability_definition"},
            "runtime_verified": {"authority": "runtime_verification"},
        },
        "reconciliation": {"no_third_value_registry": True},
    }
    for rel, payload in {
        "docs/capability-registry/field_authority_policy.json": policy,
        "docs/capability-registry/generated/capability_registry.json": {
            "capabilities": canonical_rows
        },
        "capabilities/registry/capabilities.json": {"capabilities": legacy_rows},
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def _canonical_row(**over) -> dict:
    base = {
        "id": "INT-004",
        "domain": "precision",
        "dependencies": ["PA-005"],
        "maturity": 3,
        "evidence_level": 3,
        "owner": "sahool-platform",
    }
    base.update(over)
    return base


def _legacy_row(**over) -> dict:
    base = _canonical_row(
        title="External machinery integrations",
        services=["services/x/main.py"],
        runtime={"receipts": []},
        runtime_verified=False,
        production_certified=False,
    )
    base.update(over)
    return base


def test_the_shipped_projection_is_converged_zero_drift():
    """بوّابة الشحن: الإسقاط الحيّ متقارب — حقلٌ canonical بائت يحمّر CI باسمه."""
    module = _load()

    identities, synced, fields = module.drift()

    assert identities == []
    assert len(fields) == 7
    assert "lifecycle" in fields
    assert len(synced["capabilities"]) == 81


def test_projection_follows_the_canonical_value_not_the_other_way(tmp_path):
    """الاشتقاق آليّ لا تحريرَ يدويّاً: تغيّر القانونيّ يظهر انحرافاً مسمّىً
    وتُسقَط قيمتُه — والإسقاط لا يستطيع «إقناع» القانونيّ بقيمته البائتة."""
    module = _load()
    _write_fixture(
        tmp_path,
        [_canonical_row(maturity=4, owner="new-owner")],
        [_legacy_row()],
    )

    identities, synced, _fields = module.drift(tmp_path)

    assert identities == ["INT-004:maturity", "INT-004:owner"]
    [row] = synced["capabilities"]
    assert row["maturity"] == 4
    assert row["owner"] == "new-owner"


def test_non_canonical_fields_are_never_touched_by_the_projector(tmp_path):
    """المُسقِط يكتب ما تملكه السلطة القانونيّة فقط — الحقول المتحوّلة وحقول
    إسقاط المستودع لكتّابها المخوَّلين."""
    module = _load()
    _write_fixture(
        tmp_path,
        [_canonical_row(maturity=5)],
        [_legacy_row(title="KEEP-ME", services=["services/keep/main.py"], runtime_verified=True)],
    )

    identities, synced, _fields = module.drift(tmp_path)

    assert identities == ["INT-004:maturity"]
    [row] = synced["capabilities"]
    assert row["title"] == "KEEP-ME"
    assert row["services"] == ["services/keep/main.py"]
    assert row["runtime_verified"] is True


def test_identity_disagreement_fails_closed(tmp_path):
    module = _load()
    _write_fixture(tmp_path, [_canonical_row(id="A")], [_legacy_row(id="B")])

    try:
        module.drift(tmp_path)
    except module.ProjectionSyncError as exc:
        assert "identity sets disagree" in str(exc)
    else:
        raise AssertionError("identity drift must fail closed")


def test_a_permissive_or_nested_policy_is_refused(tmp_path):
    module = _load()
    _write_fixture(tmp_path, [_canonical_row()], [_legacy_row()])
    policy_path = tmp_path / "docs/capability-registry/field_authority_policy.json"
    doc = json.loads(policy_path.read_text(encoding="utf-8"))
    doc["reconciliation"]["no_third_value_registry"] = False
    policy_path.write_text(json.dumps(doc), encoding="utf-8")
    try:
        module.drift(tmp_path)
    except module.ProjectionSyncError as exc:
        assert "third value registry" in str(exc)
    else:
        raise AssertionError("permissive policy must be refused")

    doc["reconciliation"]["no_third_value_registry"] = True
    doc["field_authority"]["runtime.nested"] = {"authority": "canonical_capability_definition"}
    policy_path.write_text(json.dumps(doc), encoding="utf-8")
    try:
        module.drift(tmp_path)
    except module.ProjectionSyncError as exc:
        assert "explicit merger" in str(exc)
    else:
        raise AssertionError("nested canonical field must be refused")


def _assignment_pattern(field: str) -> re.Pattern[str]:
    """إسنادٌ إلى ``cap[<field>]`` بأيّ تنويع تنسيق: اقتباس مفرد أو مزدوج،
    فراغات حرّة، إسناد بسيط أو مركَّب — مراجعةٌ آليّة أصابت في أنّ المطابقة
    الحرفيّة تُتجاوَز بتنويع تنسيقٍ بريء الشكل."""
    return re.compile(r"cap\s*\[\s*['\"]" + re.escape(field) + r"['\"]\s*\]\s*[-+*/|&^%]?=(?!=)")


def test_the_linker_no_longer_writes_canonical_owned_fields():
    """قفل A′-4b: الرابط فقد سلطة كتابة `dependencies` و`owner` — عودةُ أيّ
    سطر كتابةٍ لهما بأيّ صياغة تُحمِّر هذا الاختبار قبل أن تصل CI."""
    source = (ROOT / "scripts/ci/capability_linker.py").read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )

    assert not _assignment_pattern("owner").search(executable)
    assert not _assignment_pattern("dependencies").search(executable)
    # والحقول التي يملكها بحقّ باقية له:
    assert _assignment_pattern("services").search(executable)
    assert _assignment_pattern("apis").search(executable)
