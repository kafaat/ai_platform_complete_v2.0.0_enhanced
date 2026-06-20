"""tests/test_adapt_from_evidence.py — توصيل نقطة التكيّف بالدليل المُدام.

نقطة `POST /api/v1/calibration/{region}/adapt-from-evidence` تُغلق حلقة التعلّم: التكيّف
محروس بدليل **مُدام** متراكم من القاعدة (لا حمولة طلب). هنا نؤكّد تسجيل المسار فقط؛
مسار القراءة يتطلّب Postgres ⇒ مُختبَر تكامليّاً لا هنا.
"""

import api.main
import pytest

pytestmark = pytest.mark.unit


def _routes() -> set[tuple[str, str]]:
    return {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}


def test_adapt_from_evidence_route_registered():
    """المسار مُسجَّل بطريقة POST (يمرّ حارس التفكيك ونمط التوصيل)."""
    assert (
        "/api/v1/calibration/{region}/adapt-from-evidence",
        "POST",
    ) in _routes()
