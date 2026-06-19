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


# ── Auto-merge (Level 3): خطّة الدمج 3-way ──


def test_merge_non_overlapping_auto(fields_mod):
    # العميل غيّر soil_type، والطرف الآخر غيّر crop_type ⇒ دمج آليّ بلا تعارض.
    plan = fields_mod._field_merge_plan
    client = {"soil_type": "طينية"}
    server = {"soil_type": "رملية", "crop_type": "ذرة"}
    base = {"soil_type": "رملية"}  # الخادم لم يمسّ soil_type (server == base)
    can_merge, conflicts = plan(client, server, base)
    assert can_merge is True
    assert conflicts == []


def test_merge_overlapping_conflict(fields_mod):
    # الطرفان غيّرا crop_type ⇒ تعارض حقيقيّ، لا دمج.
    plan = fields_mod._field_merge_plan
    client = {"crop_type": "قمح"}
    server = {"crop_type": "ذرة"}
    base = {"crop_type": "بطاطس"}  # server(ذرة) != base(بطاطس) ⇒ الطرف الآخر غيّره
    can_merge, conflicts = plan(client, server, base)
    assert can_merge is False
    assert conflicts == ["crop_type"]


def test_no_base_values_cannot_merge(fields_mod):
    # بلا base_values لا يمكن تحديد الأمان ⇒ fail-closed (تعارض، لا دمج).
    plan = fields_mod._field_merge_plan
    can_merge, conflicts = plan({"soil_type": "X"}, {"soil_type": "old"}, None)
    assert can_merge is False
    assert conflicts == ["soil_type"]


def test_noop_when_server_matches_intent(fields_mod):
    # الخادم يطابق نيّة العميل أصلاً ⇒ لا-عمل، دمج آمن (لا تعارض).
    plan = fields_mod._field_merge_plan
    can_merge, conflicts = plan({"crop_type": "ذرة"}, {"crop_type": "ذرة"}, {"crop_type": "قمح"})
    assert can_merge is True
    assert conflicts == []
