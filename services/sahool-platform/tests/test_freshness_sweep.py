"""اختبارات وحدة لفحص نضارة القرار الدوريّ (freshness sweep).

يغطّي الجزء النقيّ ``compute_data_ages`` (تحويل epoch → أيّام/ساعات، تمرير None،
تثبيت السالب)، وعقد التوصيل: أنّ ``_freshness_sweep`` لم يعُد يستخدم أصفاراً
مُلفَّقة بل يقرأ أعماراً فعليّة ويسجّلها عبر LEDGER. الجزء المُستعلِم من القاعدة
يعمل في النشر الحيّ فقط (integration) — هنا نفحص الوصلة عبر inspect.getsource.
"""

import inspect

import pytest
from api.agronomic_consistency import check_decision_freshness, compute_data_ages

pytestmark = pytest.mark.unit

_DAY = 86400.0
_HOUR = 3600.0
_NOW = 1_700_000_000.0


# ─── compute_data_ages: المنطق النقيّ ──────────────────────────────────────


def test_fresh_ages_below_thresholds():
    ages = compute_data_ages(
        _NOW,
        ndvi_at_epoch=_NOW - 1 * _DAY,  # يوم واحد
        soil_at_epoch=_NOW - 1 * _HOUR,  # ساعة واحدة
        weather_at_epoch=_NOW - 1 * _HOUR,
    )
    assert ages["ndvi_age_days"] == pytest.approx(1.0)
    assert ages["soil_age_days"] == pytest.approx(1.0 / 24.0)
    assert ages["weather_age_hours"] == pytest.approx(1.0)
    # طازج ⇒ لا تناقضات
    assert check_decision_freshness(**ages).consistent is True


def test_stale_ages_above_thresholds_flag_conflicts():
    ages = compute_data_ages(
        _NOW,
        ndvi_at_epoch=_NOW - 10 * _DAY,  # 10 أيّام > 5
        soil_at_epoch=_NOW - 4 * _DAY,  # 4 أيّام > 2
        weather_at_epoch=_NOW - 12 * _HOUR,  # 12 ساعة > 6
    )
    assert ages["ndvi_age_days"] == pytest.approx(10.0)
    assert ages["soil_age_days"] == pytest.approx(4.0)
    assert ages["weather_age_hours"] == pytest.approx(12.0)
    result = check_decision_freshness(**ages)
    assert result.consistent is False
    ids = {c.rule_id for c in result.conflicts}
    assert ids == {"stale_ndvi", "stale_soil", "stale_weather"}


def test_none_passes_through():
    ages = compute_data_ages(_NOW, ndvi_at_epoch=None, soil_at_epoch=None, weather_at_epoch=None)
    assert ages == {
        "ndvi_age_days": None,
        "soil_age_days": None,
        "weather_age_hours": None,
    }
    # كلّ المصادر None ⇒ الفحص يتخطّى كلّ شيء (لا قواعد مفحوصة، لا تناقض)
    result = check_decision_freshness(**ages)
    assert result.consistent is True
    assert result.checked_rules == 0


def test_partial_none_only_checks_available():
    ages = compute_data_ages(
        _NOW,
        ndvi_at_epoch=_NOW - 10 * _DAY,
        soil_at_epoch=None,  # لا تربة متاحة
        weather_at_epoch=None,  # لا طقس متاح
    )
    assert ages["ndvi_age_days"] == pytest.approx(10.0)
    assert ages["soil_age_days"] is None
    assert ages["weather_age_hours"] is None
    result = check_decision_freshness(**ages)
    assert result.checked_rules == 1  # NDVI فقط
    assert {c.rule_id for c in result.conflicts} == {"stale_ndvi"}


def test_negative_age_clamped_to_zero():
    # طابع في المستقبل (انحراف ساعة) ⇒ عمر سالب يُثبَّت عند 0 لا يُخترَع.
    ages = compute_data_ages(
        _NOW,
        ndvi_at_epoch=_NOW + 5 * _DAY,
        soil_at_epoch=_NOW + 3 * _HOUR,
        weather_at_epoch=_NOW + 2 * _HOUR,
    )
    assert ages["ndvi_age_days"] == 0.0
    assert ages["soil_age_days"] == 0.0
    assert ages["weather_age_hours"] == 0.0


def test_epoch_conversion_exact():
    # دقّة التحويل: 5 أيّام = 5، 6 ساعات = 6.
    ages = compute_data_ages(
        _NOW,
        ndvi_at_epoch=_NOW - 5 * _DAY,
        soil_at_epoch=_NOW - 2 * _DAY,
        weather_at_epoch=_NOW - 6 * _HOUR,
    )
    assert ages["ndvi_age_days"] == pytest.approx(5.0)
    assert ages["soil_age_days"] == pytest.approx(2.0)
    assert ages["weather_age_hours"] == pytest.approx(6.0)
    # عند العتبة بالضبط ⇒ ليس قديماً (الفحص: > لا ≥)
    assert check_decision_freshness(**ages).consistent is True


# ─── عقد التوصيل: _freshness_sweep لم يعُد خاملاً ───────────────────────────


def _sweep_source() -> str:
    import api.main as main_mod

    # _freshness_sweep دالّة داخليّة في _start_scheduler — افحص مصدر المُحيط.
    src = inspect.getsource(main_mod._start_scheduler)
    assert "_freshness_sweep" in src
    # اقتطع جسم _freshness_sweep فقط
    start = src.index("async def _freshness_sweep")
    nxt = src.index("async def _weather_sweep")
    return src[start:nxt]


def test_freshness_sweep_no_longer_hardcodes_zeros():
    body = _sweep_source()
    assert "ndvi_age_days=0" not in body
    assert "soil_age_days=0" not in body
    assert "weather_age_hours=0" not in body


def test_freshness_sweep_wires_real_pipeline():
    body = _sweep_source()
    assert "compute_data_ages(" in body
    assert "check_decision_freshness(" in body
    # يستخدم سجلّ الأتمتة (LEDGER) بنفس نمط _alerts_sweep
    assert "LEDGER.start_run(" in body
    assert "mark_evaluated()" in body
    assert "mark_errored(" in body
    assert ".finish()" in body
    # يقرأ أعماراً فعليّة (لا None ثابتة فقط) ويتعامل مع غياب البيانات
    assert "_DB_POOL" in body


def test_freshness_sweep_reads_real_sources():
    body = _sweep_source()
    # المصادر الفعليّة: NDVI + رطوبة التربة + الطقس
    assert "last_ndvi_date" in body
    assert "_latest_soil_moisture" in body
    assert "weather_automation_cache" in body
