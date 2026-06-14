"""إكمال تغطية الأحداث لنقاط الكتابة (CDES P0-2): مهامّ/مزارع/جداول ريّ.

سدّ فجوة من تدقيق CDES: نقاط كتابة كانت تُحدِّث القاعدة دون حدث، فلا يتفاعل
المستهلكون (وكيل الإشعارات يبثّ sahool.events.> للواجهة حيّاً). يثبّت: أنواع
الأحداث مُعرَّفة، وأنّ كلّ نقطة تُصدِر حدثها — فحص تعاقُد على المصدر (بلا قاعدة).
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


def test_writeop_event_types_defined(core_on_path):
    from api.event_bus import EventType

    assert EventType["TASK_UPDATED"].value == "task.updated"
    assert EventType["FARM_CREATED"].value == "farm.created"
    assert EventType["IRRIGATION_SCHEDULE_CREATED"].value == "irrigation.schedule.created"


def test_update_task_emits_task_updated():
    body = _func_src("update_task")
    assert "TASK_UPDATED" in body, "تحديث المهمّة لا يُصدِر TASK_UPDATED"
    # محروس بوجود الصفّ (لا إصدار لمهمّة غير موجودة/خارج المستأجِر)
    lines = body.splitlines()
    ev = next(i for i, ln in enumerate(lines) if "TASK_UPDATED" in ln)
    assert any(
        ln.strip() == "if row is not None:"
        and (len(ln) - len(ln.lstrip())) < (len(lines[ev]) - len(lines[ev].lstrip()))
        for ln in lines[:ev]
    ), "TASK_UPDATED ليس داخل حارس `if row is not None`"


def test_create_farm_emits_farm_created():
    body = _func_src("create_farm")
    assert "FARM_CREATED" in body, "إنشاء المزرعة لا يُصدِر FARM_CREATED"
    assert body.index("INSERT INTO farms") < body.index("FARM_CREATED")


def test_create_schedule_emits_schedule_created():
    body = _func_src("create_schedule")
    assert "IRRIGATION_SCHEDULE_CREATED" in body, "إنشاء جدول الريّ لا يُصدِر الحدث"
    assert body.index("INSERT INTO irrigation_schedules") < body.index(
        "IRRIGATION_SCHEDULE_CREATED"
    )
