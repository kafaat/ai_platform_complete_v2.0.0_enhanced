"""حارس عقد تلخيص مركز العمليّات (خادم ↔ واجهة) — نمط شاشة 大屏.

علّة مُثبَتة أُصلِحت: نوع ``OperationsSummary`` في الواجهة (`api.ts`) كان يعلن حقولاً
(`fields_total`/`decisions_total`/`valves_open`/`fleet`) **لا تطابق** ما يُرجِعه الخادم
فعلاً (`shape_operations_summary`: `totals.{fields,…}` / `alerts.by_severity` /
`irrigation.{valves,schedules}`)؛ فبقيت الأرقام المُجمَّعة الغنيّة مُهدَرة (تُستعمَل كعلَم
منطقيّ فقط). الإصلاح: توحيد النوع + شريط KPI بارز يقرأ الأرقام الحقيقيّة.

هذا الحارس (مسح ساكن، طبقة الوحدات) يمنع تكرار الانجراف بين الطرفين.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SHAPER = _ROOT / "services/sahool-platform/api/operations_summary.py"
_API_TS = _ROOT / "frontend/src/services/api.ts"
_WALL = _ROOT / "frontend/src/sections/OperationCenterWallPage.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_backend_shaper_emits_totals_alerts_irrigation():
    src = _read(_SHAPER)
    for key in ('"totals"', '"fields"', '"iot_devices"', '"decision_records"'):
        assert key in src, f"الخادم لا يُخرِج {key} في totals"
    assert '"by_severity"' in src, "الخادم لا يُخرِج alerts.by_severity"
    assert '"valves"' in src and '"schedules"' in src, "الخادم لا يُخرِج irrigation.valves/schedules"


def test_frontend_type_matches_backend_contract():
    src = _read(_API_TS)
    # النوع الموحّد الجديد يعلن العقد الحقيقيّ.
    assert "totals?:" in src, "OperationsSummary يفتقد totals (عقد الخادم)"
    assert "decision_records?:" in src and "iot_devices?:" in src
    assert "by_severity?:" in src, "OperationsSummary يفتقد alerts.by_severity"
    # الحقول القديمة المنجرفة أُزيلت (منع عودة الانجراف).
    assert "fields_total?:" not in src, "بقي الحقل المنجرف القديم fields_total"
    assert "valves_open?:" not in src, "بقي الحقل المنجرف القديم valves_open"


def test_wall_renders_kpi_strip_from_real_totals():
    src = _read(_WALL)
    assert "<KpiStrip summary={summary.data} />" in src, "الجدار لا يعرض شريط KPI"
    # الشريط يقرأ الأرقام الحقيقيّة + يحترم صدق التوفّر (sections status).
    assert "summary.totals" in src, "شريط KPI لا يقرأ totals الحقيقيّة"
    assert "sections" in src and "unavailable" in src, "شريط KPI لا يحترم صدق توفّر القسم"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
