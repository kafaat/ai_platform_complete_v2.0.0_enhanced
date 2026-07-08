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


def test_dispatch_decision_recording_is_authoritative_then_mirrored():
    """INTERIM bridge: dispatch persistence is AUTHORITATIVE in the platform (temporary SoR)
    and best-effort mirrored to decision-service.

    The execute route writes ``dispatch_decisions`` and emits DISPATCH_DECISION_RECORDED via
    the outbox (authoritative), then best-effort mirrors through the decision-service facade.
    """
    src = _DISPATCH_SRC.read_text(encoding="utf-8")
    emitted = set(re.findall(r'_emit_domain_event\(\s*conn,\s*user,\s*"([A-Z_]+)"', src))
    assert "DISPATCH_DECISION_RECORDED" in emitted
    assert "INSERT INTO dispatch_decisions" in src
    assert "_mirror_dispatch_to_service" in src
