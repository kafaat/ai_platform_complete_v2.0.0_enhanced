"""التنبيهات تصبح تفاعليّة: create_alert/acknowledge_alert يُصدران أحداثاً.

سدّ فجوة كشفها تدقيق CDES: التنبيهات كانت تُكتب في القاعدة دون حدث، فلا يتفاعل
المستهلكون (وكيل الإشعارات يستهلك sahool.events.>) إلّا بمسح دوريّ. هنا نثبّت:
نوعا الحدث مُعرَّفان، وأنّ النقطتين تُصدرانهما (فحص تعاقُد على المصدر، بلا قاعدة).
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_alert_event_types_defined(core_on_path):
    from api.event_bus import EventType

    assert EventType["ALERT_CREATED"].value == "alert.created"
    assert EventType["ALERT_ACKNOWLEDGED"].value == "alert.acknowledged"


def test_create_alert_emits_alert_created():
    body = _func_src("create_alert")
    assert "ALERT_CREATED" in body, "إنشاء التنبيه لا يُصدِر ALERT_CREATED"
    # الإصدار قبل/مع منطق الحالة، داخل تهيئة المعاملة (يقع بعد INSERT).
    assert body.index("INSERT INTO alerts") < body.index("ALERT_CREATED")


def test_acknowledge_alert_emits_acknowledged():
    body = _func_src("acknowledge_alert")
    assert "ALERT_ACKNOWLEDGED" in body, "إقرار التنبيه لا يُصدِر ALERT_ACKNOWLEDGED"
    # الإصدار محروس بوجود الصفّ (لا إصدار لتنبيه غير موجود/خارج المستأجِر).
    lines = body.splitlines()
    ev_idx = next(i for i, ln in enumerate(lines) if "ALERT_ACKNOWLEDGED" in ln)
    guarded = any(
        ln.strip() == "if row is not None:"
        and (len(ln) - len(ln.lstrip())) < (len(lines[ev_idx]) - len(lines[ev_idx].lstrip()))
        for ln in lines[:ev_idx]
    )
    assert guarded, "ALERT_ACKNOWLEDGED ليس داخل حارس `if row is not None`"
