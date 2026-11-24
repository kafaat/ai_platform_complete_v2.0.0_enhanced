"""حذف حقلٍ أو دمجه أو انقسامه يمنعه سجلٌّ محميّ (ON DELETE RESTRICT) ⇒ 409 يسمّيه، لا 503.

**الفجوة** (Devin على #1598): روابط التحقّق الميدانيّ في v289 تشير إلى ``field_tasks`` بـ
``ON DELETE RESTRICT``، والحذف والدمج والانقسام تحذف من ``fields`` بالتتابع عبر المهامّ. فكان خطأ
المفتاح الأجنبيّ (23503) يسقط إلى فرع «تعذّر القاعدة» فيُجيب 503 والقاعدة سليمة.
**قرار المالك (2026-11-24):** يُرفض ذلك صراحةً بـ409 يسمّي سجلّ التحقّق، كما تُرفض دفعات الحصاد (v278).

**ما يُثبِته:** دالّة التحويل على أخطاء asyncpg الحقيقيّة (لا اتّصال مُزيَّف)، وحارسٌ بنيويّ يُلزم كلّ
مسارٍ في الموجِّه ينفّذ ``DELETE FROM fields`` بأن يمرّر خطأ القاعدة عليها قبل 503.
**حدُّه:** بلا Postgres — تتابع الحذف الحيّ وتراجع المعاملة لم يُقاسا هنا.
"""

from __future__ import annotations

import ast
import inspect

import asyncpg
import pytest
from api.routers import fields as mod

pytestmark = pytest.mark.unit

_ACTIONS = ["حذف الحقل", "دمج الحقول", "انقسام الحقل"]


def _fk_violation(table: str) -> asyncpg.ForeignKeyViolationError:
    return asyncpg.ForeignKeyViolationError.new(
        {"C": "23503", "M": "update or delete violates foreign key constraint", "t": table}
    )


@pytest.mark.parametrize("action_ar", _ACTIONS)
def test_a_verification_record_is_a_409_naming_the_record_and_the_action(action_ar) -> None:
    conflict = mod._protected_reference_conflict(
        _fk_violation("scouting_verification_links"), action_ar
    )
    assert conflict is not None and conflict.status_code == 409
    assert "scouting_verification" in conflict.detail and action_ar in conflict.detail


def test_any_other_protected_reference_is_a_409_naming_its_table() -> None:
    conflict = mod._protected_reference_conflict(_fk_violation("field_task_evidence"), "حذف الحقل")
    assert conflict is not None and conflict.status_code == 409
    assert "field_task_evidence" in conflict.detail


@pytest.mark.parametrize(
    "exc",
    [
        asyncpg.ConnectionDoesNotExistError("gone"),
        asyncpg.UniqueViolationError.new({"C": "23505", "M": "duplicate key"}),
        RuntimeError("bug"),
    ],
)
def test_anything_else_stays_with_the_503_path(exc) -> None:
    assert mod._protected_reference_conflict(exc, "حذف الحقل") is None


def test_every_route_that_deletes_fields_maps_a_protected_reference_to_409() -> None:
    """الحذف والدمج والانقسام تحذف من ``fields`` بالمسار المتتالي نفسه (مراجعة المستشفى).

    كلّ دالّة مسار في الموجِّه تنفّذ ``DELETE FROM fields`` يجب أن تمرّر خطأ القاعدة على
    ``_protected_reference_conflict`` قبل 503 — وإلّا عاد السجلّ المحميّ «تعذّر القاعدة».
    """
    module_source = inspect.getsource(mod)
    deleting = []
    # Route handlers only (module level); their nested ``_work`` helpers are covered by them.
    for node in ast.parse(module_source).body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        source = ast.get_source_segment(module_source, node) or ""
        if "DELETE FROM fields" in source:
            deleting.append(node.name)
            assert "_protected_reference_conflict(" in source, node.name
    assert {"delete_field", "merge_fields", "split_field"} <= set(deleting), deleting
