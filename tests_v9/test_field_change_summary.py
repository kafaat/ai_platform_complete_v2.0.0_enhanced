"""بوّابة المسار 1 (MCP فوق CDSE) — منطق تلخيص تغيّر الحقل النقيّ + تسجيل الأداة.

اختبار وحدة لا يتطلّب خادماً حيّاً: يختبر المنطق النقيّ في
``shared.field_change_summary`` مباشرةً، ويؤكّد ساكناً أنّ أداة
``analyze_field_change`` مسجّلة في خادم MCP وتبقى قراءة-فقط (satellite:read).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shared.field_change_summary import (
    MAX_CLOUD_PCT,
    STABLE_BAND,
    InsufficientObservations,
    summarize_field_change,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "services" / "mcp_servers" / "sentinel_hub_server.py"


def _pt(date, mean, cloud=0.0):
    return {"datetime": date, "mean": mean, "cloud_pct": cloud}


def test_improving_change_between_first_and_last() -> None:
    out = summarize_field_change(
        [_pt("2026-03-01", 0.40), _pt("2026-04-01", 0.52), _pt("2026-05-01", 0.60)],
        field_id="f1",
        tenant_id="t1",
        index="ndvi",
    )
    assert out["from"]["date"] == "2026-03-01"
    assert out["to"]["date"] == "2026-05-01"
    assert out["delta"] == 0.2
    assert out["direction"] == "improving"
    assert out["observations_used"] == 3
    assert out["real_data"] is True
    assert out["source"] == "raster-service"


def test_declining_and_stable_directions() -> None:
    dec = summarize_field_change(
        [_pt("2026-03-01", 0.60), _pt("2026-05-01", 0.40)], field_id="f", tenant_id="t"
    )
    assert dec["direction"] == "declining"
    stable = summarize_field_change(
        [_pt("2026-03-01", 0.50), _pt("2026-05-01", 0.505)], field_id="f", tenant_id="t"
    )
    assert stable["direction"] == "stable"
    assert abs(stable["delta"]) <= STABLE_BAND


def test_cloudy_and_null_points_excluded() -> None:
    # سحاب > 30% أو غير مقيس (None) أو mean=None ⇒ غير مؤهّل.
    out = summarize_field_change(
        [
            _pt("2026-03-01", 0.40, cloud=5),
            _pt("2026-03-15", 0.99, cloud=80),  # مُلبّد ⇒ يُستبعَد
            {"datetime": "2026-03-20", "mean": None, "cloud_pct": 0},  # لا قيمة
            {"datetime": "2026-04-01", "mean": 0.55, "cloud_pct": None},  # سحاب غير مقيس
            _pt("2026-05-01", 0.58, cloud=10),
        ],
        field_id="f",
        tenant_id="t",
    )
    assert out["observations_used"] == 2
    assert out["from"]["mean"] == 0.40
    assert out["to"]["mean"] == 0.58


def test_since_filter_and_insufficient_raises() -> None:
    pts = [_pt("2026-01-01", 0.30), _pt("2026-05-01", 0.60)]
    # since يُبقي مشاهدةً واحدةً ⇒ لا مقارنة ⇒ يرفع (يُترجَم إلى 424 على الحافّة).
    with pytest.raises(InsufficientObservations):
        summarize_field_change(pts, field_id="f", tenant_id="t", since="2026-04-01")
    # بلا مشاهدات ⇒ يرفع أيضاً (لا مقارنة مُلفّقة).
    with pytest.raises(InsufficientObservations):
        summarize_field_change([], field_id="f", tenant_id="t")


def test_no_agronomic_interpretation_only_measurement() -> None:
    out = summarize_field_change(
        [_pt("2026-03-01", 0.40), _pt("2026-05-01", 0.60)], field_id="f", tenant_id="t"
    )
    # delta قياسٌ فقط — لا مفاتيح توصية/تفسير زراعيّ.
    for forbidden in ("recommendation", "advice", "irrigation", "cause", "diagnosis"):
        assert forbidden not in out
    assert MAX_CLOUD_PCT == 30.0


def test_mcp_tool_registered_and_read_only() -> None:
    """ساكن: الأداة مسجّلة في MCP وتبقى قراءة-فقط (لا كتابة/تنفيذ)."""
    src = MCP.read_text(encoding="utf-8")
    assert '"name": "analyze_field_change"' in src
    assert "summarize_field_change" in src
    # قراءة-فقط: نطاق satellite:read، ولا تنفيذ فعل داخل MCP (لا write/approve).
    assert 'require_scope("satellite:read")' in src
    assert "satellite:write" not in src
    # لا حساب طيفيّ في MCP — يقرأ نقطة raster-service القانونيّة.
    assert "/v1/fields/{field_id}/timeseries" in src
