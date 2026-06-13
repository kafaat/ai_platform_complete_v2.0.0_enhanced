"""Stage C — توجيه التوصيات عبر الحالة القانونيّة الموحّدة (Canonical Field State).

يثبّت أنّ نقطة /api/v1/fields/{id}/recommendations تمرّر قرارها عبر field_state:
تستدعي recompute_field_state وتُرفِق field_state + requires_review بالاستجابة
(مصدر حقيقة واحد يحكم: تلقائيّ أم مراجعة بشريّة). فحص تعاقُد على المصدر + تسجيل
النقطة — متّسق مع نمط اختبارات المنصّة؛ سلوك حساب الحالة يغطّيه اختبار الإسقاط.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _field_recommendations_src() -> str:
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    start = src.index("async def field_recommendations(")
    # نهاية الجسم = أوّل تعريف مستوى-أعلى تالٍ بلا إزاحة: أيّ decorator (@…) أو
    # def/async def/class. (@\w أعمّ من @app. — يلتقط أيّ مزخرِف يُضاف لاحقاً.)
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_recommendations_route_through_canonical_state():
    body = _field_recommendations_src()
    # تمرّ عبر الحالة: تستدعي recompute_field_state وتُرفِق field_state + requires_review
    assert "recompute_field_state" in body, "التوصيات لا تستدعي recompute_field_state"
    assert '"field_state"' in body, "الاستجابة لا تُرفِق كتلة field_state"
    assert '"requires_review"' in body, "الاستجابة لا تُرفِق requires_review"
    # البوّابة الحاكمة: requires_review = نمط التنفيذ ليس auto
    assert 'execution_mode"] != "auto"' in body


def test_recommendations_endpoint_registered(core_on_path):
    import api.main as m

    paths = {getattr(r, "path", None) for r in m.app.routes}
    assert "/api/v1/fields/{field_id}/recommendations" in paths
