"""اختبارات SahoolFormConditionV1 — corpus مشترك backend/Flutter (GAP-FIELD-FORMS-01 §10).

corpus الاختبار الواحد (condition_corpus.json) يعمل على بايثون هنا وعلى Flutter لاحقًا —
قبول/رفض/نتيجة متطابقة حرفيًّا. expect:
  true/false  ⇒ يجتاز validate_condition + evaluate يعيد القيمة
  "error"     ⇒ يجتاز validate_condition لكن evaluate يرفع ConditionTypeError (لا coercion)
  "invalid"   ⇒ validate_condition يرفضه عند النشر (ConditionError)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.contracts.forms.condition_v1 import (
    MAX_ARRAY_ITEMS,
    MAX_NODES,
    MAX_STRING_LENGTH,
    MAX_VAR_PATH_LENGTH,
    ConditionError,
    ConditionTypeError,
    evaluate,
    validate_condition,
)

CORPUS = (
    Path(__file__).resolve().parents[1] / "shared" / "contracts" / "forms" / "condition_corpus.json"
)


def _cases() -> list[dict]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_corpus_case(case: dict) -> None:
    expect = case["expect"]
    if expect == "invalid":
        with pytest.raises(ConditionError):
            validate_condition(case["condition"])
        return
    validate_condition(case["condition"])  # لا يرفع
    if expect == "error":
        with pytest.raises((ConditionTypeError, ConditionError)):
            evaluate(case["condition"], case["answers"])
        return
    assert evaluate(case["condition"], case["answers"]) is expect


# ── حدود DoS الملزمة (§10) — تُرفَض عند النشر ──────────────────────────────────
def test_nodes_limit_enforced() -> None:
    node: dict = {"==": [{"var": "x"}, 1]}
    condition: dict = node
    for _ in range(MAX_NODES):  # and(node, node, …) ينفخ عدد العقد
        condition = {"and": [condition, node]}
    with pytest.raises(ConditionError):
        validate_condition(condition)


def test_array_items_limit_enforced() -> None:
    with pytest.raises(ConditionError):
        validate_condition({"in": [{"var": "x"}, list(range(MAX_ARRAY_ITEMS + 1))]})


def test_string_length_limit_enforced() -> None:
    with pytest.raises(ConditionError):
        validate_condition({"==": [{"var": "x"}, "a" * (MAX_STRING_LENGTH + 1)]})


def test_var_path_length_limit_enforced() -> None:
    with pytest.raises(ConditionError):
        validate_condition({"==": [{"var": "a" * (MAX_VAR_PATH_LENGTH + 1)}, 1]})


def test_nan_literal_rejected() -> None:
    with pytest.raises(ConditionError):
        validate_condition({"==": [{"var": "x"}, float("nan")]})


def test_root_must_be_boolean() -> None:
    with pytest.raises(ConditionTypeError):
        evaluate({"var": "x"}, {"x": 42})
