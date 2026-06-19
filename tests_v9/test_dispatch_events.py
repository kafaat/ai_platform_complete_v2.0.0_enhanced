"""اختبار أحداث توزيع القرار (H3): تدقيق نقاط كتابة decision_dispatch.

يثبت: (أ) نوعا الحدث موجودان في EventType بقيمتهما المنقّطة؛ (ب) مُسجَّلان في الكتالوج؛
(ج) سلوكيّاً: نقطتا الكتابة (execute/record) تُصدِران الحدثين فعلاً (مسح المصدر).
نواة بلا خدمات.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parent.parent / "services" / "sahool-platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from api import event_catalog  # noqa: E402
from api.event_bus import EventType  # noqa: E402

_DISPATCH_SRC = _PLATFORM / "api" / "routers" / "decision_dispatch.py"


def test_dispatch_event_members_exist():
    assert EventType["DISPATCH_DECISION_RECORDED"].value == "dispatch.decision.recorded"
    assert EventType["DISPATCH_EXECUTION_RECORDED"].value == "dispatch.execution.recorded"


def test_dispatch_events_registered_in_catalog():
    assert event_catalog.is_registered("DISPATCH_DECISION_RECORDED")
    assert event_catalog.is_registered("DISPATCH_EXECUTION_RECORDED")


def test_write_points_emit_both_events():
    src = _DISPATCH_SRC.read_text(encoding="utf-8")
    # كلّ اسم مُمرَّر لـ_emit_domain_event يجب أن يكون اسم نقطة كتابة فعليّة موصولة.
    emitted = set(re.findall(r'_emit_domain_event\(\s*conn,\s*user,\s*"([A-Z_]+)"', src))
    assert "DISPATCH_DECISION_RECORDED" in emitted
    assert "DISPATCH_EXECUTION_RECORDED" in emitted
