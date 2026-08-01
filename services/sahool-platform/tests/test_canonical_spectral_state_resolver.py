"""عقد ``api/canonical_spectral_state.resolve_canonical_spectral_state`` (P0-2، نصف الطيف).

المُحلِّل يجيب سؤالاً واحداً: **ما الذي تعرفه المنصّة فعلاً عن طيف هذا الحقل الآن؟**
والجواب إمّا منتَج كنسيّ يقبله ``core/canonical_field_state.py``، أو ``None``.

الخطأ الذي تمنعه هذه الاختبارات ليس «قيمة خاطئة» بل **حضورٌ بلا معرفة**: منتَج مؤشّراته
كلّها ``None`` يرفع ``availability.spectral`` إلى ``True`` فتبدو الحالة أغنى ممّا هي.
الغياب المُعلَن أصدق من حضور فارغ.
"""

from __future__ import annotations

import pytest
from core.canonical_field_state import compose_canonical_field_state

pytestmark = pytest.mark.unit


def _grid(mean, *, real=True, source="cdse", date="2026-06-10", scene="S2_ABC"):
    return {
        "real_data": real,
        "source": source,
        "date": date,
        "scene_id": scene,
        "stats": {"mean": mean},
    }


def _patch_grid(monkeypatch, by_index):
    """يُرقِّع الواجهة القانونيّة الوحيدة لحدود raster-service، لا النقل تحتها."""
    from api import canonical_spectral_state as mod

    calls: list[str] = []

    async def _fake(field_id, *, tenant_id=None, index="ndvi", date="latest", timeout_s=20.0):
        calls.append(index)
        value = by_index.get(index)
        if value is None:
            raise RuntimeError(f"no product for {index}")
        return value

    monkeypatch.setattr("api.raster_service_client.get_indicator_grid", _fake)
    return mod, calls


@pytest.mark.asyncio
async def test_absent_master_index_yields_absence_not_an_empty_product(monkeypatch):
    """NDVI سيّد: غيابه ⇒ ``None``. منتَج بمؤشّرات فارغة كان سيُعلن حضوراً بلا معرفة."""
    mod, _ = _patch_grid(monkeypatch, {"ndmi": _grid(0.31), "msi": _grid(1.2)})
    assert await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1") is None


@pytest.mark.asyncio
async def test_simulated_or_unreal_products_are_not_authority(monkeypatch):
    """`real_data=false` أو ``source=simulation`` ⇒ لا سلطة خادميّة (لا خلط مصادر)."""
    mod, _ = _patch_grid(monkeypatch, {"ndvi": _grid(0.62, source="simulation")})
    assert await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1") is None

    mod, _ = _patch_grid(monkeypatch, {"ndvi": _grid(0.62, real=False)})
    assert await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1") is None


@pytest.mark.asyncio
async def test_empty_field_id_does_not_call_raster_at_all(monkeypatch):
    mod, calls = _patch_grid(monkeypatch, {"ndvi": _grid(0.62)})
    assert await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="") is None
    assert calls == [], "حقل بلا معرّف لا يستحقّ نداءً شبكيّاً"


@pytest.mark.asyncio
async def test_resolved_product_is_accepted_by_the_composer(monkeypatch):
    """الاختبار الحاسم: المنتَج يمرّ **فعلاً** عبر فحص المخطّط في النواة.

    ``build_canonical_spectral_state`` يُصدِر المفتاح ``schema`` لا ``schema_version``؛
    و``_schema_of`` يقبل الاثنين. لو تغيّر أحدهما لصار المنتَج يُرفَض بصمت بوصفه
    ``spectral_noncanonical_schema`` — أي وصلٌ يبدو قائماً ولا يصل شيئاً.
    """
    mod, _ = _patch_grid(
        monkeypatch,
        {"ndvi": _grid(0.62), "ndre": _grid(0.28), "ndmi": _grid(0.31), "msi": _grid(1.2)},
    )
    product = await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1")
    assert product is not None
    assert product["schema"] == "canonical_spectral_state.v1"
    assert product["indices"] == {"ndvi": 0.62, "ndre": 0.28, "ndmi": 0.31, "msi": 1.2}
    assert product["evidence_ids"] == ["S2_ABC"]
    assert product["acquisition_date"] == "2026-06-10"

    state = compose_canonical_field_state(
        field_id="f1", season_id=None, as_of_time="2026-06-10T00:00:00Z", spectral=product
    )
    assert state.availability["spectral"] is True
    assert "spectral_missing" not in state.limitations
    assert "spectral_noncanonical_schema" not in state.limitations
    assert "spectral" in state.evidence_digests


@pytest.mark.asyncio
async def test_temporal_compatibility_is_declared_unverified_not_assumed(monkeypatch):
    """المسار الخادميّ لا يملك إثبات التوافق الزمنيّ بين NDMI وMSI، فلا يدّعيه.

    تمرير ``temporal_compatible=True`` كان سيرفع ``confirmation_available`` بلا دليل
    ويحوّل قراءتين من مشهدين مختلفين إلى «تأكيد إجهاد».
    """
    mod, _ = _patch_grid(monkeypatch, {"ndvi": _grid(0.62), "ndmi": _grid(0.31), "msi": _grid(1.2)})
    product = await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1")
    assert product["water_stress"]["confirmation_available"] is False
    assert product["water_stress"]["temporal_compatible"] is None
    assert "ndmi_msi_temporal_compatibility_not_verified" in product["limitations"]


@pytest.mark.asyncio
async def test_partial_indices_are_named_missing_not_dropped(monkeypatch):
    mod, _ = _patch_grid(monkeypatch, {"ndvi": _grid(0.62)})
    product = await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1")
    assert product["indices"]["ndvi"] == 0.62
    assert sorted(product["missing_indices"]) == ["msi", "ndmi", "ndre"]
    assert product["status"] == "available"


@pytest.mark.asyncio
async def test_transport_failure_on_the_master_index_is_absence_not_an_exception(monkeypatch):
    """fail-soft: انقطاع raster-service يُترجَم غياباً مُعلَناً، لا انفجاراً في مسار خدمة-لخدمة."""
    from api import canonical_spectral_state as mod

    async def _boom(*a, **k):
        raise TimeoutError("raster unreachable")

    monkeypatch.setattr("api.raster_service_client.get_indicator_grid", _boom)
    assert await mod.resolve_canonical_spectral_state(tenant_id="t1", field_id="f1") is None
