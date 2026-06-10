"""Unit test (CI-enforced) for the /api/v1/recommendations/for-field chain.

يحرس الربط الجديد: بناء «شهادة الجودة» (validation) خادميّاً عبر
validate_observations ثمّ استدعاء المحرّك الحقيقيّ (handle_recommendation_request).
صدق: مستأجر بلا ملاحظات ⇒ شهادة محجوبة، لكنّ المحرّك يُسلّم توصية محدودة (لا
سيناريو مفبرَك) — وهو السلوك المُصمَّم لبوّابة الجودة.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.mark.unit
def test_for_field_chain_builds_validation_and_delivers(tmp_path):
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    import validate_observations as vo
    from core.api_adapter import ApiRequest, handle_recommendation_request
    from core.canonical_schemas import UserRole, UserSchema

    # مستأجر بلا ملاحظات ⇒ شهادة جودة حقيقيّة (محجوبة) لا مفبركة.
    validation = vo.validate(tmp_path)
    assert "quality_grade" in validation
    assert "missing_A" in validation

    u = UserSchema(user_id="u1", tenant_id="t1", role=UserRole.AGRONOMIST, name_ar="م")
    req = ApiRequest(
        user=u,
        payload={
            "tenant_id": "t1",
            "farm_id": "f1",
            "field_id": "fld1",
            "crop": "قمح صلب",
            "validation": validation,
            "current_indicators": {"ndvi": 0.55},
        },
        path="/api/v1/recommendations/for-field",
        method="POST",
    )
    resp = handle_recommendation_request(req)
    assert resp.status_code == 200, resp.body
    assert resp.body["delivered"] is True
    rec = resp.body["recommendation"]
    # المحرّك الحقيقيّ يُرجِع حالةً + درجة جودة (لا قيم مفبركة).
    assert "status" in rec
    assert "quality_grade" in rec
