"""اختبار جاهزيّة البيانات — تلميح الدقّة لا ينقلب فارغاً عند أعلى المستويات."""

from api.data_readiness import assess_readiness


def test_high_level_data_gets_top_accuracy_hint_not_blank():
    # بيانات حتى المستوى 6 (مجسّات) كانت تُرجِع تلميح دقّة فارغاً (عكسيّ: أكثر بيانات
    # ⇒ تلميح أسوأ). الآن تأخذ أعلى تلميح مُعرَّف (٩٠٪+).
    provided = [
        "location",
        "area_ha",
        "crop",
        "season",
        "planting_date",
        "irrigation",  # L1
        "t_min",
        "t_max",
        "rain",  # L2
        "soil_texture",
        "ph",
        "ec",  # L3
        "ndvi",  # L4
        "n_ppm",
        "p_ppm",
        "k_ppm",
        "fe_ppm",
        "zn_ppm",  # L5
        "soil_moisture",  # L6
    ]
    r = assess_readiness(provided)
    assert r.highest_complete_level >= 5
    assert r.accuracy_hint_ar  # غير فارغ
    assert "٩٠" in r.accuracy_hint_ar  # تلميح أعلى دقّة، لا ""
