"""حقن سلسلة GDD من المحرّك في محاكاة الموسم (WS-C.1c Zero-Legacy) — لا نواة محلّيّة.

يُثبِت: السلسلة المحقونة الكنسيّة تقود التراكم الحراريّ فعلاً · يوم None يُستبعَد (لا يُلفَّق،
لا عودة لنواة gdd_day محلّيّة) · غياب السلسلة كلّها ⇒ تراكم صفر (fail-closed، المحرّك مصدر
GDD الوحيد) · crop_gdd_policy يعيد عتبات النموذج (تُمرَّر للمحرّك).
"""

from __future__ import annotations

from api.season_simulation import (
    DayWeather,
    SimContext,
    crop_gdd_policy,
    simulate_season,
)


def _weather(n=30):
    return [DayWeather(t_min_c=14.0 + (i % 5), t_max_c=30.0 + (i % 5)) for i in range(n)]


def test_policy_getter_returns_model_thresholds():
    base, cutoff = crop_gdd_policy("wheat")
    # عتبات النموذج (تُمرَّر للمحرّك بـmethod="modified") — أساس ≤ سقف.
    assert isinstance(base, float) and isinstance(cutoff, float)
    assert base <= cutoff


def test_injected_series_drives_gdd_total():
    weather = _weather(20)
    # سلسلة GDD موجبة محقونة ⇒ تراكم موجب (تُثبِت أنّ الحقن يقود الحساب فعلاً).
    injected = [12.0] * len(weather)
    out = simulate_season(SimContext(crop="wheat", weather=weather, gdd_daily_override=injected))
    assert abs(out.gdd_total - 12.0 * len(weather)) < 1e-6


def test_zeros_injected_yield_zero_gdd():
    weather = _weather(10)
    zeros = [0.0] * len(weather)
    out = simulate_season(SimContext(crop="wheat", weather=weather, gdd_daily_override=zeros))
    assert out.gdd_total == 0.0


def test_none_day_excluded_not_fabricated():
    weather = _weather(5)
    # يوم None في السلسلة ⇒ يُستبعَد من التراكم (لا عودة لنواة محلّيّة، لا صفر مُلفَّق فوق البقيّة).
    injected = [10.0, None, 10.0, 10.0, 10.0]
    out = simulate_season(SimContext(crop="wheat", weather=weather, gdd_daily_override=injected))
    assert abs(out.gdd_total - 40.0) < 1e-6  # 4 أيّام × 10، اليوم None مُستبعَد


def test_no_override_yields_zero_gdd_no_local_kernel():
    # لا سلسلة محقونة ⇒ تراكم GDD = 0 (لا نواة gdd_day محلّيّة تملأ الفراغ). fail-closed.
    weather = _weather(15)
    out = simulate_season(SimContext(crop="wheat", weather=weather))
    assert out.gdd_total == 0.0
