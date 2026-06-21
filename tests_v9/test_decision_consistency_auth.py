"""فرض المصادقة على نقاط القرار/الاتّساق (governance #410).

الفجوة المسدودة: مجموعتا موجِّهات تُنتجان قرارات (decision/consistency) كانتا
مكشوفتين بلا مصادقة. هذه النقاط تُخرِج قراراً/توصية لا فهرساً عامّاً، فيجب أن
تتطلّب صلاحيّة العرض (RECOMMENDATION_VIEW). هنا نُثبِت أنّ الطلب **غير المُصادَق**
يُرفَض (401) عبر طبقة HTTP الحقيقيّة (TestClient).
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def app_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


# نقاط القرار/الاتّساق التي يجب أن تحرسها المصادقة (governance #410).
_GATED_ENDPOINTS = [
    "/api/v1/decision/for-location",
    "/api/v1/decision/explain",
    "/api/v1/consistency/irrigation",
    "/api/v1/consistency/freshness",
]


@pytest.mark.integration
@pytest.mark.parametrize("path", _GATED_ENDPOINTS)
def test_unauthenticated_rejected_on_decision_consistency(app_mod, path):
    """طلب بلا توكن على نقطة قرار/اتّساق ⇒ 401 (مرفوض قبل أيّ حساب)."""
    from fastapi.testclient import TestClient

    m = app_mod
    client = TestClient(m.app)
    r = client.get(path)
    assert r.status_code == 401, r.text
