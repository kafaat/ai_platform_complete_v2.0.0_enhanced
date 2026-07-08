"""Guard: Learning/lineage dashboard degrades honestly when the decision-records read
is unavailable — an empty *degraded* state, never fabricated numbers, never a collapsed page.

Architecture note (interim dual-path, decision d201527): sahool-platform is the
authoritative Source-of-Record for decision writes AND the decision-records read path.
`list_decision_records` reads the platform's own Postgres directly (RLS-isolated) and
raises a documented 503 when the database is unavailable — it is deliberately NOT a
best-effort facade to decision-service on the read side. Because the authoritative read
honestly surfaces unavailability as 404/502/503/504, the *graceful degradation* for the
observability dashboard lives in the frontend: `fetchDecisionRecords` maps those statuses
to a `degraded` empty result, and `LearningDashboardPage` renders a degraded banner
instead of a hard error. Auth/RBAC failures (401/403) stay hard — they are not
availability degradation.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_decision_records_read_is_authoritative_direct_db_not_facade():
    """The read path stays the authoritative direct-DB SoR read (dual-path), raising an
    honest 503 on DB failure — it must NOT be re-wrapped as a best-effort decision-service
    facade read (that would silently reverse the platform-as-SoR decision)."""
    src = read("services/sahool-platform/api/routers/decision_record.py")
    start = src.index("async def list_decision_records(")
    body = src[start : src.index("def _group_outcomes_by_decision")]
    # Authoritative platform read: RLS connection + honest 503 on DB error.
    assert "tenant_connection(user)" in body, "read path must use the platform DB (SoR)"
    assert "_db_unavailable(" in body, (
        "DB failure must surface as an honest 503, not fabricated data"
    )
    # It must not have been reverted to a decision-service facade read.
    assert "_list_decisions_via_service" not in body, (
        "read path must not delegate to decision-service facade — platform is the SoR (d201527)"
    )


def test_frontend_decision_records_has_degraded_contract():
    """Frontend degrades on availability failures (404/502/503/504) to an honest empty
    state; auth failures are left to throw."""
    src = read("frontend/src/services/api.ts")
    assert "degraded?: boolean" in src
    assert "warning_ar?: string" in src
    assert "decision_records_unavailable" in src
    assert "[404, 502, 503, 504].includes(status)" in src


def test_learning_dashboard_renders_degraded_banner_not_hard_error():
    src = read("frontend/src/sections/LearningDashboardPage.tsx")
    assert "recordsDegraded" in src
    assert "تعمل اللوحة في وضع متدهور" in src
    assert "لا تُعرض أرقام مُلفّقة" in src
    assert "تعطل read-side لخدمة القرار" in src
