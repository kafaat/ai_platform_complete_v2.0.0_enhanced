"""tests/test_yield_interval_service.py — اختبارات وحدة لِمُغلِّف نطاق الإنتاج النزيه.

منطق صِرف بلا خدمات/قاعدة. يتحقّق من: المعايرة (نطاق يحيط بالنقطة)، حالة «قيد
المعايرة» عند نقص البقايا أو غياب التقدير، اتّساع النطاق مع التغطية، وعدم الرمي.
"""

import pytest
from core.yield_interval_service import field_yield_interval

pytestmark = pytest.mark.unit

# عشر بقايا فأكثر = الحدّ الأدنى الذي يقبله المحرّك لِبناء نطاق موثوق.
_ENOUGH = [0.5, -0.4, 0.3, -0.2, 0.6, -0.5, 0.1, -0.3, 0.2, -0.1]
_TOO_FEW = [0.5, -0.4, 0.3]


class TestCalibrated:
    def test_enough_residuals_yields_interval_around_point(self):
        out = field_yield_interval(6.0, _ENOUGH, 0.90)
        assert out["calibrated"] is True
        assert out["interval"] is not None
        low, high = out["interval"]
        assert low <= high
        assert low <= out["point_estimate"] <= high
        assert out["coverage"] == 0.90
        assert out["n_residuals"] == len(_ENOUGH)
        assert out["unit"] == "t/ha"
        assert out["status_ar"] == "معايَر"

    def test_point_estimate_echoed(self):
        out = field_yield_interval(4.2, _ENOUGH, 0.90)
        assert out["point_estimate"] == 4.2


class TestPending:
    def test_too_few_residuals_is_pending(self):
        out = field_yield_interval(6.0, _TOO_FEW, 0.90)
        assert out["calibrated"] is False
        assert out["interval"] is None
        assert out["status_ar"] == "قيد المعايرة"
        assert out["coverage"] is None

    def test_none_point_estimate_is_honest_pending(self):
        out = field_yield_interval(None, _ENOUGH, 0.90)
        assert out["calibrated"] is False
        assert out["interval"] is None
        assert out["status_ar"] == "قيد المعايرة"

    def test_empty_residuals_never_raises(self):
        out = field_yield_interval(6.0, [], 0.90)
        assert out["calibrated"] is False
        assert out["interval"] is None
        assert out["status_ar"] == "قيد المعايرة"

    def test_none_residuals_never_raises(self):
        out = field_yield_interval(6.0, None, 0.90)
        assert out["calibrated"] is False
        assert out["interval"] is None


class TestCoverageMonotonicity:
    def test_wider_coverage_gives_wider_or_equal_interval(self):
        narrow = field_yield_interval(6.0, _ENOUGH, 0.80)
        wide = field_yield_interval(6.0, _ENOUGH, 0.95)
        assert narrow["calibrated"] is True
        assert wide["calibrated"] is True
        narrow_width = narrow["interval"][1] - narrow["interval"][0]
        wide_width = wide["interval"][1] - wide["interval"][0]
        assert wide_width >= narrow_width
