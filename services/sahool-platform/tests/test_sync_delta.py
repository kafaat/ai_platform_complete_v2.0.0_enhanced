"""اختبار المزامنة التفاضليّة (Delta-Sync) — منطق نقيّ + توصيل العلم.

يُثبت — بلا قاعدة/خدمات:
  منطق ``filter_since`` النقيّ (api/sync_delta.py):
    ١) cursor=None ⇒ كلّ العمليّات (السلوك الحاليّ، full replay).
    ٢) cursor وسط ⇒ الأحدث فقط (إقصاء ما ≤ cursor).
    ٣) cursor فاسد (نوع غير نصّيّ/فارغ) ⇒ كلّ العمليّات (ارتداد آمن، fail-safe).
    ٤) الترتيب الأصليّ (FIFO) محفوظ.
    ٥) عمليّة بلا ``created_at`` تُبقى دائماً (لا إسقاط ما لا يُؤرَّخ).
    ٦) ``newest_cursor`` يحسب أحدث طابع (None إن لا طوابع).
  توصيل العلم (api/routers/sync.py):
    ٧) ``FEATURE_DELTA_SYNC`` مُطفأ افتراضاً ⇒ ``_delta_sync_enabled()`` False.
    ٨) متغيّرات صادقة/كاذبة للعلم.
    ٩) نقطة ``POST /api/v1/sync`` مُسجَّلة على app.routes.

مُعلَّم unit؛ يُشغَّل من services/sahool-platform بـPYTHONPATH=.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import api.main as _m  # noqa: E402,F401  (يُحمَّل أوّلاً لكسر الاستيراد الدائريّ)
from api import sync_delta  # noqa: E402
from api.routers import sync as sync_router  # noqa: E402
from api.sync_delta import filter_since, newest_cursor  # noqa: E402


def _ops(*timestamps: str) -> list[dict]:
    """عمليّات اختباريّة على شكل dict مع created_at (يطابق مُدخل /api/v1/sync)."""
    return [{"kind": "observation_create", "created_at": ts} for ts in timestamps]


# ─── منطق filter_since النقيّ ─────────────────────────────────────


def test_cursor_none_returns_all():
    ops = _ops("2026-06-20T10:00:00", "2026-06-20T11:00:00")
    out = filter_since(ops, None)
    assert out == ops
    assert out is not ops  # قائمة جديدة (لا تعديل المُدخل)


def test_cursor_empty_string_returns_all():
    ops = _ops("2026-06-20T10:00:00", "2026-06-20T11:00:00")
    assert filter_since(ops, "") == ops


def test_cursor_middle_returns_only_newer():
    ops = _ops(
        "2026-06-20T09:00:00",
        "2026-06-20T10:00:00",  # = cursor، يُقصى (نستعمل > لا >=)
        "2026-06-20T11:00:00",
        "2026-06-20T12:00:00",
    )
    out = filter_since(ops, "2026-06-20T10:00:00")
    assert [o["created_at"] for o in out] == [
        "2026-06-20T11:00:00",
        "2026-06-20T12:00:00",
    ]


def test_cursor_newest_returns_empty():
    ops = _ops("2026-06-20T09:00:00", "2026-06-20T10:00:00")
    assert filter_since(ops, "2026-06-20T10:00:00") == []


@pytest.mark.parametrize("bad", [123, 4.5, [], {}, object()])
def test_invalid_cursor_type_falls_back_to_full(bad):
    ops = _ops("2026-06-20T09:00:00", "2026-06-20T10:00:00")
    # cursor فاسد (نوع غير نصّيّ) ⇒ ارتداد لـfull (لا فقدان عمليّات).
    assert filter_since(ops, bad) == ops


def test_order_preserved_fifo():
    ops = _ops(
        "2026-06-20T11:00:00",
        "2026-06-20T13:00:00",
        "2026-06-20T12:00:00",  # غير مرتّب زمنيّاً عمداً
    )
    out = filter_since(ops, "2026-06-20T10:00:00")
    # كلّها أحدث من cursor ⇒ تُرجَع بترتيب الإدخال (FIFO) لا مرتّبة بالطابع.
    assert [o["created_at"] for o in out] == [
        "2026-06-20T11:00:00",
        "2026-06-20T13:00:00",
        "2026-06-20T12:00:00",
    ]


def test_op_without_created_at_always_kept():
    ops = [
        {"kind": "observation_create", "created_at": "2026-06-20T09:00:00"},  # ≤ cursor
        {"kind": "observation_create"},  # بلا طابع ⇒ يُبقى
        {"kind": "observation_create", "created_at": "2026-06-20T12:00:00"},  # أحدث
    ]
    out = filter_since(ops, "2026-06-20T10:00:00")
    # الأقدم يُقصى، بلا-طابع يُبقى، الأحدث يُبقى.
    assert out == [ops[1], ops[2]]


def test_empty_operations():
    assert filter_since([], None) == []
    assert filter_since([], "2026-06-20T10:00:00") == []


def test_filter_since_accepts_objects_with_created_at_attr():
    class _Op:
        def __init__(self, ts: str) -> None:
            self.created_at = ts

    ops = [_Op("2026-06-20T09:00:00"), _Op("2026-06-20T12:00:00")]
    out = filter_since(ops, "2026-06-20T10:00:00")
    assert out == [ops[1]]


# ─── newest_cursor ────────────────────────────────────────────────


def test_newest_cursor_picks_max():
    ops = _ops("2026-06-20T11:00:00", "2026-06-20T13:00:00", "2026-06-20T12:00:00")
    assert newest_cursor(ops) == "2026-06-20T13:00:00"


def test_newest_cursor_none_when_no_timestamps():
    assert newest_cursor([]) is None
    assert newest_cursor([{"kind": "observation_create"}]) is None


# ─── توصيل العلم FEATURE_DELTA_SYNC ───────────────────────────────


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("FEATURE_DELTA_SYNC", raising=False)
    assert sync_router._delta_sync_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_flag_on_variants_enable(monkeypatch, val):
    monkeypatch.setenv("FEATURE_DELTA_SYNC", val)
    assert sync_router._delta_sync_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "off", "", "maybe"])
def test_flag_falsey_variants_disable(monkeypatch, val):
    monkeypatch.setenv("FEATURE_DELTA_SYNC", val)
    assert sync_router._delta_sync_enabled() is False


def test_sync_endpoint_registered():
    routes = {
        (meth, getattr(r, "path", ""))
        for r in _m.app.routes
        for meth in (getattr(r, "methods", None) or set())
    }
    assert ("POST", "/api/v1/sync") in routes


def test_sync_delta_module_pure_no_io():
    # الوحدة نقيّة: لا تستورد قاعدة/شبكة. نتحقّق أنّ filter_since/newest_cursor
    # دالّتان عاديّتان قابلتان للاستدعاء بلا أيّ تهيئة.
    assert callable(sync_delta.filter_since)
    assert callable(sync_delta.newest_cursor)
