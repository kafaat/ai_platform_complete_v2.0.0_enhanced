"""DECISION-CENTER Composer — المُحلِّل الطيفيّ الخادميّ (شريحة server-authoritative).

اختبار وحدة (بلا شبكة/قاعدة): يستدعي ``_compose_state`` مباشرةً ويؤكّد:
  (أ) الراية معطَّلة ⇒ طيف العميل مُستخدَم، provenance=client (سلوك بلا تغيير)؛
  (ب) الراية مُفعَّلة + جلب خادميّ ناجح ⇒ NDVI الخادميّ يتجاوز قيمة العميل،
      provenance=raster-service؛
  (ج) الراية مُفعَّلة + فشل الجلب ⇒ طيف العميل مُستخدَم مع تعليم
      ``client_supplied_spectral_unverified`` (شفافيّة، لا اختلاق سلطة).
"""

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه (تفادي دورة استيراد)
import pytest
from api.routers import crop_twin as ct
from api.routers.crop_twin import ComposeForecastDay, CropTwinComposeRequest, _compose_state

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_engine_gdd(monkeypatch):
    """يجلب المسار GDD من المحرّك (async) — نُبدِّله بمزيّف محلّيّ (لا شبكة)."""

    async def _fake_gdd(*, daily_t_min, daily_t_max, base_c, upper_cutoff_c, method, **_kw):
        daily = [
            max(0.0, ((mn + mx) / 2) - base_c)
            for mn, mx in zip(daily_t_min, daily_t_max, strict=False)
        ]
        return {"daily_gdd": daily, "cumulative_gdd": sum(daily), "method": method}

    monkeypatch.setattr(ct, "get_gdd_product", _fake_gdd)


def _req(ndvi=0.30):
    return CropTwinComposeRequest(
        field_id="fld_1",
        crop="wheat",
        stage="mid",
        ndvi=ndvi,
        forecast=[ComposeForecastDay(t_min_c=12.0, t_max_c=28.0, et0_mm=5.0)],
    )


async def test_flag_off_uses_client_spectral(monkeypatch):
    monkeypatch.setattr(ct, "compose_server_authoritative_spectral_enabled", lambda: False)
    st = await _compose_state(_req(ndvi=0.30), tenant_id="t1")
    assert st["spectral_provenance"] == "client"
    assert st["spectral_unverified"] is False


@pytest.mark.parametrize("quality, status", [("validated", "available"), ("unknown", "degraded")])
async def test_flag_on_server_overrides_client(monkeypatch, quality, status):
    monkeypatch.setattr(ct, "compose_server_authoritative_spectral_enabled", lambda: True)

    calls = []

    async def _fake_grid(field_id, *, tenant_id, index, date, timeout_s):
        calls.append((field_id, tenant_id, index, date, timeout_s))
        if index != "ndvi":
            raise RuntimeError("no product for this index")
        return {
            "field_id": "fld_1",
            "tenant_id": "t1",
            "real_data": True,
            "source": "cdse",
            "stats": {"mean": 0.72},
            "quality_status": quality,
            "date": "2026-05-01",
            "scene_id": "S2_ABC",
        }

    # Exercise the canonical resolver and composer; replace only the external transport.
    monkeypatch.setattr("api.raster_service_client.get_indicator_grid", _fake_grid)
    # client sent 0.30; server authoritative 0.72 must win.
    st = await _compose_state(_req(ndvi=0.30), tenant_id="t1")
    assert st["spectral_provenance"] == "raster-service"
    assert st["spectral_unverified"] is False
    assert sorted(calls) == [
        ("fld_1", "t1", index, "latest", 20.0) for index in ("msi", "ndmi", "ndre", "ndvi")
    ]
    spectral = st["twin"]["crop_intelligence"]["spectral"]
    assert spectral["indices"] == {"ndvi": 0.72, "ndre": None, "ndmi": None, "msi": None}
    assert spectral["evidence_ids"] == ["S2_ABC"]
    assert spectral["source_authority"] == "raster-service"
    assert spectral["quality_status"] == quality
    assert spectral["status"] == status
    assert spectral["water_stress"]["confirmation_available"] is False
    # الطيف الخادميّ يقود Kc الديناميكيّ (قيمة أعلى من 0.30 ⇒ Kc أعلى).
    st_client = None
    monkeypatch.setattr(ct, "compose_server_authoritative_spectral_enabled", lambda: False)
    st_client = await _compose_state(_req(ndvi=0.30), tenant_id="t1")
    assert st["dyn_kc"] != st_client["dyn_kc"]  # مصدر NDVI مختلف ⇒ Kc مختلف


async def test_flag_on_fetch_fails_marks_client_unverified(monkeypatch):
    monkeypatch.setattr(ct, "compose_server_authoritative_spectral_enabled", lambda: True)

    calls = []

    async def _fail_grid(field_id, *, tenant_id, index, date, timeout_s):
        calls.append((field_id, tenant_id, index))
        raise TimeoutError("raster unavailable")

    monkeypatch.setattr("api.raster_service_client.get_indicator_grid", _fail_grid)
    st = await _compose_state(_req(ndvi=0.30), tenant_id="t1")
    assert st["spectral_provenance"] == "client"
    assert st["spectral_unverified"] is True
    assert sorted(calls) == [("fld_1", "t1", index) for index in ("msi", "ndmi", "ndre", "ndvi")]
    spectral = st["twin"]["crop_intelligence"]["spectral"]
    assert spectral["indices"]["ndvi"] == 0.30
    assert spectral["evidence_ids"] == []
    assert spectral["source_authority"] is None
    assert spectral["quality_status"] == "unknown"
    assert spectral["status"] == "degraded"
    assert spectral["water_stress"]["confirmation_available"] is False


async def test_flag_on_no_field_id_keeps_client(monkeypatch):
    monkeypatch.setattr(ct, "compose_server_authoritative_spectral_enabled", lambda: True)
    req = _req(ndvi=0.30)
    req.field_id = None  # لا حقل حقيقيّ ⇒ لا محاولة خادميّة (معاينة ad-hoc)
    st = await _compose_state(req, tenant_id="t1")
    assert st["spectral_provenance"] == "client"
    assert st["spectral_unverified"] is False
