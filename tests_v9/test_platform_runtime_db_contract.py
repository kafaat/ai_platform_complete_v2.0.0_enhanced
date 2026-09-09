"""Regression guards for platform runtime database state and tenant context wiring."""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "services" / "sahool-platform" / "api" / "routers"


@pytest.mark.unit
def test_routers_never_snapshot_db_pool_from_main() -> None:
    offenders: list[str] = []
    for path in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.module != "api.main":
                continue
            if any(alias.name == "_DB_POOL" for alias in node.names):
                offenders.append(path.name)
    assert offenders == [], (
        "top-level `from api.main import _DB_POOL` snapshots None before lifespan startup: "
        + ", ".join(offenders)
    )


@pytest.mark.unit
def test_the_call_shape_rule_has_exactly_one_definition() -> None:
    """شكلُ نداء ``tenant_connection`` يُفرَض في موضعٍ **واحد** — لا هنا.

    كان هذا الملفّ يحمل نسخةً ثانيةً من القاعدة
    (``test_routers_do_not_pass_scalar_tenant_to_user_connection``)، وهي **أضعفُ**
    من الحارس القانونيّ في محورين مقيسَين:

    * **النطاق:** ``routers/*.py`` وحدَها مقابل كامل ``services/sahool-platform``.
    * **العقد:** الاسم ``tenant_id`` مثبَّتٌ نصّاً، مقابل اشتقاقِ السمات من توقيع
      ``tenant_connection`` نفسِه — فلو غُيِّر التوقيعُ غداً تبِع الحارسُ القانونيُّ
      وتخلّفت النسخةُ هنا.

    وحذفُها ليس تخفيفاً بل **إغلاقٌ لصنفٍ بعينه**: تعريفان لحقيقةٍ واحدة يتّفقان
    اليوم وينحرفان غداً — وهو الصنفُ الذي أُغلِق في #973 في أخطر موضعَيه (حكمُ
    الاعتماد وسياسةُ المطر). فيبقى هذا الملفّ على ما ينفرد به: لقطةُ ``_DB_POOL``.

    وهذا الاختبارُ ليس تعليقاً: يُحمِّر إن زال الحارسُ القانونيُّ من الشجرة، فلا
    يُحذَف المُنفرِدُ ويبقى الحذفُ هنا بلا بديل.
    """
    canonical = ROOT / "scripts" / "ci" / "tenant_connection_call_shape_guard.py"
    assert canonical.is_file(), (
        f"الحارسُ القانونيُّ لشكل النداء غائب؛ حُذِفت النسخةُ المكرَّرة من هنا اعتماداً عليه: {canonical}"
    )
    source = canonical.read_text(encoding="utf-8")
    assert "def contract()" in source, "الحارسُ لم يعد يشتقّ عقدَه من التوقيع"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_irrigation_ownership_uses_authenticated_user(monkeypatch) -> None:
    from api.routers import irrigation_mpc

    user = object()
    seen: list[object] = []

    class _Conn:
        async def fetchrow(self, _sql: str, _field_id: str):
            return {"owned": True}

    @contextlib.asynccontextmanager
    async def _tenant_connection(actual_user):
        seen.append(actual_user)
        yield _Conn()

    monkeypatch.setattr(irrigation_mpc, "tenant_connection", _tenant_connection)
    assert await irrigation_mpc._field_belongs_to_tenant(user, "field-1") is True
    assert seen == [user]


@pytest.mark.unit
def test_db_pool_consumers_follow_main_rebinding() -> None:
    from api import main
    from api.routers import prescriptions, water_ledger

    original = main._DB_POOL
    sentinel = object()
    try:
        main._DB_POOL = sentinel
        assert water_ledger.api_main._DB_POOL is sentinel
        assert prescriptions.api_main._DB_POOL is sentinel
    finally:
        main._DB_POOL = original
