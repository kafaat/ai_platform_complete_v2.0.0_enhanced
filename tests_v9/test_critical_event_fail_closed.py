"""ضمان at-least-once للأحداث الحرجة: _emit_domain_event يُفشِل المعاملة عند تعذّر
الكتابة للـoutbox للأحداث الحرجة (fail-closed)، ويبقى best-effort لغير الحرجة.

السياق: نمط الـoutbox يكتب صفّ الحدث في **نفس** معاملة تغيير العمل، فلا يضيع. لكنّ
_emit_domain_event كان يبتلع فشل الإدراج دائماً (warn-and-continue) — فقد يُلتزَم تغيير
عمل بلا حدثه الحرج (كسر at-least-once). الإصلاح: للأحداث الحرجة (CRITICAL_EVENT_TYPES أو
critical=True) يُعاد رفع الخطأ ⇒ تُجهَض المعاملة الخارجيّة؛ ولغير الحرجة يبقى السلوك
best-effort (تحذير-ومتابعة) كي لا تتحوّل إشارةٌ لينة إلى انقطاع.

فحص سلوكيّ بلا قاعدة: conn مزيّف + EventBus.emit مُرقَّع (يرفع/ينجح) — لا Postgres.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def main_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m  # noqa: WPS433 — تهيئة بعد ضبط المسار

    return m


class _FakeUser:
    """مستخدم مزيّف يكفي لـ_emit_domain_event (tenant_id/user_id/role)."""

    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "admin"


class _FakeTxn:
    """savepoint مزيّف: async context manager بلا أثر قاعدة."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False  # لا يبتلع — يَدَع الاستثناء يصعد كما القاعدة الحقيقيّة


class _FakeConn:
    def transaction(self):
        return _FakeTxn()


def _patch_emit(monkeypatch, main_mod, *, raise_exc: Exception | None):
    """يُرقّع EventBus.emit وget_pool فلا يُلمَس Postgres.

    raise_exc=None ⇒ نجاح؛ غير None ⇒ يرفع (يحاكي غياب جدول/فشل DB).
    """
    from api.event_bus import EventBus

    async def _fake_emit(self, **kwargs):  # noqa: ANN001
        if raise_exc is not None:
            raise raise_exc
        return None  # نجاح صامت يكفي للمسار السعيد

    monkeypatch.setattr(EventBus, "emit", _fake_emit, raising=True)
    monkeypatch.setattr(main_mod, "get_pool", lambda: object(), raising=True)


# ── (أ) حدث حرج + فشل الإدراج ⇒ يُعاد رفع الاستثناء (المعاملة الخارجيّة تُجهَض) ──


async def test_critical_event_failure_propagates(main_mod, monkeypatch):
    _patch_emit(monkeypatch, main_mod, raise_exc=RuntimeError("outbox insert failed"))
    user = _FakeUser()
    # نوع ضمن CRITICAL_EVENT_TYPES ⇒ fail-closed بلا تمرير صريح.
    assert "DISPATCH_DECISION_RECORDED" in main_mod.CRITICAL_EVENT_TYPES
    with pytest.raises(RuntimeError, match="outbox insert failed"):
        await main_mod._emit_domain_event(
            _FakeConn(), user, "DISPATCH_DECISION_RECORDED", "dispatch_decision", "d1", {}
        )


async def test_critical_flag_overrides_non_critical_type(main_mod, monkeypatch):
    """critical=True يفرض fail-closed حتى لنوع ليس في القائمة (التمرير الصريح يَغلِب)."""
    _patch_emit(monkeypatch, main_mod, raise_exc=RuntimeError("boom"))
    user = _FakeUser()
    assert "ALERT_CREATED" not in main_mod.CRITICAL_EVENT_TYPES
    with pytest.raises(RuntimeError, match="boom"):
        await main_mod._emit_domain_event(
            _FakeConn(), user, "ALERT_CREATED", "alert", "a1", {}, critical=True
        )


# ── (ب) حدث غير حرج + فشل الإدراج ⇒ يُبتلَع/يُحذَّر بلا رفع ──


async def test_non_critical_event_failure_swallowed(main_mod, monkeypatch):
    _patch_emit(monkeypatch, main_mod, raise_exc=RuntimeError("table missing"))
    user = _FakeUser()
    assert "ALERT_CREATED" not in main_mod.CRITICAL_EVENT_TYPES
    # لا يرفع — best-effort. الإرجاع None ضمنيّ.
    result = await main_mod._emit_domain_event(
        _FakeConn(), user, "ALERT_CREATED", "alert", "a1", {}
    )
    assert result is None


async def test_critical_false_forces_best_effort(main_mod, monkeypatch):
    """critical=False يفرض best-effort حتى لنوع حرج (تمرير صريح يَغلِب الاشتقاق)."""
    _patch_emit(monkeypatch, main_mod, raise_exc=RuntimeError("ignored"))
    user = _FakeUser()
    await main_mod._emit_domain_event(
        _FakeConn(),
        user,
        "DISPATCH_DECISION_RECORDED",
        "dispatch_decision",
        "d1",
        {},
        critical=False,
    )  # لا يرفع


# ── (ج) المسار السعيد (نجاح الإصدار) غير متأثّر لكِلا النوعين ──


async def test_success_path_unaffected_critical(main_mod, monkeypatch):
    _patch_emit(monkeypatch, main_mod, raise_exc=None)
    user = _FakeUser()
    await main_mod._emit_domain_event(
        _FakeConn(), user, "DISPATCH_DECISION_RECORDED", "dispatch_decision", "d1", {}
    )  # لا يرفع


async def test_success_path_unaffected_non_critical(main_mod, monkeypatch):
    _patch_emit(monkeypatch, main_mod, raise_exc=None)
    user = _FakeUser()
    await main_mod._emit_domain_event(
        _FakeConn(), user, "ALERT_CREATED", "alert", "a1", {}
    )  # لا يرفع


# ── محتوى القائمة الحرجة: حوكمة/مال/تبدّل حالة فقط (لا تيليمتري) ──


def test_critical_set_membership(main_mod):
    crit = main_mod.CRITICAL_EVENT_TYPES
    for name in (
        "DISPATCH_DECISION_RECORDED",
        "DISPATCH_EXECUTION_RECORDED",
        "DECISION_RECORDED",
        "OUTCOME_MEASURED",
        "LINEAGE_LINKED",
        "IRRIGATION_VALVE_STATE_CHANGED",
        "CALIBRATION_OVERRIDE_SET",
    ):
        assert name in crit, f"{name} يجب أن يكون حرجاً"
    # تيليمتري/إشارات لينة تبقى غير حرجة (best-effort) كي لا تصبح انقطاعاً.
    for name in (
        "ALERT_CREATED",
        "RECOMMENDATION_CREATED",
        "NOTIFICATION_DELIVERED",
        "TASK_UPDATED",
        "FARM_CREATED",
    ):
        assert name not in crit, f"{name} يجب أن يبقى غير حرج (best-effort)"


def test_critical_names_are_valid_event_types(main_mod):
    """كلّ اسم في القائمة الحرجة عضوٌ فعليّ في EventType (لا اسم ميّت)."""
    from api.event_bus import EventType

    for name in main_mod.CRITICAL_EVENT_TYPES:
        assert name in EventType.__members__, f"{name} ليس عضواً في EventType"
