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
    classify_condition,
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


def test_multi_tenant_and_distribution():
    fields = _fields("Taiz", "Sabir", 4, 0.1, tenant="t1") + _fields(
        "Taiz", "Sabir", 4, -0.2, tenant="t2"
    )
    gov = build_regional_bulletin(fields)["governorates"][0]
    assert gov["status"] == "published"
    assert gov["tenant_count"] == 2  # تجميع عبر مستأجرين (آمن الخصوصيّة)
    dist = gov["condition_distribution"]
    assert dist["exceptional"] == 4 and dist["poor"] == 4


def test_district_rollup_within_governorate():
    fields = _fields("Dhamar", "A", 6, 0.1) + _fields("Dhamar", "B", 2, -0.2)
    gov = build_regional_bulletin(fields)["governorates"][0]
    districts = {d["district"]: d for d in gov["districts"]}
    assert districts["A"]["status"] == "published"
    assert districts["B"]["status"] == "suppressed_for_privacy"  # 2 < 5


def test_empty_and_malformed_inputs():
    b = build_regional_bulletin([])
    assert b["total_fields"] == 0 and b["governorates"] == []
    # سجلّات بلا محافظة تُهمَل (لا تُجمَّع).
    b2 = build_regional_bulletin([{"district": "x", "ndvi_anomaly": 0.1}])
    assert b2["total_fields"] == 0


def test_configurable_privacy_floor():
    bulletin = build_regional_bulletin(_fields("Hajjah", "Kuhlan", 3, 0.1), min_fields_privacy=3)
    assert bulletin["governorates"][0]["status"] == "published"  # العتبة 3 ⇒ يُنشَر
    assert bulletin["privacy_floor_fields"] == 3
