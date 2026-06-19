"""حارس بادئة مواضيع NATS لوكيل الإشعارات — يمنع انحدار خطأ البادئة (C3 في تقرير الفجوات).

مواضيع NATS حسّاسة لحالة الأحرف؛ موضوع بحرف كبير (مثل `SAHOOL.alerts.weather`) يقع خارج
تيّار `sahool.>` فيُعطّل المستهلك الدائم بصمت. هذا الفحص ساكن (يقرأ المصدر) لتفادي
استيراد تبعيّات NATS الثقيلة.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_AGENT = Path(__file__).resolve().parent.parent / "agents" / "notification" / "agent.py"


def _subscription_subjects() -> list[str]:
    src = _AGENT.read_text(encoding="utf-8")
    block = re.search(r"SUBSCRIPTIONS\s*=\s*\[(.*?)\]", src, re.S)
    assert block, "تعذّر إيجاد قائمة SUBSCRIPTIONS في وكيل الإشعارات"
    # أوّل عنصر نصّيّ في كلّ صفّ tuple = الموضوع.
    return re.findall(r'\(\s*["\']([^"\']+)["\']', block.group(1))


def test_all_subscription_subjects_use_sahool_prefix():
    subjects = _subscription_subjects()
    assert subjects, "لا مواضيع اشتراك — تحقّق من التحليل"
    offenders = [s for s in subjects if not s.startswith("sahool.")]
    assert offenders == [], (
        f"مواضيع بلا بادئة `sahool.` (حسّاسة للحالة، تكسر الـstream): {offenders}"
    )


def test_no_uppercase_sahool_prefix_anywhere_in_agent():
    # يمنع تحديداً عودة `SAHOOL.` بأحرف كبيرة في أيّ موضوع.
    src = _AGENT.read_text(encoding="utf-8")
    assert "SAHOOL." not in src, "بادئة `SAHOOL.` كبيرة موجودة — يجب أن تكون `sahool.`"
