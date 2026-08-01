"""حارس انعكاس corpus — يمنع انحراف نسخة Dart عن corpus الخادم (GAP-FIELD-FORMS-01 §15.3).

اختبار Flutter يقرأ حالات التكافؤ من ثابت JSON خام في
mobile/sahool_app/test/field_forms/condition_corpus_data.dart (بيئات Flutter المعزولة
لا تصل shared/ من جذر المستودع). هذا الحارس يفرض تطابق الدلالة الكامل بايتًا-معنى
بين الثابت و shared/contracts/forms/condition_corpus.json — أيّ تعديل مستقبليّ
للcorpus الخادميّ يلزم تحديث الانعكاس وإلا يحمرّ CI.

نصّيّ/JSON فقط — لا استيراد لأيّ وحدة (بيئة الوحدة الدنيا).
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "shared/contracts/forms/condition_corpus.json"
DART = ROOT / "mobile/sahool_app/test/field_forms/condition_corpus_data.dart"

_BLOCK = re.compile(r"kConditionCorpusJson\s*=\s*r'''\s*(\[.*?\])\s*'''", re.DOTALL)


def _dart_cases() -> list:
    src = DART.read_text(encoding="utf-8")
    m = _BLOCK.search(src)
    assert m, "condition_corpus_data.dart يجب أن يعرّف kConditionCorpusJson = r'''[...]'''"
    return json.loads(m.group(1))


def test_dart_corpus_mirror_matches_backend():
    backend_cases = json.loads(BACKEND.read_text(encoding="utf-8"))["cases"]
    dart_cases = _dart_cases()
    assert len(dart_cases) == len(backend_cases), (
        f"عدد الحالات يختلف: dart={len(dart_cases)} backend={len(backend_cases)}"
    )
    assert dart_cases == backend_cases, "حالات التكافؤ في Dart لا تطابق corpus الخادم"


def test_dart_corpus_covers_all_expect_kinds():
    expects = {str(c["expect"]) for c in _dart_cases()}
    assert {"True", "False", "error", "invalid"} <= expects
