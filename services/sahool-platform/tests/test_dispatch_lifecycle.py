"""اختبارات تصليب الموزِّع (core.dispatch_lifecycle) — المرحلة A، الشريحة 2.

نقيّة وحتميّة ⇒ `unit`. تثبّت: حتميّة مفتاح اللاتكرار، حراسة دورة حياة exec_status
(الانتقالات المسموحة فقط، fail-closed على غيرها)، والحالات النهائيّة.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.dispatch_lifecycle import (  # noqa: E402
    LIVE_EXEC_STATES,
    assert_transition,
    can_transition,
    derive_idempotency_key,
    is_terminal,
    is_valid_exec_status,
)


# ── مفتاح اللاتكرار ──
def test_idempotency_key_is_deterministic():
    a = derive_idempotency_key("rec1", "irrigation", "f1")
    b = derive_idempotency_key("rec1", "irrigation", "f1")
    assert a == b
    assert a.startswith("disp:")


def test_idempotency_key_differs_per_identity():
    base = derive_idempotency_key("rec1", "irrigation", "f1")
    assert derive_idempotency_key("rec2", "irrigation", "f1") != base
    assert derive_idempotency_key("rec1", "spray", "f1") != base
    assert derive_idempotency_key("rec1", "irrigation", "f2") != base


def test_idempotency_key_handles_missing_field():
    k = derive_idempotency_key("rec1", "irrigation", None)
    assert k.startswith("disp:")
    assert k == derive_idempotency_key("rec1", "irrigation", "")


def test_idempotency_key_fits_column():
    # عمود VARCHAR(120) — المفتاح أقصر بكثير (بادئة + sha1[:24]).
    assert len(derive_idempotency_key("r" * 80, "irrigation", "f" * 50)) <= 120


# ── دورة الحياة: التحقّق من الحالات ──
def test_valid_exec_statuses():
    for s in ("not_executed", "queued", "dispatched", "executed", "failed"):
        assert is_valid_exec_status(s)
    assert not is_valid_exec_status("bogus")
    assert not is_valid_exec_status("")


def test_terminal_states():
    assert is_terminal("not_executed")
    assert is_terminal("executed")
    assert is_terminal("failed")
    assert not is_terminal("queued")
    assert not is_terminal("dispatched")


def test_live_states_constant():
    assert set(LIVE_EXEC_STATES) == {"queued", "dispatched"}


# ── دورة الحياة: الانتقالات المسموحة ──
def test_allowed_transitions():
    assert can_transition("queued", "dispatched")
    assert can_transition("queued", "failed")
    assert can_transition("dispatched", "executed")
    assert can_transition("dispatched", "failed")


def test_forbidden_transitions():
    # لا قفز من queued إلى executed دون المرور بـdispatched.
    assert not can_transition("queued", "executed")
    # لا انتقال من حالة نهائيّة.
    assert not can_transition("executed", "failed")
    assert not can_transition("failed", "executed")
    assert not can_transition("not_executed", "queued")
    # لا رجوع للخلف.
    assert not can_transition("dispatched", "queued")


def test_assert_transition_returns_normalized_target():
    assert assert_transition("QUEUED", "Dispatched") == "dispatched"


def test_assert_transition_raises_on_forbidden():
    with pytest.raises(ValueError, match="غير مسموح"):
        assert_transition("queued", "executed")


def test_assert_transition_raises_on_unknown():
    with pytest.raises(ValueError, match="مجهولة"):
        assert_transition("queued", "frobnicate")
    with pytest.raises(ValueError, match="مجهولة"):
        assert_transition("nope", "queued")
