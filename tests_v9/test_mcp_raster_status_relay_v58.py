"""حارس MCP — ترجمة خطأ raster-service إلى حالة صادقة بدل تسريب 500.

عطل كشفه التشغيل الحيّ: ``read_indicator_observation``/``analyze_field_change`` كانا يستدعيان
``resp.raise_for_status()`` ⇒ عند 424 من راستر (لا COG/مشاهدات) يُرفَع ``HTTPStatusError`` غير
مُلتقَط ⇒ FastAPI يعيد **500** (يُلبِس fail-closed الصادق رمزاً مُضلِّلاً).

حارس ساكن (نمط اختبارات MCP في tests_v9 — تفادي تصادم حزمة ``shared`` عند استيراد خادم MCP
كاملاً): يؤكّد أنّ ``_relay_raster_status`` يُبقي الدلالة، وأنّ مساري القراءة من راستر يستخدمانه
بدل ``raise_for_status`` العاري.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services" / "mcp_servers" / "sentinel_hub_server.py"


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_relay_helper_defined_with_honest_mapping():
    s = _src()
    assert "def _relay_raster_status(" in s
    # 424 من راستر ⇒ 424 (لا مشاهدة موثوقة) لا 500.
    assert "if code == 424:" in s
    assert "HTTPException(424, detail=" in s
    # 404 ⇒ 404 · بقيّة 4xx ⇒ 422 · 5xx/غيرها ⇒ 502 (خطأ منبع).
    assert "if code == 404:" in s
    assert "HTTPException(404, detail=" in s
    assert "HTTPException(422, detail=" in s
    assert "HTTPException(502, detail=" in s
    # النجاح يمرّ صامتاً (2xx ⇒ لا رفع).
    assert "if resp.is_success:" in s


def test_raster_reads_use_relay_not_bare_raise_for_status():
    s = _src()
    # مسارا indicator-grid (read_indicator_observation) وtimeseries (analyze_field_change)
    # يستخدمان المُترجِم — نقطتان على الأقلّ.
    assert s.count("_relay_raster_status(resp)") >= 2


def test_read_indicator_and_timeseries_no_longer_leak_500():
    s = _src()
    # لا يُسبَق أيّ قراءة راستر بـraise_for_status العاري مباشرةً بعد نداء indicator/timeseries.
    for anchor in ("/indicator-grid", "/timeseries"):
        idx = s.find(anchor)
        assert idx != -1, f"مرجع راستر مفقود: {anchor}"
        window = s[idx : idx + 600]
        assert "_relay_raster_status(resp)" in window, f"{anchor} لا يستخدم المُترجِم"
