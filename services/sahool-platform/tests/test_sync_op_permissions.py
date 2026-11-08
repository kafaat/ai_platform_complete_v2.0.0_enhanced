"""T5 (تدقيق 2026-11-01): ``POST /api/v1/sync`` لا يمنح أكثر ممّا يمنحه المسار المباشر.

كان ``field.update`` يُطبَّق على ``fields`` لأيّ دور (VIEWER/WORKER) متجاوزاً ``FIELD_EDIT``
الذي يفرضه ``PATCH /api/v1/fields/{id}``. الآن تُفحَص صلاحية كلّ عمليّة قبل إدخالها
الطابور؛ المرفوضة تُعلَن ``forbidden`` في ``op_status`` ولا تُطبَّق ولا تُدوَّن.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import api.main as api_main  # noqa: E402  (يُحمَّل أوّلاً لكسر الاستيراد الدائريّ)
from api.offline_sync_contracts import _known_operation_kinds  # noqa: E402
from api.routers import sync as sync_router  # noqa: E402
from core.authorization import Permission, has_permission  # noqa: E402
from core.canonical_schemas import UserRole, UserSchema  # noqa: E402
from core.offline_first import OfflineQueue  # noqa: E402

_TENANT = "00000000-0000-0000-0000-0000000000a5"
_OP_FIELD = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a01"
_OP_OBS = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a02"


def _user(role: UserRole) -> UserSchema:
    return UserSchema(user_id="u-t5", tenant_id=_TENANT, role=role, name_ar="مختبِر")


@pytest.fixture
def queue(monkeypatch):
    """طابور معزول لكلّ اختبار، بلا قاعدة (المسار الذي تبقى فيه العمليّات QUEUED).

    دخولُ العمليّة الطابورَ هو شرطُ تطبيقها: كلّ ما في الطابور يُطبَّق في مزامنةٍ لاحقة
    لأيّ مستخدمٍ من المستأجر نفسه (``peek_pending`` لكلّ المستأجر). فالمرفوضة يجب ألّا تدخله.
    """
    q = OfflineQueue(max_per_tenant=100)
    monkeypatch.setattr(api_main, "_DB_POOL", None)
    monkeypatch.setattr(sync_router, "_OFFLINE_QUEUE", q)
    return q


def _queued_ids(q) -> set[str]:
    return {op.op_id for op in q.peek_pending(_TENANT, limit=100)}


def _batch():
    return api_main.SyncBatchRequest(
        operations=[
            {
                "op_id": _OP_FIELD,
                "kind": "field.update",
                "payload": {"field_id": "fld_1", "name": "مُعدَّل", "base_version": 1},
            },
            {"op_id": _OP_OBS, "kind": "observation_create", "payload": {"note": "x"}},
        ]
    )


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.WORKER])
async def test_field_update_without_field_edit_is_rejected_per_op_and_never_queued(queue, role):
    out = await sync_router.sync(_batch(), user=_user(role), since=None)

    assert _OP_FIELD not in _queued_ids(queue), "field.update دخل الطابور لدورٍ بلا FIELD_EDIT"
    assert out["op_status"][_OP_FIELD] == "forbidden"
    assert out["forbidden"] >= 1
    assert out["applied"] == 0
    assert _OP_FIELD in out["op_ids"]


async def test_viewer_cannot_record_ledger_ops_its_direct_route_forbids(queue):
    out = await sync_router.sync(_batch(), user=_user(UserRole.VIEWER), since=None)
    assert out["op_status"][_OP_OBS] == "forbidden"
    assert _queued_ids(queue) == set()
    assert out["forbidden"] == 2


async def test_worker_keeps_the_ops_its_role_may_perform(queue):
    """WORKER يملك OBSERVATION_RECORD ⇒ تبقى ملاحظته للمزامنة؛ وتُرفَض field.update وحدها."""
    out = await sync_router.sync(_batch(), user=_user(UserRole.WORKER), since=None)
    assert out["op_status"][_OP_OBS] == "queued"
    assert _queued_ids(queue) == {_OP_OBS}
    assert out["forbidden"] == 1


async def test_field_edit_holder_still_queues_field_update_for_apply(queue):
    out = await sync_router.sync(_batch(), user=_user(UserRole.MANAGER), since=None)
    assert _queued_ids(queue) == {_OP_FIELD, _OP_OBS}
    assert out["op_status"][_OP_FIELD] == "queued"
    assert out["forbidden"] == 0


def test_every_sync_kind_has_an_explicit_permission():
    """نوعٌ جديد في OperationKind بلا صلاحية مُعلَنة يُرفَض (fail-closed) — فيُعلَن هنا."""
    assert set(sync_router.SYNC_KIND_PERMISSIONS) == _known_operation_kinds()
    assert sync_router.SYNC_KIND_PERMISSIONS["field.update"] is Permission.FIELD_EDIT


def test_unknown_kind_is_denied_fail_closed():
    assert sync_router.sync_op_allowed(_user(UserRole.OWNER), "field.delete") is False


def test_sync_never_grants_what_the_role_lacks():
    for role in UserRole:
        user = _user(role)
        for kind, perm in sync_router.SYNC_KIND_PERMISSIONS.items():
            if perm is not None:
                assert sync_router.sync_op_allowed(user, kind) == has_permission(user, perm)
