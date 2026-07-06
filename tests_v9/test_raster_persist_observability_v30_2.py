"""حارس: رصد حفظ raster_assets + ملخّص فحص backfill (تدقيق السجلّ الحيّ v5).

- F1: «job completed» وحده كان لا يُميّز الحفظ في DB عن الذاكرة فقط. الآن
  `_persist_raster_asset` يُرجِع bool ويُصدِر سطراً منظَّماً، و`persisted` في نتيجة المهمّة.
- F8: ملخّص فحص backfill منظَّم يكشف نطاق الفحص (أشهر/مشاهد/مهامّ).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
RASTER_MAIN = REPO / "services" / "raster-service" / "main.py"
# التفكيك (phase-4): تنفيذ الحفظ انتقل إلى raster_asset_persistence.py
# (الدالّة العامّة persist_raster_asset، وله اسم خاصّ مُعاد تصديره _persist_raster_asset)،
# وتجميع نتيجة المهمّة (persisted) إلى raster_job_orchestration.py. main يعيد تصديرها فقط.
RASTER_PERSIST = REPO / "services" / "raster-service" / "raster_asset_persistence.py"
RASTER_JOBS = REPO / "services" / "raster-service" / "raster_job_orchestration.py"
FIELDS = REPO / "services" / "raster-service" / "routers" / "fields.py"


def test_persist_emits_structured_result_and_returns_bool() -> None:
    src = RASTER_PERSIST.read_text(encoding="utf-8")
    joined = " ".join(src.split())
    # التوقيع يُرجِع bool (لا None) — الدالّة نفسها بعد التفكيك اسمها persist_raster_asset،
    # ويبقى الاسم الخاصّ _persist_raster_asset مُعاد تصديره للتوافق الخلفيّ.
    assert "def persist_raster_asset(" in src
    assert "_persist_raster_asset = persist_raster_asset" in src, (
        "الاسم الخاصّ يجب أن يبقى مُعاد تصديره للتوافق الخلفيّ"
    )
    assert ") -> bool:" in joined.split("def persist_raster_asset(")[1][:400]
    # سطر نجاح/فشل منظَّم يجيب سؤال «هل حُفِظ في DB؟».
    assert "raster_assets persist ok field_id=" in src
    assert "raster_assets persist failed field_id=" in src


def test_job_result_carries_persisted_flag() -> None:
    src = RASTER_JOBS.read_text(encoding="utf-8")
    joined = " ".join(src.split())
    assert '"persisted": persisted' in joined, "نتيجة المهمّة يجب أن تحمل persisted"
    assert "persisted={persisted}" in src, "سطر completed يجب أن يذكر persisted"


def test_backfill_scan_summary_logged() -> None:
    src = FIELDS.read_text(encoding="utf-8")
    assert "historical_backfill_scan completed field_id=" in src, "ملخّص فحص backfill غائب"
    for token in ("months_scanned=", "scenes_selected=", "jobs_scheduled="):
        assert token in src, f"ملخّص الفحص يفتقد {token}"
