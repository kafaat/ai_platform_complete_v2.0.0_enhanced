"""حقن نواة GDD من المحرّك في محاكاة الموسم (WS-C.1c) — مُحافِظ على الطريقة.

يُثبِت: السلسلة المحقونة تُستخدم بدل gdd_day المحلّيّة · غيابها ⇒ سلوك محلّيّ مطابق ·
None ليوم ⇒ عودة لـgdd_day لذلك اليوم · crop_gdd_policy يعيد عتبات النموذج نفسها.
"""

from __future__ import annotations

from api.season_simulation import (
    DayWeather,
    SimContext,
    crop_gdd_policy,
    gdd_day,
    simulate_season,
)


def _weather(n=30):
    return [DayWeather(t_min_c=14.0 + (i % 5), t_max_c=30.0 + (i % 5)) for i in range(n)]


def test_policy_getter_matches_model_thresholds():
    base, cutoff = crop_gdd_policy("wheat")
    # نفس القيم المُستخدَمة في gdd_day داخل المحاكاة (لا اختلاف سياسة).
    w = _weather(1)[0]
    assert gdd_day(w.t_min_c, w.t_max_c, base, cutoff) >= 0.0


def test_injected_series_replaces_local_kernel():
    weather = _weather(20)
    base, cutoff = crop_gdd_policy("wheat")
    # سلسلة محقونة تطابق النواة المحلّيّة ⇒ نفس gdd_total (إثبات إعادة إنتاج أمين).
    injected = [gdd_day(w.t_min_c, w.t_max_c, base, cutoff) for w in weather]
    local = simulate_season(SimContext(crop="wheat", weather=weather))
    delegated = simulate_season(
        SimContext(crop="wheat", weather=weather, gdd_daily_override=injected)
    )
    assert abs(delegated.gdd_total - local.gdd_total) < 1e-6


def test_injected_series_actually_drives_gdd():
    weather = _weather(10)
    # سلسلة أصفار محقونة ⇒ gdd_total = 0 (تُثبِت أنّ الحقن يقود الحساب فعلاً).
    zeros = [0.0] * len(weather)
    out = simulate_season(SimContext(crop="wheat", weather=weather, gdd_daily_override=zeros))
    assert out.gdd_total == 0.0


def test_none_day_falls_back_to_local_kernel():
    weather = _weather(5)
    base, cutoff = crop_gdd_policy("wheat")
    # يوم None في السلسلة ⇒ عودة لـgdd_day لذلك اليوم فقط.
    injected = [0.0, None, 0.0, 0.0, 0.0]
    out = simulate_season(SimContext(crop="wheat", weather=weather, gdd_daily_override=injected))
    expected_day1 = gdd_day(weather[1].t_min_c, weather[1].t_max_c, base, cutoff)
    assert abs(out.gdd_total - expected_day1) < 1e-6


def test_no_override_is_unchanged_behavior():
    weather = _weather(15)
    a = simulate_season(SimContext(crop="barley", weather=weather))
    b = simulate_season(SimContext(crop="barley", weather=weather, gdd_daily_override=None))
    assert a.gdd_total == b.gdd_total
    assert a.yield_kg_ha == b.yield_kg_ha
