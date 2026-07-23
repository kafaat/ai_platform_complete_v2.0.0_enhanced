"""حارس ساكن لعيوب مراجعة PR #585 في field_forms_api.py — يفحص النصّ بلا تبعيّات.

يمنع تراجع P0-2/P0-3 صامتًا: لو عاد الربط مشروطًا (if actor_id and ...) أو غاب
حلّ الإسناد عن مسار current، يفشل هذا الحارس فورًا في أيّ بيئة CI.
"""

from __future__ import annotations

from pathlib import Path

API = (
    Path(__file__).resolve().parents[1] / "services" / "scout-ingest-service" / "field_forms_api.py"
).read_text(encoding="utf-8")


def test_actor_binding_unconditional() -> None:
    assert 'if not actor_id or claims["actor_id"] != actor_id:' in API
    assert 'if actor_id and claims["actor_id"]' not in API


def test_device_binding_mandatory() -> None:
    assert 'alias="X-Device-Id"' in API
    # الحضور إلزاميّ: غياب device_id يفشل الإثبات (fail-closed) لا يتخطّى المقارنة.
    assert "if not device_id:" in API
    # التطابق مطلوب؛ الاستثناء الوحيد نافذة تدوير device-key صريحة (§9.2.1) مغلقة
    # افتراضيًّا (grace<=0 ⇒ _device_rotation_grace_ok=False ⇒ السلوك القائم لا يتغيّر).
    assert 'claims["device_id"] != device_id' in API
    # منع تراجع P0-3: ربط مشروط (if device_id and ...) يتخطّى فحص الجهاز عند غيابه.
    assert 'if device_id and claims["device_id"]' not in API


def test_revision_binding_unconditional() -> None:
    assert 'if assignment_revision is None or claims["revision"] != assignment_revision:' in API
    assert 'if assignment_revision is not None and claims["revision"]' not in API


def test_assignment_claim_read_from_postgres() -> None:
    assert "_assignment_row_matches" in API
    assert "FROM field_form_assignments" in API


def test_current_submission_requires_assignment() -> None:
    assert "_resolve_active_assignment" in API
    assert "no_active_assignment" in API
    assert 'raise HTTPException(status_code=409, detail="ambiguous_active_assignment")' in API
