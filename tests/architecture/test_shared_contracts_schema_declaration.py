#!/usr/bin/env python3
"""عقد إعلان المخططات — كل *.schema.json يُعلن ميتا-مخططه ويُتحقق منه قياسياً.

الفجوة المعالجة: 11 مخططاً على main كانت بلا `$schema` (9 في
shared/contracts/remote_sensing/schemas/ و2 في shared/contracts/soil/) —
مجهولة المواصفة فلا يُعرف بأي Draft تُقرأ. هذا العقد يمنع عودة النمط:
مخطط جديد بلا إعلان = فشل صريح، وإعلان بمواصفة لا يطابقها = فشل صريح.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILES = sorted(
    p for p in ROOT.rglob("*.schema.json") if ".git" not in p.parts
)

try:
    import jsonschema
except ImportError as e:  # فشل صريح لا تخطٍّ — التبعية جزء من العقد
    raise AssertionError(
        "pip install jsonschema — التحقق القياسي يتطلبها (فشل صريح لا تخطٍّ صامت)"
    ) from e

_VALIDATORS = {
    "https://json-schema.org/draft/2020-12/schema": jsonschema.Draft202012Validator,
    "http://json-schema.org/draft-07/schema#": jsonschema.Draft7Validator,
    "http://json-schema.org/draft-04/schema#": jsonschema.Draft4Validator,
}


def test_schema_files_discovered() -> None:
    # حارس ضد مسار اكتشاف مكسور يعيد «صفر مخططات = نجاح كاذب»
    assert len(SCHEMA_FILES) >= 15, f"اكتُشف {len(SCHEMA_FILES)} فقط — مسار الاكتشاف مكسور"


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_declares_meta_schema(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "$schema" in data, f"{path.relative_to(ROOT)} بلا إعلان $schema — مجهول المواصفة"
    assert data["$schema"] in _VALIDATORS, (
        f"{path.relative_to(ROOT)} يُعلن مواصفة غير مدعومة: {data['$schema']}"
    )


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_conforms_to_declared_meta(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    validator_cls = _VALIDATORS.get(data.get("$schema"))
    if validator_cls is None:
        pytest.fail(f"مواصفة غير مدعومة في {path.relative_to(ROOT)}")
    validator_cls.check_schema(data)  # إعلان بمواصفة لا يطابقها = فشل
