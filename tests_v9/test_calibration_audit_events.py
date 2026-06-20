"""سجلّ تدقيق المعايرة (v84) — تسجيل الحدث + إصداره في نقاط الكتابة الثلاث.

CALIBRATION_AUDIT_RECORDED مُسجَّل في EventType + event_catalog (فئة calibration)،
والدالّة المساعدة _append_calibration_audit مُستدعاة في النقاط الثلاث بأفعالها الصحيحة
بعد كتابة calibration_override (داخل المعاملة، best-effort). فحص تعاقُد على المصدر (بلا قاعدة).
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
CALIB = os.path.join(CORE, "api", "routers", "calibration.py")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


def _func_src(name: str) -> str:
    needle = f"async def {name}("
    with open(CALIB, encoding="utf-8") as f:
        src = f.read()
    start = src.find(needle)
    assert start != -1, f"لم يُعثر على المعالِج `{name}` في calibration.py"
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_audit_event_type_defined(core_on_path):
    from api.event_bus import EventType

    assert EventType["CALIBRATION_AUDIT_RECORDED"].value == "calibration.audit.recorded"


def test_audit_event_registered_in_catalog(core_on_path):
    import api.main  # noqa: F401 — تهيئة api.main
    from api.event_catalog import get_event, is_registered

    assert is_registered("CALIBRATION_AUDIT_RECORDED")
    ev = get_event("CALIBRATION_AUDIT_RECORDED")
    assert ev is not None and ev["category"] == "calibration"


def test_append_helper_emits_event(core_on_path):
    """الدالّة المساعدة تُصدِر CALIBRATION_AUDIT_RECORDED (تكامُل التدقيق↔مجرى الأحداث)."""
    body = _func_src("_append_calibration_audit")
    assert "INSERT INTO calibration_audit" in body
    assert "CALIBRATION_AUDIT_RECORDED" in body
    # best-effort داخل savepoint: معاملة فرعيّة + ابتلاع الاستثناء (لا يكسر الكتابة).
    assert "conn.transaction()" in body
    assert "pass" in body


@pytest.mark.parametrize(
    ("func", "action", "insert_or_delete"),
    [
        ("set_region_override", "override_set", "INSERT INTO calibration_override"),
        (
            "apply_region_adaptation_from_evidence",
            "adaptation_applied",
            "INSERT INTO calibration_override",
        ),
        ("delete_region_override", "reverted", "DELETE FROM calibration_override"),
    ],
)
def test_write_endpoint_appends_audit_after_write(core_on_path, func, action, insert_or_delete):
    """كلّ نقطة كتابة تستدعي تدقيق الفعل الصحيح بعد كتابة calibration_override (داخل المعاملة)."""
    body = _func_src(func)
    assert "_append_calibration_audit" in body, f"{func} لا يُدوّن تدقيقاً"
    assert f'"{action}"' in body, f"{func} لا يُدوّن الفعل {action}"
    # التدقيق بعد كتابة الـoverride (لا قبلها) — ضمن نفس المعاملة.
    assert body.index(insert_or_delete) < body.index("_append_calibration_audit"), (
        f"{func}: التدقيق ليس بعد الكتابة"
    )
