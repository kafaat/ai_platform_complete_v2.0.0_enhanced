"""تحقّق V66 — نشرة حالة المحاصيل الإقليميّة (تجميع حقل→مديريّة→محافظة، آمن الخصوصيّة).

- تصنيف GEOGLAM: exceptional/favourable/watch/poor من شذوذ NDVI؛ بلا تاريخ ⇒ unknown.
- أرضيّة خصوصيّة (k-anonymity): مجموعة < العتبة تُكتَم بلا أرقام (suppressed_for_privacy).
- لا معرّفات حقول في المخرَج؛ التجميع من المُمرَّر فقط.
- الشذوذ من ``ndvi_anomaly`` أو (الحاليّ − المتوسّط التاريخيّ).

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

from core.regional_bulletin import (
    build_regional_bulletin,
    bulletin_rows_to_records,
    classify_condition,
    effective_privacy_floor,
)

_TH = {"exceptional": 0.08, "favourable": -0.05, "watch": -0.15}


def _fields(gov: str, dist: str, n: int, anomaly: float, tenant: str = "t1") -> list[dict]:
    return [
        {
            "governorate": gov,
            "district": dist,
            "tenant_id": tenant,
            "ndvi_anomaly": anomaly,
            "scene_count": 6,
            "field_id": f"{dist}-{i}",
        }
        for i in range(n)
    ]


def test_classify_condition_bands():
    assert classify_condition(0.12, _TH) == "exceptional"
    assert classify_condition(0.00, _TH) == "favourable"
    assert classify_condition(-0.10, _TH) == "watch"
    assert classify_condition(-0.20, _TH) == "poor"
    assert classify_condition(None, _TH) == "unknown"  # لا تخمين


def test_privacy_floor_suppresses_small_groups():
    # مجموعة من 3 حقول < العتبة 5 ⇒ مكتومة بلا أرقام.
    bulletin = build_regional_bulletin(_fields("Sanaa", "Bani Matar", 3, 0.1))
    gov = bulletin["governorates"][0]
    assert gov["status"] == "suppressed_for_privacy"
    assert "mean_ndvi_anomaly" not in gov  # لا أرقام مُسرَّبة
    # RFC R3 DS-R02: the count and the floor were still returned on a suppressed group.
    assert "field_count" not in gov
    assert "5" not in gov["reason"]
    assert bulletin["suppressed_governorates"] == 1


def test_published_group_has_condition_and_no_field_ids():
    bulletin = build_regional_bulletin(_fields("Sanaa", "Bani Matar", 8, 0.12))
    gov = bulletin["governorates"][0]
    assert gov["status"] == "published"
    assert gov["condition"] == "exceptional"
    assert gov["field_count"] == 8
    # لا معرّفات حقول في المخرَج (تجميعيّ فقط).
    import json

    assert "Bani Matar-0" not in json.dumps(bulletin, ensure_ascii=False)


def test_anomaly_from_current_minus_historical():
    fields = [
        {
            "governorate": "Ibb",
            "district": "Jiblah",
            "tenant_id": "t1",
            "ndvi_current": 0.30,
            "ndvi_historical_mean": 0.50,  # شذوذ −0.20 ⇒ poor
            "scene_count": 5,
        }
        for _ in range(6)
    ]
    gov = build_regional_bulletin(fields)["governorates"][0]
    assert gov["condition"] == "poor"
    assert gov["mean_ndvi_anomaly"] == -0.20


def test_distribution_and_no_tenant_count():
    """``tenant_count`` is gone: RLS makes it 1 for every caller, and it would identify a
    single tenant if the bulletin were ever aggregated across tenants."""
    fields = _fields("Taiz", "Sabir", 4, 0.1, tenant="t1") + _fields(
        "Taiz", "Sabir", 4, -0.2, tenant="t2"
    )
    gov = build_regional_bulletin(fields)["governorates"][0]
    assert gov["status"] == "published"
    assert "tenant_count" not in gov
    dist = gov["condition_distribution"]
    assert dist["exceptional"] == 4 and dist["poor"] == 4


def test_district_rollup_suppresses_a_neighbour_so_subtraction_reveals_nothing():
    """RFC R3 DS-R02: governorate 8 fields, district A 6 published, district B 2 suppressed.
    Publishing A would give B by subtraction (count 2, both 'poor'), so A is suppressed too."""
    fields = _fields("Dhamar", "A", 6, 0.1) + _fields("Dhamar", "B", 2, -0.2)
    gov = build_regional_bulletin(fields)["governorates"][0]
    assert gov["status"] == "published" and gov["field_count"] == 8
    districts = {d["district"]: d for d in gov["districts"]}
    assert districts["B"]["status"] == "suppressed_for_privacy"  # 2 < 5
    assert districts["A"]["status"] == "suppressed_for_privacy"  # complementary
    for d in gov["districts"]:
        assert set(d) == {"district", "status", "reason"}, d  # no number of any kind


def test_neighbour_stays_published_when_the_suppressed_together_reach_the_floor():
    fields = (
        _fields("Dhamar", "A", 6, 0.1)
        + _fields("Dhamar", "B", 3, -0.2)
        + _fields("Dhamar", "C", 3, -0.2)
    )
    districts = {
        d["district"]: d for d in build_regional_bulletin(fields)["governorates"][0]["districts"]
    }
    # B and C are suppressed (3 < 5 each) but together hold 6 >= 5: subtraction gives only the
    # pair's combined figure, which is itself above the floor, so A can be published.
    assert districts["A"]["status"] == "published"
    assert districts["B"]["status"] == districts["C"]["status"] == "suppressed_for_privacy"


def test_total_minus_published_governorates_reveals_nothing():
    fields = _fields("Sanaa", "X", 9, 0.1) + _fields("Ibb", "Y", 2, -0.2)
    b = build_regional_bulletin(fields)
    govs = {g["governorate"]: g for g in b["governorates"]}
    assert govs["Ibb"]["status"] == "suppressed_for_privacy"
    # total_fields (11) − Sanaa (9) would give Ibb's 2, so Sanaa is suppressed with it.
    assert govs["Sanaa"]["status"] == "suppressed_for_privacy"
    assert govs["Sanaa"]["districts"] == []
    assert b["published_governorates"] == 0


def test_fields_without_a_district_are_not_published_as_a_district_called_unknown():
    """RFC R3 DS-R04: the bulletin query selects no district, so every field used to land in a
    district named "unknown" that looked like a real place."""
    rows = [{"field_id": f"f{i}", "gov": "Taiz", "ndvi_anomaly": 0.1} for i in range(6)]
    gov = build_regional_bulletin(bulletin_rows_to_records(rows))["governorates"][0]
    assert gov["status"] == "published"
    assert gov["districts"] == []
    assert gov["district_breakdown"] == "unavailable_no_district_mapping"
    assert "unknown" not in {d.get("district") for d in gov["districts"]}


def test_unmapped_remainder_is_its_own_group_under_the_floor():
    fields = _fields("Lahj", "A", 6, 0.1) + [
        {"governorate": "Lahj", "district": None, "ndvi_anomaly": -0.2} for _ in range(2)
    ]
    districts = build_regional_bulletin(fields)["governorates"][0]["districts"]
    unmapped = [d for d in districts if d.get("unmapped")]
    assert unmapped and unmapped[0]["status"] == "suppressed_for_privacy"
    # Otherwise the governorate minus A would reveal the two unmapped fields.
    assert {d["district"]: d for d in districts}["A"]["status"] == "suppressed_for_privacy"


def test_empty_and_malformed_inputs():
    b = build_regional_bulletin([])
    assert b["governorates"] == []
    # Below the floor even the overall total is withheld.
    assert b["total_fields"] is None
    # سجلّات بلا محافظة تُهمَل (لا تُجمَّع).
    b2 = build_regional_bulletin([{"district": "x", "ndvi_anomaly": 0.1}])
    assert b2["total_fields"] is None and b2["governorates"] == []


def test_privacy_floor_can_be_raised_but_never_lowered():
    """RFC R3 DS-R01: the floor used to be whatever the caller sent, down to 1."""
    low = build_regional_bulletin(_fields("Hajjah", "Kuhlan", 3, 0.1), min_fields_privacy=3)
    assert low["governorates"][0]["status"] == "suppressed_for_privacy"
    assert low["privacy_floor_fields"] == 5
    for bad in (1, 0, -4, None, "x", True):
        assert effective_privacy_floor(bad) == 5
    high = build_regional_bulletin(_fields("Hajjah", "Kuhlan", 8, 0.1), min_fields_privacy=10)
    assert high["governorates"][0]["status"] == "suppressed_for_privacy"
    assert high["privacy_floor_fields"] == 10


def test_period_is_reported_as_a_label_not_a_filter():
    """RFC R3 DS-R03: ``period`` never filtered the NDVI scenes; the bulletin now says so."""
    b = build_regional_bulletin(_fields("Taiz", "Sabir", 6, 0.1), period="2026-10")
    assert b["period"] == "2026-10" and b["period_applied_as_filter"] is False
