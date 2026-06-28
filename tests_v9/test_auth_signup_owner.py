"""عقد التسجيل الذاتيّ: المُسجِّل = مالك مستأجِره الجديد (TENANT_OWNER).

الفجوة المُغلَقة (Bootstrap Deadlock): التسجيل الذاتيّ يُنشئ مستأجِراً معزولاً جديداً
(users.tenant_id افتراضه gen_random_uuid)، لكنّ الدور كان 'farmer' (→WORKER) فلا
يملك FIELD_CREATE ⇒ يملك مستأجِراً لا يقدر على تأسيسه. الآن يُسنَد 'owner'.

أمان: لا تصعيد عابر — RLS يعزل المستأجرين، والمُسجِّل مالك مستأجِره وحده، وRegisterRequest
بلا حقل role (العميل لا يختار دوره). اختبار تعاقُد مصدريّ (بلا قاعدة) يعمل في CI.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")
AUTH = os.path.join(ROOT, "services/auth/main.py")

# بعد تفكيك مسارات auth: مُعالِج register انتقل إلى routers/registration.py، بينما
# RegisterRequest وValidRole يبقيان في main.py (نماذج/ثوابت مشتركة). نمسح المصدر
# المُسلسَل (main.py + routers/*.py) كي يغطّي الحارس الحالتين بلا إضعاف أيّ تأكيد أمنيّ.
from auth_route_source import auth_combined_source  # noqa: E402


def _src() -> str:
    return auth_combined_source(ROOT)


def test_register_assigns_owner_to_tenant_founder():
    src = _src()
    reg = src[src.index("async def register") : src.index("async def register") + 900]
    assert "'owner'" in reg, "register يجب أن يُسنِد 'owner' لمؤسِّس المستأجِر الجديد"
    assert "'farmer'" not in reg, "register لا يجب أن يُثبّت 'farmer' (Bootstrap Deadlock)"


def test_register_request_has_no_client_role_field():
    """منع تصعيد الصلاحيات: العميل لا يُرسل دوره (لا حقل role في RegisterRequest)."""
    src = _src()
    rr = src[src.index("class RegisterRequest") : src.index("class RegisterRequest") + 250]
    assert "role:" not in rr, "RegisterRequest لا يجب أن يقبل role من العميل"


def test_owner_is_a_recognized_auth_role():
    """owner ضمن أدوار auth الصالحة (ValidRole) كي يُعرَّف عبر النظام."""
    src = _src()
    vr = src[src.index("ValidRole = Literal") : src.index("ValidRole = Literal") + 120]
    assert '"owner"' in vr, "owner يجب أن يكون ضمن ValidRole"
