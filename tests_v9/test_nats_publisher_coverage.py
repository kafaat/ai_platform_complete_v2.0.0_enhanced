"""حارس تغطية ناشري NATS (H2): كلّ موضوع مُستهلَك له منتِج موثَّق أو waiver.

يفرض عقد ``event_publish_contracts.yaml``: أيّ موضوع NATS يُستهلَك في الكود
(``agents/notification/agent.py: SUBSCRIPTIONS`` + أيّ ``.subscribe("literal")``)
يجب أن يظهر في العقد بمنتِجٍ (producer) أو ``reserved_future_subject`` (waiver) —
وإلّا يفشل («مُستهلَك بلا منتِج»). يمنع مناطق أحداث ميّتة دون توثيق، ويُبقي القرار
المعماريّ (ناشرون عبر outbox لا تقليم اشتراكات) مرئيّاً ومُتحقَّقاً في CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tools"))

import sahool_inspector as si  # noqa: E402


def test_contracts_file_exists():
    assert (_ROOT / "event_publish_contracts.yaml").exists(), "عقد نشر الأحداث مفقود"


def test_every_consumed_subject_has_producer_or_waiver():
    """الحارس العكسيّ يمرّ: لا موضوع مُستهلَك بلا منتِج/waiver."""
    result = si.check_nats_publisher_coverage()
    assert result.status == si.PASS, "موضوعات مُستهلَكة بلا منتِج/waiver:\n" + "\n".join(
        result.findings
    )


def test_notification_subscriptions_are_all_documented():
    """كلّ موضوع في SUBSCRIPTIONS موثَّق في العقد (لا انجراف كود↔عقد)."""
    import yaml

    consumed = set(si._consumed_subjects())
    doc = yaml.safe_load((_ROOT / "event_publish_contracts.yaml").read_text(encoding="utf-8"))
    documented = {e["subject"] for e in doc.get("subjects", []) if e.get("subject")}
    missing = sorted(consumed - documented)
    assert not missing, f"موضوعات مُستهلَكة غير موثَّقة في العقد: {missing}"


def test_guard_is_registered_in_checks():
    """الحارس مُسجَّل في CHECKS فيُشغَّل ضمن المفتّش (بوّابة CI)."""
    assert si.check_nats_publisher_coverage in si.CHECKS


def test_guard_catches_undocumented_consumed_subject(monkeypatch):
    """سلبيّ: موضوع مُستهلَك غير موثَّق ⇒ الحارس يفشل (يثبت أنّه يحرس فعلاً)."""
    orig = si._consumed_subjects
    monkeypatch.setattr(
        si,
        "_consumed_subjects",
        lambda: {**orig(), "sahool.bogus.undocumented": "test:0"},
    )
    result = si.check_nats_publisher_coverage()
    assert result.status == si.FAIL
    assert any("sahool.bogus.undocumented" in f for f in result.findings)


# ── الموضوع اليتيم (متابعة C): منشور بلا مشترِك، موثَّق كـwaiver ──
_ORPHAN = "sahool.weather.field.overlay.completed"


def test_orphan_published_subject_is_waived_in_contract():
    """`overlay.completed` المنشور (weather-polygon-worker) موثَّق في published_no_consumer."""
    waived = si._published_no_consumer_waivers()
    assert _ORPHAN in waived, f"`{_ORPHAN}` يجب أن يكون موثَّقاً في published_no_consumer بعقد الأحداث"


def test_nats_subjects_passes_with_orphan_waived():
    """فحص NATS subjects يمرّ (PASS): الموضوع اليتيم الموثَّق لا يُنتِج WARN."""
    result = si.check_nats_subjects()
    assert result.status == si.PASS, "فحص NATS subjects ليس PASS:\n" + "\n".join(result.findings)
    assert not any(_ORPHAN in f for f in result.findings), (
        f"`{_ORPHAN}` ما زال يُنتِج إنذاراً رغم التوثيق"
    )


def test_subjects_check_warns_when_waiver_removed(monkeypatch):
    """سلبيّ: لولا الـwaiver لأصدر الموضوع اليتيم WARN (يثبت أنّ الـwaiver هو ما يُسكِته)."""
    monkeypatch.setattr(si, "_published_no_consumer_waivers", set)
    result = si.check_nats_subjects()
    assert result.status == si.WARN
    assert any(_ORPHAN in f and "منشور بلا مشترِك" in f for f in result.findings)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
