"""WATER-LEDGER-AUTO — منطق التراكم اليوميّ النقيّ (FAO-56) بلا قاعدة.

يثبت: التراكم Dr_t = clamp(Dr_prev + ETc − P_eff − I, 0, TAW)، والافتراضات
المُعلَنة (bootstrap / قصّ قيد سابق شاذّ / ريّ غير مُقاس / سقف TAW)، وسيادة
القيد اليدويّ، ورفض المدخلات الفاسدة.
"""

from __future__ import annotations

import pytest
from api.water_balance import _effective_rain
from api.water_ledger_auto import (
    AUTO_CREATED_BY,
    CONFIDENCE_AUTO,
    CONFIDENCE_BOOTSTRAP,
    compute_daily_ledger_entry,
    manual_entry_takes_precedence,
)


def test_daily_accumulation_matches_fao56_identity():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=40.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=6.0,
        kc=1.15,
        rain_mm=2.0,
        irrigation_mm=10.0,
    )
    etc = round(1.15 * 6.0, 2)
    expected = 40.0 + etc - _effective_rain(2.0) - 10.0
    assert entry["etc_mm"] == etc
    assert entry["depletion_mm"] == round(expected, 2)
    assert entry["bootstrap"] is False
    assert entry["confidence"] == CONFIDENCE_AUTO
    assert entry["notes"] == []
    assert entry["decision"] == "auto:daily_balance"


def test_bootstrap_is_declared_with_lower_confidence():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=None,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert entry["bootstrap"] is True
    assert entry["confidence"] == CONFIDENCE_BOOTSTRAP
    assert "bootstrap_assumed_field_capacity" in entry["notes"]
    # اليوم الأوّل من Dr=0: الاستنزاف = ETc فقط.
    assert entry["depletion_mm"] == 5.0


def test_depletion_clamps_at_zero_and_taw_with_declared_flags():
    # ريّ غزير يدفع الحساب تحت الصفر ⇒ يُقصّ إلى 0 (لا استنزاف سالب).
    wet = compute_daily_ledger_entry(
        prev_depletion_mm=10.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=4.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=60.0,
    )
    assert wet["depletion_mm"] == 0.0
    assert wet["deficit_mm"] == 0.0

    # جفاف يتجاوز السعة ⇒ سقف TAW مع علم مُعلَن (إجهاد فوق المتاح لا يُخفى).
    dry = compute_daily_ledger_entry(
        prev_depletion_mm=118.0,
        taw_mm=120.0,
        raw_mm=60.0,
        et0_mm=8.0,
        kc=1.2,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert dry["depletion_mm"] == 120.0
    assert "depletion_capped_at_taw" in dry["notes"]
    assert dry["deficit_mm"] == 60.0


def test_out_of_range_previous_entry_is_clamped_and_declared():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=500.0,  # قيد يدويّ قديم شاذّ فوق TAW
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=0.0001,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
    )
    assert "previous_depletion_clamped" in entry["notes"]
    assert entry["depletion_mm"] <= 100.0


def test_untracked_irrigation_volume_is_flagged_not_fabricated():
    entry = compute_daily_ledger_entry(
        prev_depletion_mm=30.0,
        taw_mm=100.0,
        raw_mm=50.0,
        et0_mm=5.0,
        kc=1.0,
        rain_mm=0.0,
        irrigation_mm=0.0,
        irrigation_volume_untracked=True,
    )
    assert "irrigation_volume_untracked" in entry["notes"]
    assert "irrigation_volume_untracked" in entry["decision"]


def test_invalid_inputs_are_rejected_not_guessed():
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(
            prev_depletion_mm=0.0,
            taw_mm=0.0,
            raw_mm=0.0,
            et0_mm=5.0,
            kc=1.0,
            rain_mm=0.0,
            irrigation_mm=0.0,
        )
    with pytest.raises(ValueError):
        compute_daily_ledger_entry(
            prev_depletion_mm=0.0,
            taw_mm=100.0,
            raw_mm=50.0,
            et0_mm=-1.0,
            kc=1.0,
            rain_mm=0.0,
            irrigation_mm=0.0,
        )


def test_manual_entry_precedence():
    assert manual_entry_takes_precedence("haithm") is True
    assert manual_entry_takes_precedence(AUTO_CREATED_BY) is False
    assert manual_entry_takes_precedence(None) is False


def test_worker_kind_is_wired():
    """العامل مُسجَّل في phase_runtime_workers (kind + CLI) — حارس توصيل ساكن."""
    from pathlib import Path

    src = (Path(__file__).parents[1] / "api" / "phase_runtime_workers.py").read_text()
    assert "async def run_water_ledger_once" in src
    assert '"water_ledger": run_water_ledger_once' in src
    assert "WATER_LEDGER_AUTO_ENABLED" in src
    assert "manual_entry_takes_precedence" in src
    compose = (Path(__file__).parents[3] / "docker-compose.v9.yml").read_text()
    assert "sahool-water-ledger-worker:" in compose
    assert "- water_ledger" in compose
