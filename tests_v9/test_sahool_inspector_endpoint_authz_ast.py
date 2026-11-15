"""فحص «endpoint authz» في Sahool Inspector يقرأ توقيع النقطة بشجرة Python لا بتعبير نمطيّ.

الدرس (SAHOOL #1449): التعبير السابق أنهى التوقيع عند أوّل ``):``، فتعليقٌ داخل التوقيع
يحمل ``):`` أخفى ``Depends(require_permission(...))`` بعده، فصُنِّفت نقطة مصادَقة HIGH
«تمسّ قاعدة بلا مصادقة». هذه الاختبارات تبني راوترات مؤقّتة وتُشغّل الفحص عليها.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "sahool_inspector.py"
_spec = importlib.util.spec_from_file_location("sahool_inspector_authz_ast", _TOOL)
inspector = importlib.util.module_from_spec(_spec)
sys.modules["sahool_inspector_authz_ast"] = inspector
_spec.loader.exec_module(inspector)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str):
    routers = tmp_path / "routers"
    routers.mkdir()
    (routers / "sample.py").write_text(textwrap.dedent(source), encoding="utf-8")
    monkeypatch.setattr(inspector, "REPO", tmp_path)
    monkeypatch.setattr(inspector, "ROUTERS", routers)
    return inspector.check_endpoint_authz()


def test_comment_with_paren_colon_does_not_hide_require_permission(tmp_path, monkeypatch):
    # الحالة التي أنتجت HIGH كاذباً: تعليق فيه «):» قبل Depends(require_permission(...)).
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.get("/api/v1/fields/{field_id}/state")
        async def field_state(
            field_id: str,
            # صارم (مراجعة #1449): GET يقرأ حالة الحقل للمستأجِر فقط
            user=Depends(require_permission("fields:read")),
        ):
            async with tenant_connection(user) as conn:
                return await conn.fetchrow("SELECT 1")
        """,
    )
    assert result.findings == [], result.findings
    assert result.status == inspector.PASS
    assert result.summary.startswith("1 نقطة؛ 0 تمسّ"), result.summary


def test_unauthenticated_db_route_is_still_high(tmp_path, monkeypatch):
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.post("/api/v1/fields/{field_id}/notes")
        async def add_note(field_id: str, body: dict):
            async with tenant_connection(None) as conn:
                await conn.execute("INSERT INTO notes VALUES ($1)", field_id)
        """,
    )
    assert result.status == inspector.FAIL
    assert result.findings == [
        "HIGH نقطة تمسّ قاعدة/مستأجِر بلا مصادقة: POST /api/v1/fields/{field_id}/notes "
        "(routers/sample.py:2 — add_note)"
    ]


def test_unauthenticated_pure_route_is_info_and_health_is_exempt(tmp_path, monkeypatch):
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.get("/healthz")
        async def healthz():
            return {"ok": _DB_POOL is not None}

        @router.get("/api/v1/proverbs")
        def proverbs():
            return PROVERBS
        """,
    )
    assert result.status == inspector.WARN
    assert result.summary.startswith("2 نقطة؛ 0 تمسّ قاعدة/مستأجِر بلا مصادقة (خطر)، 1 عامّة")
    assert result.findings == [
        "INFO نقطة عامّة (بيانات مرجعيّة نقيّة) بلا مصادقة: GET /api/v1/proverbs "
        "(routers/sample.py:6 — proverbs)"
    ]


def test_stacked_decorators_map_to_their_own_function(tmp_path, monkeypatch):
    # الديكور العلويّ لنقطة مصادَقة، ثمّ نقطة عامّة تمسّ القاعدة بديكورات مكدَّسة.
    # كلّ ديكور مسار يُنسب إلى دالّته هو، لا إلى الدالّة التالية ولا السابقة.
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.get("/api/v1/a")
        @limiter.limit("5/minute")
        @cache(ttl=60)
        async def secured(user=Depends(get_current_user)):
            return {"a": 1}

        @router.get("/api/v1/b")
        @router.get("/api/v1/b-alias")
        @limiter.limit("5/minute")
        async def open_db(request: Request):
            pool = get_pool()
            return await pool.fetch("SELECT 1")

        @router.delete("/api/v1/c")
        @audit("c")
        async def internal(_=Depends(_require_service_token)):
            await conn.execute("DELETE FROM c")
        """,
    )
    assert result.summary.startswith("4 نقطة؛ 2 تمسّ"), result.summary
    assert result.findings == [
        "HIGH نقطة تمسّ قاعدة/مستأجِر بلا مصادقة: GET /api/v1/b (routers/sample.py:8 — open_db)",
        "HIGH نقطة تمسّ قاعدة/مستأجِر بلا مصادقة: GET /api/v1/b-alias "
        "(routers/sample.py:9 — open_db)",
    ]


def test_db_access_in_a_helper_after_the_handler_still_counts(tmp_path, monkeypatch):
    # Review of #1477: the regex scanned up to the next route decorator, the first AST version
    # only the function body, so an unauthenticated route reaching the DB via a helper defined
    # right after it fell from HIGH to INFO. The scanned extent is the old one again.
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.get("/api/v1/leak")
        async def leak():
            return await _helper()


        async def _helper():
            async with tenant_connection(None) as conn:
                return await conn.fetch("SELECT * FROM fields")


        @router.get("/api/v1/pure")
        async def pure():
            return {"ok": True}
        """,
    )
    assert result.status == inspector.FAIL
    assert result.findings == [
        "HIGH نقطة تمسّ قاعدة/مستأجِر بلا مصادقة: GET /api/v1/leak (routers/sample.py:2 — leak)",
        # The next route's extent starts after the helper, so `pure` stays INFO.
        "INFO نقطة عامّة (بيانات مرجعيّة نقيّة) بلا مصادقة: GET /api/v1/pure (routers/sample.py:12 — pure)",
    ]


def test_an_unparseable_router_file_is_reported_not_skipped(tmp_path, monkeypatch):
    result = _run(
        tmp_path,
        monkeypatch,
        """
        @router.post("/api/v1/x")
        async def x(body: dict):
            async with tenant_connection(None) as conn:
                await conn.execute("DELETE FROM fields")

        def broken(:
            pass
        """,
    )
    assert result.status == inspector.FAIL
    assert any("لا يُحلَّل" in f and "routers/sample.py" in f for f in result.findings), (
        result.findings
    )
