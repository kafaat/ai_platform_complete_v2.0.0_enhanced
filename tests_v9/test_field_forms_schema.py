"""اختبارات schema_v1 — عقد الحقول + تحقّق الإجابات خادميًّا (GAP-FIELD-FORMS-01 §8/§12)."""

from __future__ import annotations

import pytest

from shared.contracts.forms.schema_v1 import (
    SchemaError,
    canonical_answers_hash,
    validate_answers,
    validate_form_schema,
    visible_fields,
)

SCHEMA = {
    "fields": [
        {"key": "crop", "field_type": "select", "options": ["wheat", "barley"], "required": True},
        {"key": "severity", "field_type": "number", "validation_rules": {"min": 0, "max": 5}},
        {"key": "notes", "field_type": "text", "validation_rules": {"max_length": 200}},
        {"key": "spray_date", "field_type": "date"},
        {"key": "location", "field_type": "gps"},
    ]
}
# severity يظهر فقط عند crop=wheat (ظهور شرطيّ)
LOGIC = {"severity": {"==": [{"var": "crop"}, "wheat"]}}


def test_valid_schema_passes() -> None:
    validate_form_schema(SCHEMA, LOGIC)


def test_unknown_field_type_rejected() -> None:
    bad = {"fields": [{"key": "x", "field_type": "widget_flutter_column"}]}
    with pytest.raises(SchemaError):
        validate_form_schema(bad, None)


def test_logic_targeting_unknown_field_rejected() -> None:
    with pytest.raises(SchemaError):
        validate_form_schema(SCHEMA, {"ghost": {"==": [{"var": "crop"}, "wheat"]}})


def test_logic_dsl_outside_whitelist_rejected_at_publish() -> None:
    with pytest.raises(SchemaError):
        validate_form_schema(SCHEMA, {"severity": {"cat": [1, 2]}})


def test_visibility_evaluated_server_side() -> None:
    assert visible_fields(SCHEMA, LOGIC, {"crop": "wheat"}) >= {"severity"}
    assert "severity" not in visible_fields(SCHEMA, LOGIC, {"crop": "barley"})


def test_answer_for_hidden_field_invalid() -> None:
    _normalized, errors = validate_answers(SCHEMA, LOGIC, {"crop": "barley", "severity": 3})
    assert any("answer_for_hidden_field" in e for e in errors)


def test_required_only_when_visible() -> None:
    schema = {
        "fields": [
            {**SCHEMA["fields"][0], "required": True},
            {**SCHEMA["fields"][1], "required": True},
        ]
    }
    _n, errors = validate_answers(schema, LOGIC, {"crop": "barley"})
    assert not any("required_missing: severity" in e for e in errors)


def test_no_coercion_types() -> None:
    _n, errors = validate_answers(SCHEMA, LOGIC, {"crop": "wheat", "severity": "3"})
    assert any("expected_number" in e for e in errors)


def test_gps_bounds() -> None:
    _n, errors = validate_answers(
        SCHEMA, LOGIC, {"crop": "wheat", "location": {"lat": 95, "lng": 44}}
    )
    assert any("gps_lat_out_of_range" in e for e in errors)


def test_unknown_answer_key_invalid() -> None:
    _n, errors = validate_answers(SCHEMA, LOGIC, {"crop": "wheat", "smuggled": 1})
    assert any("unknown_answer_key" in e for e in errors)


def test_canonical_hash_stable() -> None:
    assert canonical_answers_hash({"b": 1, "a": 2}) == canonical_answers_hash({"a": 2, "b": 1})


# ── P0-4 (مراجعة PR #585): قواعد validation مُنوَّعة ومغلقة القائمة عند النشر ──


def _schema_with_rules(rules: dict) -> dict:
    return {"fields": [{"key": "notes", "field_type": "text", "validation_rules": rules}]}


def test_untyped_min_length_rejected_at_publish() -> None:
    """مثال المراجعة حرفيًّا: "min_length": "five" يُرفَض عند التعريف لا عند الإرسال."""
    with pytest.raises(SchemaError, match="validation_rule_type_int"):
        validate_form_schema(_schema_with_rules({"min_length": "five"}), None)


def test_bool_rule_rejected_at_publish() -> None:
    with pytest.raises(SchemaError, match="validation_rule_type_int"):
        validate_form_schema(_schema_with_rules({"max_length": True}), None)


def test_unknown_rule_key_rejected_at_publish() -> None:
    with pytest.raises(SchemaError, match="validation_rule_unknown"):
        validate_form_schema(_schema_with_rules({"minLength": 3}), None)


def test_negative_length_rejected_at_publish() -> None:
    with pytest.raises(SchemaError, match="validation_rule_negative"):
        validate_form_schema(_schema_with_rules({"min_length": -1}), None)


def test_inverted_length_bounds_rejected() -> None:
    with pytest.raises(SchemaError, match="validation_rule_inverted_length"):
        validate_form_schema(_schema_with_rules({"min_length": 10, "max_length": 3}), None)


def test_untyped_numeric_range_rejected_at_publish() -> None:
    bad = {"fields": [{"key": "sev", "field_type": "number", "validation_rules": {"min": "0"}}]}
    with pytest.raises(SchemaError, match="validation_rule_type_number"):
        validate_form_schema(bad, None)


def test_inverted_numeric_range_rejected() -> None:
    bad = {
        "fields": [
            {"key": "sev", "field_type": "number", "validation_rules": {"min": 5, "max": 1}}
        ]
    }
    with pytest.raises(SchemaError, match="validation_rule_inverted_range"):
        validate_form_schema(bad, None)


def test_valid_typed_rules_still_pass() -> None:
    validate_form_schema(_schema_with_rules({"min_length": 1, "max_length": 200}), None)


def test_legacy_bad_rules_no_typeerror_at_submission() -> None:
    """دفاع عمق: نسخة منشورة قديمة بقواعد معطوبة ⇒ خطأ تحقّق نظيف (validation_rules_invalid)
    لا TypeError — تُحجَر الإجابة بدل انفجار وقت التشغيل."""
    legacy = {
        "fields": [
            {"key": "notes", "field_type": "text", "validation_rules": {"min_length": "five"}}
        ]
    }
    _, errors = validate_answers(legacy, None, {"notes": "abc"})
    assert any("validation_rules_invalid" in e for e in errors), errors
