"""عقدُ `/v1/evaluate` عبر HTTP على **التطبيق الحقيقيّ** لا على مِرقاةٍ اصطناعيّة.

مراجعةُ #1013: اختباراتُ B6 كلُّها تمرّ عبر مِرقاة تُحاكي محرّك الطبقات، فانحدارُ توصيلٍ
في المسار أو التبعيّة — سقوطُ التسجيل، أو ارتدادٌ إلى الفرع الكاتب، أو عقدُ استجابةٍ
مغلوط — **يمرّ والاختباراتُ خضراء**. وهو الصنفُ نفسه الذي قبلتُه على #1010: نصُّ
المصدر ليس سلوكَ التشغيل.

هنا يُستورَد `services/guardrails-engine/main.py` نفسُه ويُستدعى المسارُ بعميل HTTP:
مصرَّحٌ له وغيرُ مصرَّح، مع تأكيدِ أنّ التقييم **لا يُنشئ سيرَ موافقة**.

الحدّ المُعلَن: هذا عقدُ المسار والتبعيّة والاستجابة. ليس تصديقاً لقواعد الطبقات
الكيميائيّة والاقتصاديّة نفسها، ولا تشغيلاً على الخدمة المنشورة.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests_v9 import service_module

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/guardrails-engine"
TOKEN = "evaluate-contract-token"
pytestmark = pytest.mark.unit


@pytest.fixture
def guardrails(monkeypatch):
    """يُحمّل الخدمة الحقيقيّة بتوكنٍ معلوم عبر المُحمِّل المشترك.

    `main.py` اسمٌ عامٌّ عبر أربعٍ وعشرين خدمة و`sys.modules` مفتاحُه الاسم لا المسار،
    فاستيرادُه عارياً في العمليّة المشتركة يُعيد وحدةَ خدمةٍ أخرى بصمت — **نجاحٌ كاذب**
    لا فشل. لذلك `load_service_main` الذي يُسقط المُخبّأ ويُثبِت الهويّة بالمسار،
    ويحرسه `test_no_test_in_the_shared_process_imports_a_bare_main_unguarded`.

    والتوكنُ يُقرأ عند الاستيراد (`_GR_AGENT_TOKEN`) فيُضبط قبله، ويُسقَط بعده كي لا
    تبقى الوحدةُ المُخبّأة حاملةً توكنَ الاختبار لمن يُحمّلها بعدنا.
    """
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", TOKEN)
    service_module.purge_generic_modules()
    module = service_module.load_service_main(
        str(SERVICE), required_attrs=("app", "_require_service_token", "GuardrailsRequest")
    )
    if str(ROOT) not in sys.path:
        monkeypatch.syspath_prepend(str(ROOT))
    yield module
    service_module.purge_generic_modules()


def _irrigation_request() -> dict:
    """طلبٌ يستوفي عقدَ الأدلّة لمسار الريّ — وإلّا رُفِض قبل بلوغ الطبقات."""
    return {
        "action_type": "irrigation",
        # الريّ في `ECONOMIC_ACTIONS` و`SPENDING_ACTIONS` معاً، فعقدُ الأدلّة يشترط
        # الكلفةَ والعائدَ المتوقَّع مع سياقٍ ماليّ كامل. و`water_source` مُقيَّدة
        # بقيمٍ معدودة — «well» ليست منها. النقصُ يُردّ 422 قبل بلوغ الطبقات.
        "action_data": {
            "water_m3": 120.0,
            "cost_usd": 40.0,
            "projected_revenue_increase_usd": 260.0,
        },
        "farm_context": {
            "field_area_ha": 4.0,
            "season_water_used_m3_ha": 900.0,
            "water_source": "groundwater",
            "annual_revenue_usd": 50000.0,
            "annual_costs_usd": 32000.0,
            "cash_reserve_usd": 9000.0,
        },
        "user_id": 7,
        "tenant_id": str(uuid4()),
        "request_source": "agent",
    }


def test_the_route_and_its_dependency_are_actually_wired(guardrails):
    paths = {route.path for route in guardrails.app.routes}
    assert "/v1/evaluate" in paths, "المسارُ غيرُ مُسجَّل ⇒ ٤٠٤ على المُستدعي رغم خضرة الوحدات"
    assert "/v1/validate" in paths, "المسارُ القديم يبقى بسلوكه الافتراضيّ"


def test_evaluation_is_read_only_and_creates_no_approval_workflow(guardrails):
    client = TestClient(guardrails.app)
    response = client.post(
        "/v1/evaluate", json=_irrigation_request(), headers={"X-Agent-Token": TOKEN}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluation_only"] is True
    assert body["allowed"] is False, "تقييمٌ ناجح ليس إذناً بالتنفيذ"
    assert body["requires_human_approval"] is True
    assert body.get("approval_workflow_id") is None, "التقييمُ أنشأ سيرَ موافقة — كتابةٌ محظورة"
    assert body.get("notification_delivery") is None


@pytest.mark.parametrize("headers", [{}, {"X-Agent-Token": "wrong-token"}])
def test_evaluation_refuses_an_unauthorized_caller(guardrails, headers):
    client = TestClient(guardrails.app)
    response = client.post("/v1/evaluate", json=_irrigation_request(), headers=headers)
    assert response.status_code == 401
    detail = response.json().get("detail", "")
    # مراجعة #1013: الرسالةُ كانت تسمّي `/v1/validate` دائماً، فمن يصطدم بها على
    # التقييم يطارد مساراً لم يستدعه. لا تُسمّى مساراً بعينه.
    assert "/v1/validate" not in detail, "رسالةُ الرفض تسمّي مساراً آخر ⇒ تشخيصٌ مُضلِّل"


def test_a_low_risk_evaluation_is_still_not_an_authorization(guardrails):
    """حتّى مخاطرةٌ منخفضة تبقى `review_required`: التقييمُ لا يصير قراراً."""
    client = TestClient(guardrails.app)
    payload = _irrigation_request()
    payload["auto_approve_low_risk"] = True  # يُبطِلها المسار عمداً
    response = client.post("/v1/evaluate", json=payload, headers={"X-Agent-Token": TOKEN})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["allowed"] is False
    assert body["evaluation_only"] is True
    assert body.get("approval_workflow_id") is None


def test_the_legacy_route_keeps_its_default_behaviour(guardrails):
    """الترقيةُ المتدرّجة: `/v1/validate` لا يُصبح تقييماً فقط بالخطأ."""
    client = TestClient(guardrails.app)
    response = client.post(
        "/v1/validate", json=_irrigation_request(), headers={"X-Agent-Token": TOKEN}
    )
    assert response.status_code == 200, response.text
    assert response.json().get("evaluation_only") is not True
