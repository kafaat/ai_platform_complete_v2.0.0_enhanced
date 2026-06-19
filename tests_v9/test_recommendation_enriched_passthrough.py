"""اختبار وحدة: ApiResponse يحمل الكائن المُغنّى الكامل (enriched) لتخزين/تدقيق التوصية.

C1/C2: المسار يحتاج provenance + cross_reference الكاملين (الشرح) لا مجرّد العدّ في
جسم HTTP. هنا نتحقّق أنّ `handle_recommendation_request` يُرفِق `enriched` (EnrichedRecommendation
كـdict) دون تغيير جسم HTTP — اختبار نقيّ بلا قاعدة بيانات.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from core.api_adapter import ApiRequest, ApiResponse, handle_recommendation_request  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402


def _user() -> UserSchema:
    return UserSchema(
        user_id="u_test",
        tenant_id="t_test",
        role=UserRole.AGRONOMIST,
        name_ar="مهندس اختبار",
    )


def _payload(user: UserSchema) -> dict:
    return {
        "tenant_id": user.tenant_id,
        "farm_id": "",
        "field_id": "fld_1",
        "crop": "wheat",
        "validation": {},
    }


def test_apiresponse_has_enriched_field_default_none():
    r = ApiResponse(status_code=200, body={})
    assert hasattr(r, "enriched")
    assert r.enriched is None


def test_enriched_attached_on_recommendation_with_rec_id_and_explanation():
    user = _user()
    req = ApiRequest(
        user=user, payload=_payload(user), path="/api/v1/recommendations", method="POST"
    )
    resp = handle_recommendation_request(req)

    # أيّاً كان مصير الـpipeline (مُسلَّمة أو مرفوضة لنقص مدخلات)، ما دام جرى توليد
    # فعليّ (status != 429/401) يجب أن يُرفَق enriched ويحمل rec_id + مفاتيح الشرح.
    if resp.status_code in (401, 429):
        pytest.skip("مسار رفض مبكّر بلا توليد — لا enriched متوقَّع")
    assert resp.enriched is not None, "enriched يجب أن يُرفَق عند توليد توصية فعليّ"
    assert resp.enriched.get("rec_id"), "enriched يجب أن يحمل rec_id"
    # الشرح: provenance + cross_reference موجودان في الكائن المُغنّى.
    assert "provenance" in resp.enriched
    assert "cross_reference" in resp.enriched
    # جسم HTTP لم يتلوّث بالكائن المُغنّى الكامل (يبقى عقد الواجهة كما هو).
    assert "provenance" not in resp.body
