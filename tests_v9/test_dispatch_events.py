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


def test_execution_write_point_still_emits_its_event():
    """DISPATCH_EXECUTION_RECORDED remains a platform-owned ledger write-point event."""
    src = _DISPATCH_SRC.read_text(encoding="utf-8")
    emitted = set(re.findall(r'_emit_domain_event\(\s*conn,\s*user,\s*"([A-Z_]+)"', src))
    assert "DISPATCH_EXECUTION_RECORDED" in emitted


def test_dispatch_decision_recording_is_delegated_to_decision_service():
    """P4.5: dispatch-decision persistence (and its audit event) moved to decision-service.

    The platform execute route must no longer emit DISPATCH_DECISION_RECORDED locally;
    it delegates the write through the decision-service facade instead.
    """
    src = _DISPATCH_SRC.read_text(encoding="utf-8")
    emitted = set(re.findall(r'_emit_domain_event\(\s*conn,\s*user,\s*"([A-Z_]+)"', src))
    assert "DISPATCH_DECISION_RECORDED" not in emitted
    assert "_record_dispatch_decision_via_service" in src
