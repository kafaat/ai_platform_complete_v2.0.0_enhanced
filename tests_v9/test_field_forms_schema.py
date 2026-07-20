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
