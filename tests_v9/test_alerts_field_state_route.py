"""Stage C2 — التنبيهات تمرّ عبر الحالة القانونيّة الموحّدة (Canonical Field State).

يثبّت أنّ POST /api/v1/alerts (إنشاء تنبيه على حقل) يمرّ عبر field_state: يستدعي
recompute_field_state ويُصدِر FIELD_STATE_CHANGED إن تبدّلت الصلاحيّة (نفس نمط
إنشاء الموسم). فحص تعاقُد على المصدر — متّسق مع نمط اختبارات المنصّة.
"""

from __future__ import annotations

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
MAIN = os.path.join(ROOT, "services/sahool-platform", "api", "main.py")


def _func_src(name: str) -> str:
    with open(MAIN, encoding="utf-8") as f:
        src = f.read()
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_create_alert_routes_through_canonical_state():
    body = _func_src("create_alert")
    assert "recompute_field_state" in body, "إنشاء التنبيه لا يستدعي recompute_field_state"
    assert "FIELD_STATE_CHANGED" in body, "لا يُصدِر حدث تبدّل الحالة"
    assert "alert.created" in body, "لا يوسم المُحفِّز بـalert.created"
    # يُعاد الحساب فقط حين يكون التنبيه مرتبطاً بحقل
    assert "req.field_id is not None" in body
