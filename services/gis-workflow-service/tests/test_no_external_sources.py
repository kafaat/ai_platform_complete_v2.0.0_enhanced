"""حارس ساكن — الشريحة B لا تستورد ولا تستدعي أيّ مصدر خارجيّ (GEE/earthaccess/…).

يمسح كلّ ملفّات الخدمة نصّيّاً: لا استيراد/استدعاء لـearthengine/earthaccess/wapor/
worldcereal/HLS. يضمن أنّ B تعمل فقط على مخرجات ساهول (وعد النطاق الصريح).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.unit

SERVICE = Path(__file__).resolve().parents[1]
_FORBIDDEN = ("earthengine", "earthaccess", "wapor", "worldcereal", "ee.Initialize", "hls_fetch")


def test_no_external_source_imports_in_service_code():
    offenders: list[str] = []
    for py in SERVICE.glob("*.py"):
        low = py.read_text(encoding="utf-8").lower()
        for tok in _FORBIDDEN:
            # يُسمَح بذكر الاسم في نصّ الحظر/التعليق، لكن لا كاستيراد/استدعاء فعليّ.
            if f"import {tok}" in low or f"{tok}(" in low.replace(" ", ""):
                offenders.append(f"{py.name}: {tok}")
    assert not offenders, f"external source usage forbidden in slice B: {offenders}"
