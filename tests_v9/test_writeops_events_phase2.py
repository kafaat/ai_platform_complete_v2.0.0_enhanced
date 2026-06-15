"""تغطية أحداث نقاط الكتابة — المرحلة 2 (مخزون/معدّات/مرجعيّة/دورة زراعيّة).

استكمال CDES P0-2: ستّ نقاط كتابة إضافيّة تُصدِر أحداثاً (نفس نمط المرحلة 1)
فتصبح تفاعليّة عبر وكيل الإشعارات. فحص تعاقُد على المصدر (بلا قاعدة).
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
ROUTERS = os.path.join(CORE, "api", "routers")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    # المعالِجات قد تكون في main.py أو في وحدات routers بعد تفكيك monolith (P0).
    # نبحث في main.py أوّلاً ثمّ في كلّ ملفّات routers — فحص التعاقُد يبقى صحيحاً
    # أينما استقرّ المعالِج.
    sources = [MAIN]
    if os.path.isdir(ROUTERS):
        sources += [
            os.path.join(ROUTERS, f) for f in sorted(os.listdir(ROUTERS)) if f.endswith(".py")
        ]
    needle = f"async def {name}("
    for path in sources:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        start = src.find(needle)
        if start == -1:
            continue
        nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
        end = (start + 1 + nxt.start()) if nxt else len(src)
        return src[start:end]
    raise AssertionError(f"لم يُعثر على المعالِج `{name}` في main.py ولا في routers/")


_EXPECTED = {
    "INVENTORY_ITEM_CREATED": "inventory.item.created",
    "INVENTORY_BATCH_ADDED": "inventory.batch.added",
    "EQUIPMENT_CREATED": "equipment.created",
    "MAINTENANCE_LOGGED": "equipment.maintenance.logged",
    "MASTER_DATA_CREATED": "master_data.created",
    "CROP_ROTATION_ADDED": "crop_rotation.added",
}


def test_phase2_event_types_defined(core_on_path):
    from api.event_bus import EventType

    for name, value in _EXPECTED.items():
        assert EventType[name].value == value, f"{name} غير مُعرَّف/قيمته خاطئة"


@pytest.mark.parametrize(
    ("func", "event", "insert"),
    [
        ("create_inventory_item", "INVENTORY_ITEM_CREATED", "INSERT INTO inventory_items"),
        ("add_inventory_batch", "INVENTORY_BATCH_ADDED", "INSERT INTO inventory_batches"),
        ("create_equipment", "EQUIPMENT_CREATED", "INSERT INTO equipment"),
        ("log_maintenance", "MAINTENANCE_LOGGED", "INSERT INTO equipment_maintenance"),
        ("create_master_data", "MASTER_DATA_CREATED", "INSERT INTO master_data"),
        ("add_crop_rotation", "CROP_ROTATION_ADDED", "INSERT INTO crop_rotations"),
    ],
)
def test_endpoint_emits_after_insert(func, event, insert):
    body = _func_src(func)
    assert event in body, f"{func} لا يُصدِر {event}"
    # الإصدار بعد الإدراج (داخل المعاملة) — لا قبله
    assert body.index(insert) < body.index(event), f"{func}: الإصدار ليس بعد الإدراج"
