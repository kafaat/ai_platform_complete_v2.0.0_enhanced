"""Field alerts: what the rules emit, what Python allows and what alerts.alert_type accepts agree.

Two defects kept automatic field alerts from ever being created:

* ``_evaluate_field_alerts_persist`` read ``last_ndvi_mean`` from ``fields``; v54 added that
  column to ``imagery_automation_fields`` only, so every evaluation failed (503 on demand,
  DEBUG-level skip in the background loop);
* the alert rules emit ``vegetation_stress`` but v36's CHECK did not list it, so one such
  alert aborted the whole field's batch.

Test doubles accept any column and any value, so nothing caught either.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
V36 = ROOT / "migrations" / "v36_alerts.sql"
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"


def _alert_types() -> set[str]:
    tree = ast.parse((PLATFORM / "api" / "alert_models.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_ALERT_TYPES" for t in node.targets
        ):
            return {e.value for e in node.value.elts}
    raise AssertionError("_ALERT_TYPES not found")


def _emitted_by_rules() -> set[str]:
    text = (PLATFORM / "api" / "alert_rules.py").read_text(encoding="utf-8")
    return set(re.findall(r'alert_type="([a-z_]+)"', text))


def _v36_create_list() -> set[str]:
    text = V36.read_text(encoding="utf-8")
    block = re.search(r"CHECK \(alert_type IN \((.*?)\)\)", text, re.S)
    assert block, "v36 no longer declares alert_type values inline"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def _v36_wanted_list() -> set[str]:
    text = V36.read_text(encoding="utf-8")
    block = re.search(r"wanted\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];", text, re.S)
    assert block, "v36 no longer widens an existing alerts CHECK"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def test_rules_emit_only_allowed_types():
    emitted = _emitted_by_rules()
    assert len(emitted) >= 6, emitted  # a broken extractor would pass on nothing
    assert emitted <= _alert_types(), emitted - _alert_types()


def test_python_and_both_v36_lists_are_identical():
    allowed = _alert_types()
    assert _v36_create_list() == allowed
    assert _v36_wanted_list() == allowed


def test_v36_widening_is_guarded_and_never_validates_blindly():
    text = V36.read_text(encoding="utf-8")
    block = text[text.index("DO $v36_types$") : text.index("END $v36_types$")]
    assert "pg_get_constraintdef" in block and "RETURN;" in block
    assert "NOT VALID" in block and "VALIDATE CONSTRAINT" not in block


def test_v36_is_the_only_manifest_entry_defining_the_alert_type_check():
    entries = [ln.strip() for ln in MANIFEST.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if e and not e.startswith("#")]
    definers = [
        e
        for e in entries
        if re.search(
            r"alert_type\s+IN\s*\(|alerts_alert_type_check",
            (ROOT / "migrations" / e).read_text(encoding="utf-8"),
        )
    ]
    assert definers == [V36.name], definers


def test_no_platform_query_reads_last_ndvi_mean_from_fields():
    offenders = []
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"last_ndvi_mean[^\"']*?FROM\s+fields\b", text):
            offenders.append(f"{rel}:{text[: match.start()].count(chr(10)) + 1}")
    assert not offenders, (
        f"last_ndvi_mean lives in imagery_automation_fields (v54), not fields: {offenders}"
    )


def test_background_field_skip_is_not_silent():
    text = (PLATFORM / "api" / "main.py").read_text(encoding="utf-8")
    assert 'logging.debug("أتمتة التنبيهات: تخطّي حقل' not in text
