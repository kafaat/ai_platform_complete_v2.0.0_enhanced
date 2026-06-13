"""Stage F (تغذية آمنة) — التوصيات تستمدّ مرجعيّة من الحالة القانونيّة الموحّدة.

يثبّت أنّ المُجمِّع يضيف تنبيه ملوحة حرجة عالي الأولويّة حين تحكُم النواة الزراعيّة
بـsalinity_class=critical (تصعيد مرجعيّ)، ولا يضيف شيئاً خلاف ذلك، ودون تغيير عدد/
محتوى التوصيات الأخرى (يحترم قيد عدم تغيير الأرقام الفلاحيّة).
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def hub():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    from api import recommendations_hub as h

    return h


def _ctx(hub, **kw):
    return hub.RecommendationContext(
        field_id="f1", crop="wheat", stage="mid", today=date(2026, 6, 13), **kw
    )


def test_critical_salinity_adds_high_priority_caution(hub):
    recs = hub.build_recommendations(_ctx(hub, salinity_class="critical", crop_vigor=0.7))
    sal = [r for r in recs if "ملوحة" in r.title_ar]
    assert len(sal) == 1
    assert sal[0].priority == "high"
    assert "canonical_field_state" in sal[0].source  # مرجعها الحالة الموحّدة


def test_no_caution_when_not_critical(hub):
    for sc in ("low", "moderate", None):
        recs = hub.build_recommendations(_ctx(hub, salinity_class=sc))
        assert not any("ملوحة" in r.title_ar for r in recs), f"تنبيه غير متوقّع عند {sc}"


def test_other_recommendations_unchanged_by_salinity(hub):
    """التصعيد يُضيف فقط — لا يغيّر عدد/محتوى التوصيات الأخرى (قيد الأرقام)."""
    base = hub.build_recommendations(_ctx(hub, salinity_class="low"))
    crit = hub.build_recommendations(_ctx(hub, salinity_class="critical"))
    base_other = [r.to_dict() for r in base if "ملوحة" not in r.title_ar]
    crit_other = [r.to_dict() for r in crit if "ملوحة" not in r.title_ar]
    assert base_other == crit_other  # نفس التوصيات الأخرى تماماً
    assert len(crit) == len(base) + 1  # أُضيف تنبيه واحد فقط
