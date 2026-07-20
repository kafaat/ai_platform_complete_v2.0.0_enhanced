"""SahoolFormSchemaV1 — عقد schema النموذج الميدانيّ + تحقّق الإجابات (GAP-FIELD-FORMS-01 §8/§10/§12).

يفصل العقد عن العرض (§8): لكلّ حقل field_type (من القائمة المثبَّتة) + storage_value +
validation_rules + presentation_hint **استشاريّ فقط — لا أسماء Flutter widgets في العقد الخادميّ**.
واجهة العميل تُولَّد من الـschema (برهان الشريحة الوجوديّ §15).

التحقّق مزدوج (§10): validate_form_schema عند النشر (بنية + DSL + مراجع var) و
validate_answers عند الإرسال خادميًّا (لا يُكتفى بفحص العميل):
  - الظهور الشرطيّ يُقيَّم خادميًّا؛ إجابة لحقل خفيّ ⇒ invalid (صارم)
  - required يُفرَض على الظاهر فقط
  - مفاتيح مجهولة ⇒ invalid
  - أنواع صارمة بلا coercion
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from shared.contracts.forms.condition_v1 import (
    ConditionError,
    ConditionTypeError,
    evaluate,
    validate_condition,
)

SCHEMA_CONTRACT_VERSION = "sahool-form-schema.v1"
NORMALIZER_VERSION = "1.0.0"

# القائمة المثبَّتة (§8) — لا نوع جديد في الشريحة الأولى
FIELD_TYPES = frozenset({"text", "number", "integer", "select", "multi_select", "date", "gps", "photo"})
# ملاحظة: integer فئة تخزين مستقلّة عن number (لا coercion بينهما).

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SchemaError(ValueError):
    """بنية schema/logic غير صالحة — يُرفَض النشر."""


def _err(msg: str) -> SchemaError:
    return SchemaError(msg)


def validate_form_schema(schema_json: Any, logic_json: Any) -> None:
    """تحقّق النشر: يرفع SchemaError على أيّ خلل بنيويّ/DSL/مرجع."""
    if not isinstance(schema_json, dict):
        raise _err("schema_must_be_object")
    fields = schema_json.get("fields")
    if not isinstance(fields, list) or not fields:
        raise _err("schema_fields_nonempty_array")
    keys: set[str] = set()
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            raise _err(f"field_not_object at [{i}]")
        key = field.get("key")
        if not isinstance(key, str) or not _KEY_RE.match(key):
            raise _err(f"field_key_invalid at [{i}]")
        if key in keys:
            raise _err(f"field_key_duplicate: {key}")
        keys.add(key)
        ftype = field.get("field_type")
        if ftype not in FIELD_TYPES:
            raise _err(f"field_type_not_allowed: {ftype!r} at {key}")
        hint = field.get("presentation_hint")
        if hint is not None and not isinstance(hint, str):
            raise _err(f"presentation_hint_must_be_string at {key}")
        rules = field.get("validation_rules", {})
        if rules is not None and not isinstance(rules, dict):
            raise _err(f"validation_rules_must_be_object at {key}")
        if ftype in ("select", "multi_select"):
            options = field.get("options")
            if not isinstance(options, list) or not options or not all(
                isinstance(o, str) for o in options
            ):
                raise _err(f"select_requires_string_options at {key}")
    if logic_json is None:
        return
    if not isinstance(logic_json, dict):
        raise _err("logic_must_be_object")
    for key, condition in logic_json.items():
        if key not in keys:
            raise _err(f"logic_targets_unknown_field: {key}")
        try:
            validate_condition(condition)
        except ConditionError as exc:
            raise _err(f"logic_condition_invalid at {key}: {exc}") from exc
        for var_path in _collect_var_paths(condition):
            if var_path.split(".")[0] not in keys:
                raise _err(f"logic_references_unknown_field: {var_path} at {key}")


def _collect_var_paths(node: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(node, dict) and len(node) == 1:
        op, args = next(iter(node.items()))
        if op == "var" and isinstance(args, str):
            paths.append(args)
        elif isinstance(args, list):
            for a in args:
                paths.extend(_collect_var_paths(a))
    elif isinstance(node, list):
        for a in node:
            paths.extend(_collect_var_paths(a))
    return paths


def visible_fields(schema_json: dict[str, Any], logic_json: Any, answers: dict[str, Any]) -> set[str]:
    """يُقيِّم الظهور الشرطيّ خادميًّا. بلا logic ⇒ كلّ الحقول ظاهرة."""
    keys = {f["key"] for f in schema_json["fields"]}
    if not logic_json:
        return keys
    visible = set(keys)
    for key, condition in logic_json.items():
        if not evaluate(condition, answers):
            visible.discard(key)
    return visible


def validate_answers(
    schema_json: dict[str, Any], logic_json: Any, answers: Any
) -> tuple[dict[str, Any], list[str]]:
    """يتحقّق من الإجابات ويعيد (المُطبَّعة, الأخطاء). أخطاء غير فارغة ⇒ form_validation_status='invalid'.

    صارم: إجابة لحقل خفيّ أو مفتاح مجهول ⇒ خطأ. لا coercion للأنواع.
    """
    if not isinstance(answers, dict):
        return {}, ["answers_must_be_object"]
    errors: list[str] = []
    fields_by_key = {f["key"]: f for f in schema_json["fields"]}
    try:
        visible = visible_fields(schema_json, logic_json, answers)
    except (ConditionError, ConditionTypeError) as exc:
        return {}, [f"condition_evaluation_failed: {exc}"]
    normalized: dict[str, Any] = {}
    for key, value in answers.items():
        field = fields_by_key.get(key)
        if field is None:
            errors.append(f"unknown_answer_key: {key}")
            continue
        if key not in visible:
            errors.append(f"answer_for_hidden_field: {key}")
            continue
        err = _validate_value(field, value)
        if err:
            errors.append(f"{key}: {err}")
        else:
            normalized[key] = value
    for key in visible:
        field = fields_by_key[key]
        if field.get("required") and key not in answers:
            errors.append(f"required_missing: {key}")
    return normalized, errors


def _validate_value(field: dict[str, Any], value: Any) -> str | None:
    ftype = field["field_type"]
    rules = field.get("validation_rules") or {}
    if ftype == "text":
        if not isinstance(value, str):
            return "expected_string"
        if "min_length" in rules and len(value) < rules["min_length"]:
            return "below_min_length"
        if "max_length" in rules and len(value) > rules["max_length"]:
            return "above_max_length"
        return None
    if ftype == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "expected_number"
        if "min" in rules and value < rules["min"]:
            return "below_min"
        if "max" in rules and value > rules["max"]:
            return "above_max"
        return None
    if ftype == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return "expected_integer"
        if "min" in rules and value < rules["min"]:
            return "below_min"
        if "max" in rules and value > rules["max"]:
            return "above_max"
        return None
    if ftype == "select":
        if not isinstance(value, str) or value not in (field.get("options") or []):
            return "not_in_options"
        return None
    if ftype == "multi_select":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return "expected_string_array"
        options = set(field.get("options") or [])
        if any(v not in options for v in value):
            return "not_in_options"
        return None
    if ftype == "date":
        if not isinstance(value, str) or not _DATE_RE.match(value):
            return "expected_date_yyyy_mm_dd"
        return None
    if ftype == "gps":
        if not isinstance(value, dict):
            return "expected_gps_object"
        lat, lng = value.get("lat"), value.get("lng")
        if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not -90 <= lat <= 90:
            return "gps_lat_out_of_range"
        if not isinstance(lng, (int, float)) or isinstance(lng, bool) or not -180 <= lng <= 180:
            return "gps_lng_out_of_range"
        return None
    if ftype == "photo":
        if not isinstance(value, str) or not value:
            return "expected_photo_ref"
        return None
    return "unknown_field_type"


def canonical_answers_hash(normalized: dict[str, Any]) -> str:
    """sha256 للإجابات المُطبَّعة (JSON مفروز المفاتيح) — answers_hash للتدقيق وreplay."""
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
