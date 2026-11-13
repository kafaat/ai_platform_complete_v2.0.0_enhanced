"""An inspection approval covers one evidence version (v256); a worker links a task receipt.

Priority 3: the supervisor approved photo 1, then the task update path changed the photo while
the close gate only checked that the last hand-off action was "approve". The gate now also
requires the approved version to be the task's latest evidence, unchanged.

Priority 7 (task part): linking an expense to a task needs the expense-write permission
(activity:execute), not analytics:view, and the cost trace stays behind analytics:view.

The behaviour that depends on the tables (the version gate, the appended versions, the stored
link) runs on a migrated Postgres in tests_v9/test_inspection_evidence_version_live_pg.py.
What stays here needs no database: the digest, the request model, and the permission refusals,
which the route dependency answers before any connection is opened.
"""

import hashlib
import json
from uuid import UUID

import pytest
from api.main import get_current_user
from api.routers import scouting
from api.routers import simple_farm_book as book
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_TASK = UUID("6f1c2d3e-4b5a-4c6d-8e7f-a0b1c2d3e4f5")
_TENANT = "00000000-0000-0000-0000-000000000001"
_P1 = "https://evidence.example/visit/photo-1.jpg"
_P2 = "https://evidence.example/visit/photo-2.jpg"


def _digest(photo, notes):
    # The same canonical form as scouting.evidence_digest, kept local so the gate is measured
    # even on a tree without that helper.
    raw = json.dumps([photo, notes], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_evidence_digest_separates_photo_and_notes():
    assert scouting.evidence_digest(_P1, "x") == _digest(_P1, "x")
    assert scouting.evidence_digest("a", "b") != scouting.evidence_digest("ab", None)
    assert scouting.evidence_digest(None, None) != scouting.evidence_digest("", "")


def test_only_the_inspector_submit_carries_evidence():
    with pytest.raises(ValueError):
        scouting.InspectionFinding(
            expected_revision=4, action="approve", reason="ok", photo_url=_P2
        )
    sent = scouting.InspectionFinding(
        expected_revision=4, action="submit", reason="ok", photo_url=_P2
    )
    assert sent.photo_url == _P2


def _book_client(role):
    app = FastAPI()
    app.include_router(book.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id="5", tenant_id=_TENANT, role=role, name_ar="مستخدم"
    )
    return TestClient(app)


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.AGRONOMIST])
def test_roles_without_expense_write_cannot_link(role):
    refused = _book_client(role).post(
        "/api/v1/farm-book/entries/fbe_1/task", json={"task_id": str(_TASK)}
    )
    assert refused.status_code == 403


def test_the_cost_trace_stays_behind_analytics_view():
    # A worker may link a receipt (activity:execute, proved live) but not read the totals.
    assert _book_client(UserRole.WORKER).get(f"/api/v1/tasks/{_TASK}/cost-trace").status_code == 403
