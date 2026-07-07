"""تحقّق — ذكاء اتّجاه الرياح المكانيّ (compass_16 · wind_rose · windbreak) منطق صرف.

- بوصلة 16 نقطة حتميّة + تسمية عربيّة؛ اصطلاح «الريح تأتي من».
- وردة رياح: سائد بمتّجه-متوسّط موزون بالسرعة؛ عيّنة صغيرة ⇒ prevailing=None (صدق).
- مصدّ الرياح: توجيه عموديّ على الريح + جهة الزرع upwind + حماية ~10H (لا رقم بلا ارتفاع).
"""

from __future__ import annotations

from core.wind_geometry import compass_16, wind_rose, windbreak_recommendation


def test_compass_16_cardinal_and_wrap():
    assert compass_16(0)["key"] == "N"
    assert compass_16(90)["key"] == "E"
    assert compass_16(315)["key"] == "NW" and "غربيّة" in compass_16(315)["label_ar"]
    # التفاف: 360 ≡ 0، والقيم السالبة تُطبَّع.
    assert compass_16(360)["key"] == "N"
    assert compass_16(-45)["key"] == "NW"
    assert compass_16("x") is None


def test_wind_rose_prevailing_from_speed_weighted_vector_mean():
    # أغلب الأرصاد شماليّة غربيّة (315) وأقوى ⇒ السائد قربها.
    obs = [
        (315, 8.0),
        (315, 7.0),
        (310, 6.0),
        (320, 5.0),
        (315, 9.0),
        (300, 4.0),
        (330, 3.0),
        (315, 8.0),
    ]
    rose = wind_rose(obs)
    assert rose["prevailing"]["key"] in {"NW", "WNW", "NNW"}
    assert rose["n"] == 8 and rose["sectors"].get("NW", 0) >= 3


def test_wind_rose_insufficient_sample_is_honest():
    # عيّنة أصغر من الحدّ ⇒ لا سائد موهوم (صدق).
    rose = wind_rose([90, 100, 80])
    assert rose["prevailing"] is None and rose["reason"] == "insufficient_observations"
    assert wind_rose(None)["prevailing"] is None


def test_windbreak_orientation_perpendicular_and_upwind_side():
    # ريح سائدة من الشمال الغربيّ (315) ⇒ المصدّ عموديّ (سَمت خطّ 45)، الزرع على الحافة NW.
    rec = windbreak_recommendation(315, tree_height_m=4.0)
    assert rec["status"] == "ok"
    assert rec["prevailing_from"]["key"] == "NW" and rec["wind_towards"]["key"] == "SE"
    assert rec["barrier_orientation_deg"] == 45.0  # (315+90) mod 180
    assert rec["plant_side"] == "NW"
    # الحماية ~10H downwind و3H upwind (ارتفاع 4م).
    assert rec["protected_downwind_m"] == 40.0 and rec["protected_upwind_m"] == 12.0


def test_windbreak_no_height_declares_need_not_fabricates():
    rec = windbreak_recommendation(90)  # ريح شرقيّة، بلا ارتفاع
    assert rec["status"] == "ok" and "protected_downwind_m" not in rec
    assert rec["protection_basis"].startswith("needs_tree_height")
    # بلا اتّجاه سائد ⇒ unknown صريح (لا توصية موهومة).
    assert windbreak_recommendation(None)["status"] == "unknown"
