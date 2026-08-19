#!/usr/bin/env python3
"""عقد MANIFEST-REGISTRY-01 — سجلّ البيانات التحكيمية محروس ومشتقّ لا يدوي."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "architecture" / "manifest_registry.json"


def _guard():
    spec = importlib.util.spec_from_file_location(
        "manifest_registry_guard", ROOT / "scripts" / "ci" / "manifest_registry_guard.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_registry_exists_and_is_itself_governed() -> None:
    data = _registry()
    assert data["schema"] == "sahool.manifest_registry"
    assert isinstance(data["version"], int) and data["version"] >= 1
    assert "adjudicated_on" in data, "السجلّ بلا تحكيم — حارس أعزل"


def test_registry_matches_derived_inventory() -> None:
    # لا قائمة يدوية: المسجَّل = المشتقّ من git بالقاعدة المعلنة، لا أكثر ولا أقل.
    guard = _guard()
    expected = guard.derive_entries()
    registered = {e["path"]: e["kind"] for e in _registry()["entries"]}
    assert registered == expected, (
        f"انحراف: ناقص={sorted(set(expected) - set(registered))} "
        f"زائد={sorted(set(registered) - set(expected))} — أعد التوليد بـ--fix"
    )


def test_every_entry_file_exists_and_matches_kind_keys() -> None:
    guard = _guard()
    for entry in _registry()["entries"]:
        errors: list[str] = []
        guard.validate_manifest(entry["path"], entry["kind"], errors)
        assert not errors, errors


def test_check_passes_on_current_tree() -> None:
    assert _guard().check(fix=False) == 0


def test_nested_architecture_evidence_is_out_of_manifest_registry_scope() -> None:
    # git pathspec docs/architecture/*.json matches descendants too. The registry contract
    # governs direct manifests only; nested evidence payloads may legitimately be JSON arrays.
    guard = _guard()
    tracked = guard.tracked_manifests()
    assert "docs/architecture/evidence/s4_kg_parity_cases.json" not in tracked
    assert guard.derive_entries() == {e["path"]: e["kind"] for e in _registry()["entries"]}


def test_unregistered_adjudicated_manifest_is_caught() -> None:
    # تزييف حقيقي: بيان محكَّم يدخل الشجرة بلا تسجيل يجب أن يُقبض، ثم يُحذف
    # فيعود الأخضر — يثبت أن القبض على الجرد الفعلي لا على نسخة قديمة.
    fake = ROOT / "docs" / "architecture" / "zz_fake_unregistered_adjudicated.json"
    fake.write_text(json.dumps({"adjudicated_on": "2026-08-05"}) + "\n", encoding="utf-8")
    try:
        import subprocess

        subprocess.run(["git", "add", "-f", str(fake.relative_to(ROOT))], cwd=ROOT, check=True)
        assert _guard().check(fix=False) == 1, "بيان محكَّم غير مسجَّل نجا"
    finally:
        fake.unlink(missing_ok=True)
        import subprocess

        subprocess.run(
            ["git", "rm", "-q", "--cached", "--ignore-unmatch", str(fake.relative_to(ROOT))],
            cwd=ROOT,
        )
    assert _guard().check(fix=False) == 0


def test_kind_violation_is_caught() -> None:
    # تزييف: ملف legacy يُقيَّم بقيود governed يجب أن يُرفض (بلا schema/version).
    guard = _guard()
    errors: list[str] = []
    guard.validate_manifest("docs/architecture/claim_base_registry.json", "governed", errors)
    assert errors, "ملف legacy مرّ كـgoverned — قيود الصنف مكسورة"
    assert any("schema" in e or "version" in e for e in errors)


def test_new_legacy_manifest_is_rejected_by_the_ratchet() -> None:
    # الراتشة: بيان جديد بلا schema/version لا يكفي تسجيله — يُرفض إن لم يكن governed.
    fake = ROOT / "docs" / "architecture" / "zz_fake_new_legacy.json"
    fake.write_text(json.dumps({"adjudicated_on": "2026-08-05"}) + "\n", encoding="utf-8")
    try:
        import subprocess

        subprocess.run(["git", "add", "-f", str(fake.relative_to(ROOT))], cwd=ROOT, check=True)
        errors: list[str] = []
        expected = _guard().derive_entries(errors)
        assert expected[fake.relative_to(ROOT).as_posix()] == "legacy_adjudicated"
        assert _guard().check(fix=False) == 1, "بيان جديد بصنف legacy نجا من الراتشة"
    finally:
        fake.unlink(missing_ok=True)
        import subprocess

        subprocess.run(
            ["git", "rm", "-q", "--cached", "--ignore-unmatch", str(fake.relative_to(ROOT))],
            cwd=ROOT,
        )
    assert _guard().check(fix=False) == 0


def test_corrupt_json_is_caught_not_swallowed() -> None:
    # fail-closed: ملف JSON فاسد داخل النطاق يجب أن يُبلَّغ لا أن يخرج من الجرد صامتاً.
    fake = ROOT / "docs" / "architecture" / "zz_fake_corrupt.json"
    fake.write_text("{فاسد", encoding="utf-8")
    try:
        import subprocess

        subprocess.run(["git", "add", "-f", str(fake.relative_to(ROOT))], cwd=ROOT, check=True)
        errors: list[str] = []
        _guard().derive_entries(errors)
        assert errors and "zz_fake_corrupt" in errors[0], "JSON فاسد ابتُلع بصمت"
        assert _guard().check(fix=False) == 1
    finally:
        fake.unlink(missing_ok=True)
        import subprocess

        subprocess.run(
            ["git", "rm", "-q", "--cached", "--ignore-unmatch", str(fake.relative_to(ROOT))],
            cwd=ROOT,
        )
    assert _guard().check(fix=False) == 0
