"""اختبار Conflict Resolution Workflow (Level 2): حساب الحقول المتغيّرة في 409.

عند تعارض التزامن التفاؤليّ (row_version) يُرجِع update_field سجلّ الخادم + الحقول
المتغيّرة ليحسم العميل (الخادم/نسختي/دمج). هنا نختبر منطق المقارنة النقيّ
(_conflict_changed_fields) — بلا قاعدة/شبكة.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")


@pytest.fixture(scope="module")
def fields_mod():
    pytest.importorskip("fastapi")
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    import api.main  # noqa: F401 — يُهيّئ الوحدة الأمّ أوّلاً فيُحلّ الاستيراد الدائريّ
    import api.routers.fields as m

    yield m
    if added and CORE in sys.path:
        sys.path.remove(CORE)


def test_detects_only_conflicting_fields(fields_mod):
    cf = fields_mod._conflict_changed_fields
    client = {"crop_type": "قمح", "soil_type": "طينية"}
    server = {"crop_type": "ذرة", "soil_type": "طينية", "row_version": 6}
    # crop_type تغيّر (قمح≠ذرة)، soil_type متطابق ⇒ لا يُحسَب.
    assert cf(client, server) == ["crop_type"]


def test_no_conflict_when_all_match(fields_mod):
    cf = fields_mod._conflict_changed_fields
    assert cf({"a": 1, "b": 2}, {"a": 1, "b": 2, "row_version": 3}) == []


def test_ignores_keys_absent_from_server(fields_mod):
    cf = fields_mod._conflict_changed_fields
    # مفتاح لا يوجد في سجلّ الخادم ⇒ لا يُحسَب (تجنّب الإفراط في التعليم).
    assert cf({"ghost": "x"}, {"row_version": 1}) == []


def test_empty_client_changes(fields_mod):
    cf = fields_mod._conflict_changed_fields
    assert cf({}, {"crop_type": "ذرة"}) == []
