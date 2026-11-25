"""حذف حقلٍ أو دمجه أو انقسامه يمنعه سجلٌّ محميّ (ON DELETE RESTRICT) ⇒ 409 يسمّيه، لا 503.

**الفجوة** (Devin على #1598): روابط التحقّق الميدانيّ في v289 تشير إلى ``field_tasks`` بـ
``ON DELETE RESTRICT``، والحذف والدمج والانقسام تحذف من ``fields`` بالتتابع عبر المهامّ. فكان خطأ
المفتاح الأجنبيّ (23503) يسقط إلى فرع «تعذّر القاعدة» فيُجيب 503 والقاعدة سليمة.
**قرار المالك (2026-11-24):** يُرفض ذلك صراحةً بـ409 يسمّي سجلّ التحقّق، كما تُرفض دفعات الحصاد (v278).
**مراجعة المستشفى لـ#1608:** 23503 يصدر أيضاً عن إدراجٍ مفتاحه الأجنبيّ مفقود (الدمج والانقسام يُدرجان
الحقل الجديد أوّلاً)، فلا يُترجَم إلّا خطأ ``DELETE`` صفّ ``fields`` نفسه.

**ما يُثبِته:** دالّة التحويل على أخطاء asyncpg الحقيقيّة (لا اتّصال مُزيَّف)، وحارسٌ بنيويّ يُلزم أن
يكون ``DELETE FROM fields`` في ``delete_field_row`` وحده، وأن تمرّ عليه المسارات الثلاثة، وألّا يُترجَم
23503 في فرع الخطأ العامّ لأيّ مسار.
**حدُّه:** بلا Postgres — تتابع الحذف الحيّ وتراجع المعاملة لم يُقاسا هنا.
"""

from __future__ import annotations

import ast
import inspect

import asyncpg
import pytest
from api import field_context
from api.routers import fields as routes

pytestmark = pytest.mark.unit

_ACTIONS = ["حذف الحقل", "دمج الحقول", "انقسام الحقل"]


def _fk_violation(table: str) -> asyncpg.ForeignKeyViolationError:
    return asyncpg.ForeignKeyViolationError.new(
        {"C": "23503", "M": "update or delete violates foreign key constraint", "t": table}
    )


@pytest.mark.parametrize("action_ar", _ACTIONS)
def test_a_delete_refused_by_a_verification_record_is_a_409_naming_it(action_ar) -> None:
    conflict = field_context.protected_reference_conflict(
        _fk_violation("scouting_verification_links"), action_ar
    )
    assert conflict is not None and conflict.status_code == 409
    assert "scouting_verification" in conflict.detail and action_ar in conflict.detail


def test_a_delete_refused_by_any_other_protected_reference_is_a_409_naming_its_table() -> None:
    conflict = field_context.protected_reference_conflict(
        _fk_violation("field_task_evidence"), "حذف الحقل"
    )
    assert conflict is not None and conflict.status_code == 409
    assert "field_task_evidence" in conflict.detail


@pytest.mark.parametrize(
    "exc",
    [
        asyncpg.ConnectionDoesNotExistError("gone"),
        asyncpg.UniqueViolationError.new({"C": "23505", "M": "duplicate key"}),
        RuntimeError("bug"),
    ],
    ids=["connection", "unique", "bug"],
)
def test_anything_but_23503_stays_on_the_503_path(exc) -> None:
    assert field_context.protected_reference_conflict(exc, "حذف الحقل") is None


def _segments(module):
    source = inspect.getsource(module)
    return {
        node.name: ast.get_source_segment(source, node) or ""
        for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }


def test_the_only_field_row_delete_is_the_helper_and_only_it_maps_23503() -> None:
    helpers = _segments(field_context)
    holders = [name for name, code in helpers.items() if "DELETE FROM fields" in code]
    assert holders == ["delete_field_row"], holders
    assert "protected_reference_conflict(" in helpers["delete_field_row"]
    routes_source = inspect.getsource(routes)
    assert "DELETE FROM fields" not in routes_source, (
        "a field-row delete outside delete_field_row would answer 503 again for a verified field"
    )
    # The hospital's case: an insert-side 23503 inside merge/split reaches the generic except.
    # No route maps a database error to 409 there; only the DELETE helper does.
    assert "protected_reference_conflict" not in routes_source, (
        "an insert-side 23503 in merge/split must not be reported as a protected delete (409)"
    )


def test_every_route_that_deletes_fields_uses_the_helper() -> None:
    """الحذف والدمج والانقسام تحذف من ``fields`` بالمسار المتتالي نفسه (مراجعة المستشفى)."""
    using = {name for name, code in _segments(routes).items() if "delete_field_row(" in code}
    assert {"delete_field", "merge_fields", "split_field"} <= using, using
