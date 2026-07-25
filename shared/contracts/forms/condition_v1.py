"""SahoolFormConditionV1 — DSL الظهور الشرطيّ للنماذج الميدانيّة (GAP-FIELD-FORMS-01 §10).

الشكل subset من JSON-logic لكن **الدلالات مملوكة لا مستعارة** (مكتبات JSON-logic تختلف في
coercion/null/in). القواعد الملزمة (المواصفة §10):
  - عوامل مسموحة فقط: var / == != < <= > >= / and or not / in
  - مسار var يُحلّ داخل answers للإرسال الحاليّ فقط — لا عبور خارجه
  - المعاملات ثوابت فقط — لا دوالّ/استيفاء/تقييم JS/eval
  - حدود DoS: عمق <=5 / عقد <=50 / عناصر مصفوفة <=100 / سلسلة <=500 / مسار var <=100
  - in(value, array) عضويّة مصفوفة فقط (لا substring)
  - لا coercion: type mismatch يرفعه المُقيِّم (ConditionTypeError) لا يحوّله
  - var مفقود ==> None ==> أيّ مقارنة مع None ==> False (لا استثناء)
  - and/or ==> boolean فقط / NaN/Infinity مرفوضان في أيّ موضع

وحدة نقيّة (لا FastAPI/قاعدة/شبكة). التحقّق مزدوج: validate_condition عند النشر +
evaluate عند الإرسال خادميًّا. corpus الاختبار المشترك: condition_corpus.json
(يعمل على backend وFlutter — قبول/رفض/نتيجة متطابقة حرفيًّا).
"""

from __future__ import annotations

import math
from typing import Any

CONTRACT_VERSION = "sahool-form-condition.v1"

MAX_DEPTH = 5
MAX_NODES = 50
MAX_ARRAY_ITEMS = 100
MAX_STRING_LENGTH = 500
MAX_VAR_PATH_LENGTH = 100

_COMPARISONS = frozenset({"==", "!=", "<", "<=", ">", ">="})
_LOGIC = frozenset({"and", "or", "not"})
_ALLOWED_OPS = _COMPARISONS | _LOGIC | frozenset({"var", "in"})


class ConditionError(ValueError):
    """بناء شرط غير مسموح (يُرفَض عند النشر)."""


class ConditionTypeError(TypeError):
    """عدم تطابق أنواع عند التقييم — لا coercion (المواصفة §10)."""


def _is_number(value: Any) -> bool:
    # bool ابن int في بايثون — يُستثنى صراحةً (الأنواع صارمة)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_scalar(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None:
        return
    if _is_number(value):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ConditionError(f"non_finite_number at {path}")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise ConditionError(f"string_too_long at {path} (>{MAX_STRING_LENGTH})")
        return
    raise ConditionError(f"forbidden_literal at {path}: {type(value).__name__}")


def _validate_node(node: Any, depth: int, counter: list[int], path: str) -> None:
    if depth > MAX_DEPTH:
        raise ConditionError(f"max_depth_exceeded at {path} (>{MAX_DEPTH})")
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise ConditionError(f"max_nodes_exceeded (>{MAX_NODES})")
    if not isinstance(node, dict) or len(node) != 1:
        # ثابت عاديّ (عُقدة طرفيّة)
        if isinstance(node, list):
            if len(node) > MAX_ARRAY_ITEMS:
                raise ConditionError(f"array_too_large at {path} (>{MAX_ARRAY_ITEMS})")
            for i, item in enumerate(node):
                if isinstance(item, (dict, list)):
                    raise ConditionError(f"nested_structure_literal at {path}[{i}]")
                _check_scalar(item, f"{path}[{i}]")
            return
        _check_scalar(node, path)
        return
    op, args = next(iter(node.items()))
    if op not in _ALLOWED_OPS:
        raise ConditionError(f"operator_not_allowed at {path}: {op!r}")
    if op == "var":
        if not isinstance(args, str) or not args:
            raise ConditionError(f"var_path_must_be_nonempty_string at {path}")
        if len(args) > MAX_VAR_PATH_LENGTH:
            raise ConditionError(f"var_path_too_long at {path} (>{MAX_VAR_PATH_LENGTH})")
        for seg in args.split("."):
            if not seg or seg.startswith("__"):
                raise ConditionError(f"var_path_forbidden_segment at {path}: {seg!r}")
        return
    if not isinstance(args, list):
        raise ConditionError(f"operator_args_must_be_array at {path}: {op}")
    if op in _COMPARISONS or op == "in":
        if len(args) != 2:
            raise ConditionError(f"operator_arity at {path}: {op} expects 2")
    elif op == "not":
        if len(args) != 1:
            raise ConditionError(f"operator_arity at {path}: not expects 1")
    else:  # and/or
        if len(args) < 2:
            raise ConditionError(f"operator_arity at {path}: {op} expects >=2")
    if op == "in":
        # المعامل الثاني مصفوفة ثوابت حرفيًّا (عضويّة مصفوفة فقط — لا substring)
        candidate = args[1]
        if not isinstance(candidate, list):
            raise ConditionError(f"in_requires_array_literal at {path}")
        if len(candidate) > MAX_ARRAY_ITEMS:
            raise ConditionError(f"array_too_large at {path} (>{MAX_ARRAY_ITEMS})")
    for i, arg in enumerate(args):
        _validate_node(arg, depth + 1, counter, f"{path}.{op}[{i}]")


def validate_condition(node: Any) -> None:
    """تحقّق النشر: يرفع ConditionError على أيّ بناء خارج القائمة/الحدود."""
    _validate_node(node, 1, [0], "$")


def _resolve_var(path: str, answers: dict[str, Any]) -> Any:
    current: Any = answers
    for seg in path.split("."):
        if not isinstance(current, dict) or seg not in current:
            return None  # مفقود ==> null ==> كلّ مقارنة false
        current = current[seg]
    return current


def _strict_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if _is_number(left) and _is_number(right):
        return bool(left == right)
    if type(left) is not type(right):
        return False
    return bool(left == right)


def _eval(node: Any, answers: dict[str, Any], depth: int) -> Any:
    if depth > MAX_DEPTH:
        raise ConditionError("max_depth_exceeded at evaluation")
    if not isinstance(node, dict) or len(node) != 1:
        return node  # ثابت
    op, args = next(iter(node.items()))
    if op == "var":
        return _resolve_var(args, answers)
    if op in _LOGIC:
        values = [_eval(a, answers, depth + 1) for a in args]
        for v in values:
            if not isinstance(v, bool):
                raise ConditionTypeError(f"{op}_requires_boolean_operands")
        if op == "and":
            return all(values)
        if op == "or":
            return any(values)
        return not values[0]
    left = _eval(args[0], answers, depth + 1)
    right = _eval(args[1], answers, depth + 1)
    if op == "in":
        if not isinstance(right, list):
            raise ConditionTypeError("in_requires_array_operand")
        return any(_strict_equal(left, item) for item in right)
    # مقارنات: أيّ طرف null ==> false (لا استثناء)
    if left is None or right is None:
        return False
    if _is_number(left) and _is_number(right):
        pass
    elif type(left) is not type(right):
        raise ConditionTypeError(
            f"comparison_type_mismatch: {type(left).__name__} vs {type(right).__name__}"
        )
    for side in (left, right):
        if isinstance(side, float) and (math.isnan(side) or math.isinf(side)):
            raise ConditionError("non_finite_number at evaluation")
    if op == "==":
        return bool(left == right)
    if op == "!=":
        return bool(left != right)
    if op == "<":
        return bool(left < right)
    if op == "<=":
        return bool(left <= right)
    if op == ">":
        return bool(left > right)
    return bool(left >= right)


def evaluate(node: Any, answers: dict[str, Any]) -> bool:
    """تقييم شرط عند الإرسال (خادميّ). يعيد bool صرفًا.

    يرفع ConditionTypeError على type mismatch (لا coercion)، وConditionError على بناء غير
    مسموح — على المتصل تحويل الرفع إلى form_validation_status='invalid' لا إلى خطأ خادم.
    """
    result = _eval(node, answers, 1)
    if not isinstance(result, bool):
        raise ConditionTypeError("condition_root_must_be_boolean")
    return result
