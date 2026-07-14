"""المهامّ الميدانيّة (field_tasks) — تحقّق تسجيل /api/v1/tasks وعقد {tasks:[...]}.

الخلفيّة: كانت الواجهة تنادي /tasks بلا أيّ مسار خلفيّ (404 مُبتلَع). هذا الاختبار
يضمن وجود المسارَين (GET قائمة + PATCH تحديث) وأنّ القائمة تُرجِع غلاف {tasks:[...]}
الذي تتوقّعه الواجهة — فيلتقط ارتداد «المسار غير مُسجَّل» مباشرةً (CI-enforced).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def app_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


def _token(
    m, role: str = "agronomist", tenant: str = "11111111-1111-1111-1111-111111111111"
) -> str:
    now = datetime.now(UTC)
    return m.jwt.encode(
        {
            "sub": "u_tasks_test",
            "tenant_id": tenant,
            "role": role,
            "name_ar": "مختبِر",
            "iss": "sahool-platform",
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        m.JWT_SECRET,
        algorithm=m.JWT_ALGORITHM,
    )


def test_tasks_routes_registered(app_mod):
    """المسارات الجديدة مُسجَّلة فعلاً (لا ديكوريتر مفقود)."""
    paths = {getattr(r, "path", None) for r in app_mod.app.routes}
    assert "/api/v1/tasks" in paths, "GET /api/v1/tasks غير مُسجَّل"
    assert "/api/v1/tasks/{task_id}" in paths, "PATCH /api/v1/tasks/{task_id} غير مُسجَّل"


def test_tasks_methods(app_mod):
    """GET على القائمة وPATCH على العنصر."""
    methods: dict[str, set[str]] = {}
    for r in app_mod.app.routes:
        p = getattr(r, "path", None)
        if p in ("/api/v1/tasks", "/api/v1/tasks/{task_id}"):
            methods.setdefault(p, set()).update(getattr(r, "methods", set()) or set())
    assert "GET" in methods.get("/api/v1/tasks", set())
    assert "PATCH" in methods.get("/api/v1/tasks/{task_id}", set())


def test_tasks_list_contract(app_mod):
    """قائمة المهامّ تُرجِع غلاف {tasks:[...]} (عقد الواجهة) — أو 503 بلا قاعدة.

    لا نفترض قاعدة بيانات حيّة: نقبل 200 (بعقد صحيح) أو 401/503 (مصادقة/قاعدة).
    المهمّ ألّا يكون 404 (المسار موجود) وأن يكون الشكل {tasks:[...]} عند 200.
    """
    from fastapi.testclient import TestClient

    client = TestClient(app_mod.app, raise_server_exceptions=False)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {_token(app_mod)}"})
    assert resp.status_code != 404, "المسار يجب أن يكون مُسجَّلاً (لا 404)"
    if resp.status_code == 200:
        body = resp.json()
        assert isinstance(body, dict) and "tasks" in body and isinstance(body["tasks"], list)


def test_tasks_list_accepts_pagination_params(app_mod):
    """?limit/&offset مقبولان كمعاملَي استعلام (لا 404/422) — مغلّف F5-06 متوافق للخلف."""
    from fastapi.testclient import TestClient

    client = TestClient(app_mod.app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/tasks?limit=5&offset=0",
        headers={"Authorization": f"Bearer {_token(app_mod)}"},
    )
    assert resp.status_code != 404
    assert resp.status_code != 422, "limit/offset يجب أن يكونا مقبولَين"


def test_task_list_response_has_optional_pagination_fields(app_mod):
    """نموذج TaskListResponse يحمل حقول الترقيم الاختياريّة (total/limit/next_cursor)."""
    fields = app_mod.TaskListResponse.model_fields
    for f in ("tasks", "total", "limit", "next_cursor"):
        assert f in fields, f"TaskListResponse ينقصه الحقل {f}"
    # الحقول الجديدة اختياريّة (افتراضها None) فيبقى العقد متوافقاً للخلف.
    assert fields["total"].default is None
    assert fields["next_cursor"].default is None
