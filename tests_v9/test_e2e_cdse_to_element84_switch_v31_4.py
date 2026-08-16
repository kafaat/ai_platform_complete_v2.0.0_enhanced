"""اختبار E2E مكثّف: تحويل البحث التاريخيّ من CDSE إلى Element84.

يتحقّق هذا الملفّ من كلّ طبقة في سلسلة التحويل:

    الإعدادات ──► stac_search() ──► stac_search_element84()
                         │
                         ▼
    stac_search_cdse() [افتراضيّ — fail-closed بلا اعتمادات]
                         │
                         ▼
    raster_cdse_processing / CdseQuotaExhausted ──► break-loop + تعليم Job
                         │
                         ▼
    backfill_scan_worker: provider_key في DB يعكس المزوّد الصحيح

جميعها وحدويّة (unit) — لا شبكة، لا DB، لا Docker.
"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import types
import unittest.mock as mock

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
# stac_search.py يُحمَّل هنا عبر importlib.util.spec_from_file_location (استيراد مباشر
# بمسار ملفّ، لا حزمة)، فاستيراداته الداخليّة المؤجَّلة مثل
# ``from raster_scene_model import provider_fallback_suggestion`` (فرع fail-closed) تحتاج
# services/raster-service على sys.path — نفس نمط test_raster_scene_model_v63.py.
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

# ─────────────────────────────────────────────────────────────────────────────
# حارس sys.modules — يُعيد كلّ تعديل بعد كلّ اختبار تلقائيّاً.
# نحفظ الوحدات التي تتعرّض للتلوّث (cdse_client / scene_policy / وحدات stac_search_*)
# قبل كلّ اختبار ونستعيدها بعده — كي لا تؤثّر في بقيّة الجناح.
# ─────────────────────────────────────────────────────────────────────────────
_GUARDED_MODULES = ("cdse_client", "scene_policy")


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    """احفظ واستعِد الوحدات الحسّاسة بعد كلّ اختبار."""
    saved = {k: sys.modules.get(k) for k in _GUARDED_MODULES}
    # نزيل أيضاً أيّ وحدة stac_search_* مُحمَّلة باسم مؤقّت كي لا تتراكم.
    stac_keys_before = {k for k in sys.modules if k.startswith("stac_search_")}
    cdse_proc_keys_before = {k for k in sys.modules if k.startswith("raster_cdse_proc")}
    yield
    # استعادة الوحدات المحفوظة
    for key, val in saved.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val
    # إزالة الوحدات المؤقّتة التي أضافها الاختبار
    for k in list(sys.modules):
        if k.startswith("stac_search_") and k not in stac_keys_before:
            sys.modules.pop(k, None)
        if k.startswith("raster_cdse_proc") and k not in cdse_proc_keys_before:
            sys.modules.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# مساعدات
# ─────────────────────────────────────────────────────────────────────────────


def _read(rel: pathlib.Path) -> str:
    return rel.read_text(encoding="utf-8")


def _require_stac_runtime_deps() -> None:
    """تخطَّ الاختبار إذا غابت التبعيّات الثقيلة التي يستوردها ``stac_search.py``.

    ``stac_search.py`` يستورد ``fastapi`` على مستوى الوحدة (``from fastapi import
    HTTPException``)، وبيئة الوحدة الدنيا في CI (وظيفة *Unit Tests*) لا تُثبّت fastapi.
    هذا نفس نمط ``pytest.importorskip("fastapi")`` المُستخدَم في عشرات الاختبارات الأخرى
    التي تُحمّل نقاط النهاية.
    """
    pytest.importorskip("fastapi")


# ─────────────────────────────────────────────────────────────────────────────
# القسم ١ — حُرّاس الإعدادات الساكنة (بلا استيراد)
# ─────────────────────────────────────────────────────────────────────────────


class TestStaticProviderConfig:
    """الإعداد الافتراضيّ يجب أن يكون element84؛ والتبديل إلى CDSE يتمّ بمتغيّر البيئة."""

    def test_raster_settings_default_element84(self):
        src = _read(_RASTER / "raster_settings.py")
        assert 'os.getenv("HISTORICAL_SEARCH_PROVIDER", "element84")' in src, (
            "raster_settings.py يجب أن يُعرِّف المزوّد الافتراضيّ element84 (صور Sentinel-2 الخام من Earth Search)"
        )

    def test_stac_search_module_has_element84_branch(self):
        src = _read(_RASTER / "stac_search.py")
        # P2-c: الأساس ما يزال HISTORICAL_SEARCH_PROVIDER، لكنّ الاختيار الفعّال قد يُشتَقّ من
        # بوّابة satellite_cdse عند التفعيل. يبقى فرع element84 الصريح مطلوباً.
        assert "provider = HISTORICAL_SEARCH_PROVIDER" in src, (
            "stac_search.py يجب أن يبقى HISTORICAL_SEARCH_PROVIDER أساس اختيار المزوّد"
        )
        assert 'if provider == "element84":' in src, (
            "stac_search.py يجب أن يحوي فرع element84 الصريح"
        )

    def test_stac_search_failclosed_without_cdse_credentials(self):
        src = _read(_RASTER / "stac_search.py")
        idx = src.find("async def stac_search(")
        body = src[idx : idx + 2000]
        assert "not _cdse.is_configured()" in body, "غياب اعتمادات CDSE يجب أن يُفشَل مُغلَقاً"
        assert "status_code=503" in body, "الفشل المُغلَق يجب أن يُعيد 503"

    def test_element84_search_returns_provider_element84_tag(self):
        src = _read(_RASTER / "stac_search.py")
        idx = src.find("async def stac_search_element84(")
        body = src[idx : idx + 2000]
        assert '"provider": "element84"' in body, (
            "stac_search_element84 يجب أن يُعلِّم المشاهد بـprovider=element84"
        )
        assert '"source": "element84-earth-search"' in body, (
            "المصدر يجب أن يكون element84-earth-search"
        )

    def test_cdse_search_returns_provider_cdse_tag(self):
        src = _read(_RASTER / "stac_search.py")
        idx = src.find("async def stac_search_cdse(")
        body = src[idx : idx + 2000]
        assert '"provider": "cdse"' in body
        assert '"source": "cdse-catalog"' in body

    def test_band_urls_from_assets_maps_element84_names(self):
        """band_urls_from_assets يُقرأ من Element84 — التعيين يجب أن يشمل rededge1/swir16/swir22."""
        src = _read(_RASTER / "stac_search.py")
        idx = src.find("def band_urls_from_assets(")
        body = src[idx : idx + 1000]
        assert '"rededge1"' in body, "rededge1 (B05) يجب أن يُعيَّن إلى rededge"
        assert '"swir16"' in body, "swir16 (B11) يجب أن يُعيَّن إلى swir1"
        assert '"swir22"' in body, "swir22 (B12) يجب أن يُعيَّن إلى swir2"

    def test_backfill_worker_no_hardcoded_earth_search_host(self):
        src = _read(_RASTER / "backfill_scan_worker.py")
        assert "earth-search.aws.element84.com" not in src, (
            "العامل يجب ألّا يُشفِّر مضيف Earth Search — التوجيه عبر stac_search_helpers"
        )

    def test_backfill_worker_routes_via_stac_search_helpers(self):
        src = _read(_RASTER / "backfill_scan_worker.py")
        assert "stac_search_helpers.stac_search" in src, (
            "العامل يجب أن يستخدم stac_search_helpers.stac_search (يدعم المزوّدَين)"
        )

    def test_backfill_worker_uses_provider_from_scene(self):
        """العامل يقرأ provider من المشهد — فمشاهد element84 تُخزَّن بـprovider_key=element84."""
        src = _read(_RASTER / "backfill_scan_worker.py")
        assert 'scene.get("provider")' in src, (
            "العامل يجب أن يقرأ provider من المشهد لا يُثبّته hardcoded"
        )

    def test_cdse_quota_exhausted_exception_defined(self):
        src = _read(_RASTER / "cdse_client.py")
        assert "class CdseQuotaExhausted(RuntimeError):" in src
        assert 'CDSE_QUOTA_EXHAUSTED_CODE = "ACCESS_INSUFFICIENT_PROCESSING_UNITS"' in src

    def test_cdse_processing_breaks_on_quota_exhausted(self):
        """raster_cdse_processing يجب أن يكسر الحلقة فوراً عند CdseQuotaExhausted."""
        src = _read(_RASTER / "raster_cdse_processing.py")
        assert "cdse_client.CdseQuotaExhausted" in src, (
            "raster_cdse_processing يجب أن يلتقط CdseQuotaExhausted"
        )
        assert '"cdse_quota_exhausted"' in src, "حالة النفاد يجب أن تُوسَم بـcdse_quota_exhausted"
        assert "break" in src, "يجب كسر حلقة المؤشّرات عند نفاد الرصيد"


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٢ — band_urls_from_assets وحدة (بلا شبكة)
# ─────────────────────────────────────────────────────────────────────────────


class TestBandUrlsFromAssets:
    """التحقّق من تعيين أصول Element84 إلى حقول BandMapping."""

    @pytest.fixture(autouse=True)
    def _import(self):
        # stac_search.py بلا تبعيّات ثقيلة — يمكن استيراده مباشرةً.
        _require_stac_runtime_deps()
        spec = importlib.util.spec_from_file_location("stac_search_e2e", _RASTER / "stac_search.py")
        mod = importlib.util.module_from_spec(spec)
        # cdse_client يُستورَد داخل دوالّ async — لا يُحتاج عند اختبار band_urls_from_assets.
        # نستخدم إسناداً مباشراً (لا setdefault) — _restore_sys_modules يُعيد القيمة الأصليّة.
        _fake = types.ModuleType("cdse_client")
        _fake.is_configured = lambda: False  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = _fake
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        self.fn = mod.band_urls_from_assets

    def test_typical_element84_assets_complete(self):
        assets = {
            "blue": {"href": "https://example.com/B02.tif"},
            "green": {"href": "https://example.com/B03.tif"},
            "red": {"href": "https://example.com/B04.tif"},
            "nir": {"href": "https://example.com/B08.tif"},
            "rededge1": {"href": "https://example.com/B05.tif"},
            "swir16": {"href": "https://example.com/B11.tif"},
            "swir22": {"href": "https://example.com/B12.tif"},
            "scl": {"href": "https://example.com/SCL.tif"},
        }
        result = self.fn(assets)
        assert result["blue"] == "https://example.com/B02.tif"
        assert result["green"] == "https://example.com/B03.tif"
        assert result["red"] == "https://example.com/B04.tif"
        assert result["nir"] == "https://example.com/B08.tif"
        assert result["rededge"] == "https://example.com/B05.tif", (
            "rededge1 يجب أن يُعيَّن إلى rededge"
        )
        assert result["swir1"] == "https://example.com/B11.tif", "swir16 يجب أن يُعيَّن إلى swir1"
        assert result["swir2"] == "https://example.com/B12.tif", "swir22 يجب أن يُعيَّن إلى swir2"
        assert result["scl"] == "https://example.com/SCL.tif"

    def test_missing_optional_bands_return_none(self):
        """بنود مفقودة تُرجِع None بدل رفع استثناء."""
        result = self.fn({})
        for key in ("blue", "green", "red", "nir", "rededge", "swir1", "swir2", "scl"):
            assert result[key] is None, f"{key} يجب أن يكون None إن لم يُوجَد في الأصول"

    def test_extra_assets_ignored(self):
        """الأصول الزائدة (visual, thumbnail, rededge2…) لا تُضاف إلى النتيجة."""
        assets = {
            "blue": {"href": "https://example.com/B02.tif"},
            "visual": {"href": "https://example.com/TCI.tif"},
            "thumbnail": {"href": "https://example.com/thumb.jpg"},
            "rededge2": {"href": "https://example.com/B06.tif"},
        }
        result = self.fn(assets)
        assert "visual" not in result
        assert "thumbnail" not in result
        assert "rededge2" not in result
        # الأصول المطلوبة
        assert result["blue"] == "https://example.com/B02.tif"


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٣ — stac_search_element84 محاكاة (mock stac_query)
# ─────────────────────────────────────────────────────────────────────────────


def _make_element84_feature(item_id: str, datetime: str, cloud: float) -> dict:
    return {
        "id": item_id,
        "bbox": [44.0, 15.0, 44.1, 15.1],
        "properties": {
            "datetime": datetime,
            "eo:cloud_cover": cloud,
            "platform": "sentinel-2a",
        },
        "assets": {
            "blue": {"href": f"https://cdn.example.com/{item_id}/B02.tif"},
            "green": {"href": f"https://cdn.example.com/{item_id}/B03.tif"},
            "red": {"href": f"https://cdn.example.com/{item_id}/B04.tif"},
            "nir": {"href": f"https://cdn.example.com/{item_id}/B08.tif"},
            "rededge1": {"href": f"https://cdn.example.com/{item_id}/B05.tif"},
            "swir16": {"href": f"https://cdn.example.com/{item_id}/B11.tif"},
            "swir22": {"href": f"https://cdn.example.com/{item_id}/B12.tif"},
            "scl": {"href": f"https://cdn.example.com/{item_id}/SCL.tif"},
            "thumbnail": {"href": f"https://cdn.example.com/{item_id}/thumb.jpg"},
            "visual": {"href": f"https://cdn.example.com/{item_id}/TCI.tif"},
        },
    }


class TestStacSearchElement84Unit:
    """stac_search_element84 يُعيد البنية الصحيحة من استجابة STAC محاكاة."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        _require_stac_runtime_deps()
        spec = importlib.util.spec_from_file_location(
            "stac_search_e84_unit", _RASTER / "stac_search.py"
        )
        mod = importlib.util.module_from_spec(spec)
        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.is_configured = lambda: False  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse  # إسناد مباشر — _restore_sys_modules يُعيد الأصل
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        self.mod = mod

    def _run(self, coro):
        return asyncio.run(coro)

    def test_returns_element84_items_with_correct_provider(self):
        features = [
            _make_element84_feature("S2A_2025_001", "2025-01-01T10:00:00Z", 5.0),
            _make_element84_feature("S2B_2025_002", "2025-01-06T10:00:00Z", 12.0),
        ]
        mock_data = {"features": features, "_cache": "miss"}

        async def fake_stac_query(payload):
            return mock_data

        self.mod.stac_query = fake_stac_query

        result = self._run(
            self.mod.stac_search_element84(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-01-01",
                dt_end="2025-01-31",
                max_cloud=30.0,
                limit=10,
            )
        )

        assert result["count"] == 2
        assert result["source"] == "element84-earth-search"
        for item in result["items"]:
            assert item["provider"] == "element84", "كلّ مشهد يجب أن يُوسَم بـprovider=element84"
        # التحقّق من تعيين النطاقات
        first = result["items"][0]
        assert first["bands_urls"]["rededge"] is not None, "rededge1→rededge يجب أن يُعيَّن"
        assert first["bands_urls"]["swir1"] is not None, "swir16→swir1 يجب أن يُعيَّن"
        assert first["bands_urls"]["swir2"] is not None, "swir22→swir2 يجب أن يُعيَّن"
        # الأصول الزائدة لا تتسرّب
        assert "visual" not in first["bands_urls"]
        assert "thumbnail" not in first["bands_urls"]

    def test_empty_features_returns_zero_count(self):
        async def fake_stac_query(payload):
            return {"features": [], "_cache": "miss"}

        self.mod.stac_query = fake_stac_query
        result = self._run(
            self.mod.stac_search_element84(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-01-01",
                dt_end="2025-01-31",
                max_cloud=30.0,
                limit=10,
            )
        )
        assert result["count"] == 0
        assert result["items"] == []

    def test_item_structure_completeness(self):
        """كلّ عنصر يجب أن يحمل الحقول الإلزاميّة."""
        features = [_make_element84_feature("S2A_2025_ABC", "2025-03-15T09:30:00Z", 8.0)]

        async def fake_stac_query(payload):
            return {"features": features}

        self.mod.stac_query = fake_stac_query
        result = self._run(
            self.mod.stac_search_element84(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-03-01",
                dt_end="2025-03-31",
                max_cloud=20.0,
                limit=5,
            )
        )
        item = result["items"][0]
        required_keys = {
            "item_id",
            "datetime",
            "cloud_cover_pct",
            "bbox",
            "bands_urls",
            "thumbnail_url",
            "preview_url",
            "platform",
            "provider",
        }
        missing = required_keys - set(item.keys())
        assert not missing, f"حقول مفقودة: {missing}"
        assert item["item_id"] == "S2A_2025_ABC"
        assert item["datetime"] == "2025-03-15T09:30:00Z"
        assert item["cloud_cover_pct"] == 8.0
        assert item["platform"] == "sentinel-2a"


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٤ — stac_search() توجيه المزوّد (mock كامل)
# ─────────────────────────────────────────────────────────────────────────────


class TestStacSearchProviderRouting:
    """stac_search() يوجّه إلى المزوّد الصحيح بحسب HISTORICAL_SEARCH_PROVIDER."""

    @pytest.fixture(autouse=True)
    def _load_module(self, monkeypatch):
        # نعزل stac_search.py تماماً بموفِّر cdse وهميّ
        _require_stac_runtime_deps()
        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.is_configured = lambda: False  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "cdse_client", fake_cdse)

        spec = importlib.util.spec_from_file_location(
            "stac_search_routing", _RASTER / "stac_search.py"
        )
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)  # type: ignore[union-attr]

    def _run(self, coro):
        return asyncio.run(coro)

    def test_routes_to_element84_when_env_set(self):
        """HISTORICAL_SEARCH_PROVIDER=element84 ⇒ stac_search_element84 تُستدعى."""
        called = []

        async def fake_element84(bbox, dt_start, dt_end, max_cloud, limit):
            called.append("element84")
            return {"count": 0, "source": "element84-earth-search", "items": []}

        self.mod.HISTORICAL_SEARCH_PROVIDER = "element84"
        self.mod.stac_search_element84 = fake_element84

        self._run(
            self.mod.stac_search(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-01-01",
                dt_end="2025-01-31",
                max_cloud=30.0,
                limit=10,
            )
        )
        assert called == ["element84"], "يجب استدعاء element84 حصراً"

    def test_failclosed_cdse_no_credentials(self):
        """HISTORICAL_SEARCH_PROVIDER=cdse + لا اعتمادات ⇒ HTTPException 503."""
        from fastapi import HTTPException

        self.mod.HISTORICAL_SEARCH_PROVIDER = "cdse"
        # cdse_client.is_configured() يُعيد False (وُضِع في الـfixture)

        with pytest.raises(HTTPException) as exc_info:
            self._run(
                self.mod.stac_search(
                    bbox=[44.0, 15.0, 44.1, 15.1],
                    dt_start="2025-01-01",
                    dt_end="2025-01-31",
                    max_cloud=30.0,
                    limit=10,
                )
            )
        assert exc_info.value.status_code == 503, (
            "يجب أن تُعيد 503 عند غياب اعتمادات CDSE (fail-closed)"
        )

    def test_cdse_provider_with_credentials_calls_cdse_search(self):
        """HISTORICAL_SEARCH_PROVIDER=cdse + اعتمادات موجودة ⇒ stac_search_cdse تُستدعى."""
        called = []

        # أعد تحميل الوحدة بـcdse يعيد is_configured=True
        fake_cdse_configured = types.ModuleType("cdse_client")
        fake_cdse_configured.is_configured = lambda: True  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse_configured

        async def fake_cdse_search(bbox, dt_start, dt_end, max_cloud, limit, geometry=None):
            called.append("cdse")
            return {"count": 0, "source": "cdse-catalog", "items": []}

        self.mod.HISTORICAL_SEARCH_PROVIDER = "cdse"
        self.mod.stac_search_cdse = fake_cdse_search

        # أعد إضافة المزوّد الوهميّ المُهيَّأ في الوحدة
        import importlib as _il

        _il.import_module("cdse_client")

        self._run(
            self.mod.stac_search(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-01-01",
                dt_end="2025-01-31",
                max_cloud=30.0,
                limit=10,
            )
        )
        assert called == ["cdse"], "يجب استدعاء cdse_search عند وجود الاعتمادات"

    def test_element84_search_never_called_in_cdse_failclosed_path(self):
        """مسار الفشل المُغلَق يجب ألّا يستدعي element84 كارتداد صامت."""
        called_e84 = []

        async def fake_element84(*a, **kw):
            called_e84.append(True)
            return {"count": 0, "items": []}

        self.mod.HISTORICAL_SEARCH_PROVIDER = "cdse"
        self.mod.stac_search_element84 = fake_element84

        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            self._run(
                self.mod.stac_search(
                    bbox=[44.0, 15.0, 44.1, 15.1],
                    dt_start="2025-01-01",
                    dt_end="2025-01-31",
                    max_cloud=30.0,
                    limit=10,
                )
            )
        assert not called_e84, "Element84 يجب ألّا يُستدعى كارتداد صامت — لا silent fallback"


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٥ — stac_search_cdse بنية الاستجابة (mock CDSE client)
# ─────────────────────────────────────────────────────────────────────────────


class TestStacSearchCdseResponseFormat:
    """stac_search_cdse تُعيد البنية الصحيحة."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        _require_stac_runtime_deps()
        spec = importlib.util.spec_from_file_location(
            "stac_search_cdse_fmt", _RASTER / "stac_search.py"
        )
        self.mod = importlib.util.module_from_spec(spec)
        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.is_configured = lambda: True  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse
        spec.loader.exec_module(self.mod)  # type: ignore[union-attr]

    def _run(self, coro):
        return asyncio.run(coro)

    def test_cdse_features_mapped_correctly(self):
        """مشاهد CDSE تُحوَّل إلى البنية الصحيحة مع provider=cdse."""
        fake_scenes = [
            {
                "id": "cdse-scene-001",
                "bbox": [44.0, 15.0, 44.1, 15.1],
                "properties": {
                    "datetime": "2025-02-10T08:00:00Z",
                    "eo:cloud_cover": 7.3,
                    "platform": "sentinel-2b",
                },
            }
        ]

        import asyncio as _a
        import types as _t

        fake_client = _t.SimpleNamespace(search_scenes=lambda **kw: fake_scenes)
        import sys as _sys

        _sys.modules["cdse_client"].get_client = lambda: fake_client  # type: ignore[attr-defined]

        result = self._run(
            self.mod.stac_search_cdse(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-02-01",
                dt_end="2025-02-28",
                max_cloud=30.0,
                limit=10,
            )
        )

        assert result["source"] == "cdse-catalog"
        assert result["count"] == 1
        item = result["items"][0]
        assert item["provider"] == "cdse"
        assert item["item_id"] == "cdse-scene-001"
        assert item["cloud_cover_pct"] == 7.3
        # مشاهد CDSE ليس لها bands_urls (المعالجة عبر Process API)
        assert item["bands_urls"] == {}

    def test_cdse_search_error_returns_empty_list(self):
        """فشل CDSE catalog يُعيد قائمة فارغة بدل رفع استثناء (تدهور سلس)."""

        import sys as _sys
        import types as _t

        class FakeClient:
            def search_scenes(self, **kw):
                raise ConnectionError("CDSE catalog unreachable")

        _sys.modules["cdse_client"].get_client = FakeClient  # type: ignore[attr-defined]

        result = self._run(
            self.mod.stac_search_cdse(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-02-01",
                dt_end="2025-02-28",
                max_cloud=30.0,
                limit=10,
            )
        )
        assert result["count"] == 0
        assert result["items"] == []
        assert result["source"] == "cdse-catalog"


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٦ — CdseQuotaExhausted: توقّف الحلقة + تعليم الـJob
# ─────────────────────────────────────────────────────────────────────────────


class TestCdseQuotaExhaustedBreaksLoop:
    """عند نفاد رصيد CDSE، run_cdse_processing يكسر الحلقة فوراً ويُعلِّم الـJob."""

    def _make_fake_job_store(self):
        store = {}

        class FakeJobStore:
            def get(self, jid):
                return store.get(jid)

            def set(self, jid, val):
                store[jid] = val

        return FakeJobStore(), store

    def _make_fake_ctx(self, process_side_effect):
        """يبني ctx وهميّاً يرفع process_side_effect عند الاستدعاء."""
        import enum
        import sys as _sys
        import types as _t

        # تأكّد من وجود cdse_client وهميّ
        fake_cdse = types.ModuleType("cdse_client")

        class FakeQuotaExhausted(RuntimeError):
            pass

        fake_cdse.CdseQuotaExhausted = FakeQuotaExhausted  # type: ignore[attr-defined]

        class FakeClient:
            def process_index(self, **kw):
                raise process_side_effect

            def search_scenes(self, **kw):
                return []

        fake_cdse.get_client = FakeClient  # type: ignore[attr-defined]
        fake_cdse._to_rfc3339 = lambda v: v  # type: ignore[attr-defined]
        # ثابتا ترتيب الفسيفساء: `run_cdse_processing` يقرؤهما ليجعل آخر خطوة توافق
        # العقد الذي اختار المشهد (`mostRecent` للأحدث، `leastCC` لغيره). الوحدة
        # الوهميّة يجب أن تحمل عقد الحقيقيّة وإلّا صار الاختبار يقيس نقصَ الدُّمية.
        fake_cdse.MOSAIC_LEAST_CLOUD = "leastCC"  # type: ignore[attr-defined]
        fake_cdse.MOSAIC_MOST_RECENT = "mostRecent"  # type: ignore[attr-defined]
        _sys.modules["cdse_client"] = fake_cdse

        class JobStatus(str, enum.Enum):
            processing = "processing"
            completed = "completed"
            failed = "failed"

        job_store, raw_store = self._make_fake_job_store()

        class FakeCtx:
            JobStatus = JobStatus
            logger = mock.MagicMock()
            UPLOAD_DIR = "/tmp"

            def __init__(self):
                self._jobs = job_store

            def _run_processing(self, sub_job_id, preq):
                pass

        return FakeCtx(), raw_store, fake_cdse.CdseQuotaExhausted

    def test_quota_exhausted_breaks_after_first_index(self):
        """CdseQuotaExhausted عند المؤشّر الأوّل يوقف الحلقة فوراً."""

        # يجب أن تُنشَأ fake_cdse + FakeQuotaExhausted أوّلاً، ثمّ تُحمَّل الوحدة —
        # كي يكون except cdse_client.CdseQuotaExhausted يلتقط نفس الصنف المُستخدَم في raise.
        class _FakeQuotaExhausted(RuntimeError):
            pass

        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.CdseQuotaExhausted = _FakeQuotaExhausted  # type: ignore[attr-defined]

        quota_exc = _FakeQuotaExhausted(
            "CDSE account has insufficient processing units; add credits to resume imagery."
        )

        class _FakeClient:
            def process_index(self, **kw):
                raise quota_exc

            def search_scenes(self, **kw):
                return []

        fake_cdse.get_client = _FakeClient  # type: ignore[attr-defined]
        fake_cdse._to_rfc3339 = lambda v: v  # type: ignore[attr-defined]
        # ثابتا ترتيب الفسيفساء: `run_cdse_processing` يقرؤهما ليجعل آخر خطوة توافق
        # العقد الذي اختار المشهد (`mostRecent` للأحدث، `leastCC` لغيره). الوحدة
        # الوهميّة يجب أن تحمل عقد الحقيقيّة وإلّا صار الاختبار يقيس نقصَ الدُّمية.
        fake_cdse.MOSAIC_LEAST_CLOUD = "leastCC"  # type: ignore[attr-defined]
        fake_cdse.MOSAIC_MOST_RECENT = "mostRecent"  # type: ignore[attr-defined]
        fake_cdse.supported_indices = lambda: {"ndvi", "ndmi", "msi", "evi", "ndwi", "ndre", "savi"}  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse

        # raster_cdse_processing.py يستورد scene_policy على مستوى الوحدة.
        # نُقدِّم stub فارغاً (rank_scenes غير مطلوب: req.date_from مُضبوط ⇒ يتجاوز
        # مسار البحث/rank_scenes مباشرةً إلى process_index). autouse fixture ينظّفه.
        sys.modules.setdefault("scene_policy", types.ModuleType("scene_policy"))
        spec = importlib.util.spec_from_file_location(
            "raster_cdse_proc_quota", _RASTER / "raster_cdse_processing.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        import enum as _enum

        class _JS(str, _enum.Enum):
            processing = "processing"
            completed = "completed"
            failed = "failed"

        job_store, raw_store = self._make_fake_job_store()

        class _FakeCtx:
            JobStatus = _JS
            logger = mock.MagicMock()
            UPLOAD_DIR = "/tmp"

            def __init__(self):
                self._jobs = job_store

            def _run_processing(self, sub_job_id, preq):
                pass

        ctx = _FakeCtx()

        class FakeReq:
            lookback_days = 30
            date_from = "2025-01-01"
            date_to = "2025-01-31"
            bbox = [44.0, 15.0, 44.1, 15.1]
            max_cloud_pct = 30.0
            geometry = None
            geometry_revision = 1
            tenant_id = "test-tenant"
            indicators = ["ndvi", "ndmi", "msi"]  # ثلاثة مؤشّرات

        job_id = "test-job-quota-001"
        ctx._jobs.set(job_id, {"job_id": job_id})

        # الدالّة تعمل بصمت (تُعيد None) — نفحص حالة الـJob
        try:
            mod.run_cdse_processing(ctx, job_id, "field-001", FakeReq())
        except Exception as exc:
            # رمز الإنتاج يُمسِك CdseQuotaExhausted داخليّاً ولا يرفعها
            # إن وصلت هنا فالخلل في الكود
            pytest.fail(f"run_cdse_processing يجب ألّا ترفع CdseQuotaExhausted: {exc}")

        job = ctx._jobs.get(job_id)
        assert job is not None
        assert job.get("cdse_quota_exhausted") is True, (
            "يجب تعليم الـJob بـcdse_quota_exhausted=True"
        )
        assert "cdse_error_reason" in job, "يجب حفظ سبب النفاد في cdse_error_reason"
        # المؤشّر الأوّل سُجِّل كفاشل بسبب نفاد الرصيد
        failed = job.get("cdse_failed", {})
        assert "ndvi" in failed
        assert failed["ndvi"] == "cdse_quota_exhausted"
        # المؤشّران الثاني والثالث لم يُجرَّبا (الحلقة كُسِرت)
        assert "ndmi" not in failed, "ndmi لا يجب أن يُجرَّب بعد نفاد الرصيد"
        assert "msi" not in failed, "msi لا يجب أن يُجرَّب بعد نفاد الرصيد"

    def test_quota_exhausted_on_second_index_stops_third(self):
        """CdseQuotaExhausted في المؤشّر الثاني يوقف الثالث — لا انتظار."""

        # نُعدّ cdse_client أوّلاً بـCdseQuotaExhausted الصحيح، ثمّ نحمّل الوحدة.
        class _FakeQE2(RuntimeError):
            pass

        fake_cdse2 = types.ModuleType("cdse_client")
        fake_cdse2.CdseQuotaExhausted = _FakeQE2  # type: ignore[attr-defined]
        fake_cdse2.supported_indices = lambda: {"ndvi", "ndmi", "msi"}  # type: ignore[attr-defined]
        fake_cdse2._to_rfc3339 = lambda v: v  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse2
        # stub فارغ لـscene_policy (autouse fixture ينظّفه بعد الاختبار)
        sys.modules.setdefault("scene_policy", types.ModuleType("scene_policy"))

        spec = importlib.util.spec_from_file_location(
            "raster_cdse_proc_quota2", _RASTER / "raster_cdse_processing.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # الاستدعاء الأوّل ينجح، الثاني يرفع quota_exhausted
        calls = []

        class FakeClientSeq:
            def process_index(self, index, **kw):
                calls.append(index)
                if index == "ndmi":
                    raise _FakeQE2("quota")
                return b"\x49\x49\x2a\x00"  # TIFF magic bytes

            def search_scenes(self, **kw):
                return []

        fake_cdse2.get_client = FakeClientSeq  # type: ignore[attr-defined]

        import enum

        class JS(str, enum.Enum):
            processing = "processing"
            completed = "completed"
            failed = "failed"

        job_store_inner, raw_store_inner = self._make_fake_job_store()

        class Ctx2:
            JobStatus = JS
            logger = mock.MagicMock()
            UPLOAD_DIR = "/tmp"

            def __init__(self):
                self._jobs = job_store_inner

            def _run_processing(self, sub_job_id, preq):
                pass

            class ProcessRequest:
                def __init__(self, **kw):
                    pass

            class IndicatorKind:
                def __init__(self, v):
                    self.v = v

            class SourceFormat:
                sentinel2_l2a = "sentinel2_l2a"

            class BandMapping:
                def __init__(self):
                    pass

        ctx2 = Ctx2()
        ctx2._jobs.set("job-seq", {"job_id": "job-seq"})

        # نحتاج IndicatorKind/SourceFormat/BandMapping لأنّ process_backfill_scene_cdse تستعملها
        # لكنّ run_cdse_processing يعتمد ctx.ProcessRequest — نُعيّنها بشكل آمن
        # (المؤشّر الأوّل سيصل إلى process_index ويُعيد تيف مصغَّر)
        # لتجاوز حفظ الملفّ نُعيّن UPLOAD_DIR لمجلّد موجود
        import tempfile

        ctx2.UPLOAD_DIR = tempfile.gettempdir()

        class FakeReq2:
            lookback_days = 30
            date_from = "2025-01-01"
            date_to = "2025-01-31"
            bbox = [44.0, 15.0, 44.1, 15.1]
            max_cloud_pct = 30.0
            geometry = None
            geometry_revision = 1
            tenant_id = "tenant-seq"
            indicators = ["ndvi", "ndmi", "msi"]

        try:
            mod.run_cdse_processing(ctx2, "job-seq", "field-seq", FakeReq2())
        except Exception:
            pass  # بعض المؤشّرات قد ترفع استثناءات أخرى (ملفّ TIF زائف) — نتجاهلها

        job = ctx2._jobs.get("job-seq")
        assert job is not None
        # المؤشّر الأوّل جُرِّب على الأقلّ، الحلقة توقّفت عند ndmi أو بعده
        failed = job.get("cdse_failed", {})
        # المهمّ: msi لا يجب أن يُجرَّب بعد نفاد الرصيد عند ndmi
        assert "msi" not in failed, "msi لا يجب أن يُعالَج بعد CdseQuotaExhausted في ndmi"
        assert not any(k in calls for k in ["msi"]), (
            "process_index لا يجب أن يُستدعى لـmsi بعد نفاد الرصيد"
        )


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٧ — تكامل العامل + Element84 (static source analysis)
# ─────────────────────────────────────────────────────────────────────────────


class TestBackfillWorkerElement84Integration:
    """العامل يحترم مزوّد المشهد ويُخزَّن provider_key بشكل صحيح."""

    def test_worker_uses_provider_from_scene_not_hardcoded(self):
        """العامل يستخرج provider من المشهد — فعند element84 تُخزَّن provider_key=element84."""
        src = _read(_RASTER / "backfill_scan_worker.py")
        # ابحث عن منطقة إدراج DB لـprovider_key
        assert 'scene.get("provider")' in src, (
            "العامل يجب أن يقرأ provider من المشهد الذي أعاده stac_search"
        )

    def test_worker_element84_provider_fallback_to_cdse(self):
        """إن لم يُضبَط provider، يُفترَض cdse (المزوّد الافتراضيّ)."""
        src = _read(_RASTER / "backfill_scan_worker.py")
        # الكود: scene.get("provider") or "cdse"
        assert '(scene.get("provider") or "cdse")' in src, (
            "العامل يجب أن يسقط إلى cdse افتراضيّاً إن لم يُضبَط provider"
        )

    def test_worker_stac_search_call_passes_geometry(self):
        """العامل يمرّر geometry= للبحث — ضروريّ لقصّ CDSE/element84 بدقّة."""
        src = _read(_RASTER / "backfill_scan_worker.py")
        assert "geometry=clip" in src, (
            "العامل يجب أن يمرّر geometry=clip لدعم intersects في CDSE وElement84"
        )


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٨ — حارس تسرّب Earth Search (لا مسار backfill يصل element84 مباشرةً)
# ─────────────────────────────────────────────────────────────────────────────


class TestNoDirectEarthSearchInBackfillPaths:
    """لا يجب أن يشير أيّ ملفّ backfill/router إلى Earth Search مباشرةً."""

    @pytest.mark.parametrize(
        "filename",
        [
            "backfill_scan_worker.py",
            "routers/fields.py",
        ],
    )
    def test_no_direct_earth_search_host(self, filename):
        src = _read(_RASTER / filename)
        assert "earth-search.aws.element84.com" not in src, (
            f"{filename} يجب ألّا يُثبِّت رابط Earth Search — التوجيه عبر stac_search_helpers"
        )

    def test_stac_runtime_holds_earth_search_url(self):
        """raster_stac_runtime هو الوحيد المسموح له بحمل EARTH_SEARCH_URL للتهيئة."""
        src = _read(_RASTER / "raster_stac_runtime.py")
        assert "EARTH_SEARCH_URL" in src, (
            "EARTH_SEARCH_URL يجب أن يبقى في raster_stac_runtime (تهيئة العميل)"
        )

    def test_backfill_worker_no_earth_search_url_constant(self):
        """العامل لا يُعرِّف EARTH_SEARCH_URL (مُفوَّض إلى raster_stac_runtime)."""
        src = _read(_RASTER / "backfill_scan_worker.py")
        assert "EARTH_SEARCH_URL" not in src, (
            "EARTH_SEARCH_URL يجب ألّا يظهر في العامل — مفوَّض إلى raster_stac_runtime"
        )


# ─────────────────────────────────────────────────────────────────────────────
# القسم ٩ — تكامل نهائيّ (محاكاة شاملة: env=element84 → item.provider=element84)
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndElement84Switch:
    """سيناريو E2E كامل: ضبط المتغيّر → بحث → نتائج element84."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_full_switch_cdse_to_element84(self):
        """HISTORICAL_SEARCH_PROVIDER=element84 → stac_search() → items بـprovider=element84."""
        # تحميل الوحدة مع المزوّد element84
        _require_stac_runtime_deps()
        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.is_configured = lambda: False  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse

        spec = importlib.util.spec_from_file_location(
            "stac_search_e2e_full", _RASTER / "stac_search.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # ضبط المزوّد إلى element84 (يحاكي HISTORICAL_SEARCH_PROVIDER=element84)
        mod.HISTORICAL_SEARCH_PROVIDER = "element84"

        # بيانات محاكاة من Earth Search
        mock_features = [
            _make_element84_feature("S2A_2025-01-15", "2025-01-15T09:45:00Z", 3.2),
            _make_element84_feature("S2B_2025-01-20", "2025-01-20T09:45:00Z", 11.8),
        ]

        async def fake_stac_query(payload):
            assert payload["collections"] == [mod.SENTINEL_COLLECTION], (
                "مجموعة Sentinel-2 يجب أن تُطلَب"
            )
            return {"features": mock_features, "_cache": "miss"}

        mod.stac_query = fake_stac_query

        result = self._run(
            mod.stac_search(
                bbox=[44.0, 15.0, 44.1, 15.1],
                dt_start="2025-01-01",
                dt_end="2025-01-31",
                max_cloud=30.0,
                limit=10,
            )
        )

        # التحقّقات الجوهريّة
        assert result["count"] == 2, f"توقَّعنا 2 مشهد، وجدنا {result['count']}"
        assert result["source"] == "element84-earth-search"
        for item in result["items"]:
            assert item["provider"] == "element84", (
                f"المشهد {item.get('item_id')} يجب أن يكون provider=element84"
            )
            # bands_urls يجب أن تكون مُعبَّأة
            assert item["bands_urls"].get("rededge") is not None, (
                "rededge يجب أن تكون مُعيَّنة (من rededge1)"
            )
            assert item["bands_urls"].get("swir1") is not None, (
                "swir1 يجب أن تكون مُعيَّنة (من swir16)"
            )
            assert item["bands_urls"].get("swir2") is not None, (
                "swir2 يجب أن تكون مُعيَّنة (من swir22)"
            )

    def test_full_switch_cdse_failclosed(self):
        """HISTORICAL_SEARCH_PROVIDER=cdse + لا اعتمادات → 503 (لا ارتداد صامت)."""
        _require_stac_runtime_deps()
        fake_cdse = types.ModuleType("cdse_client")
        fake_cdse.is_configured = lambda: False  # type: ignore[attr-defined]
        sys.modules["cdse_client"] = fake_cdse

        spec = importlib.util.spec_from_file_location(
            "stac_search_e2e_failclosed", _RASTER / "stac_search.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        mod.HISTORICAL_SEARCH_PROVIDER = "cdse"

        from fastapi import HTTPException as FHE

        with pytest.raises(FHE) as exc_info:
            self._run(
                mod.stac_search(
                    bbox=[44.0, 15.0, 44.1, 15.1],
                    dt_start="2025-01-01",
                    dt_end="2025-01-31",
                    max_cloud=30.0,
                    limit=10,
                )
            )
        assert exc_info.value.status_code == 503
        # detail مُهيكَل (dict) لا نصّ حرّ — {"message": ..., "fallback_suggestion": {...}}
        detail = exc_info.value.detail
        assert isinstance(detail, dict), "detail يجب أن يكون مُهيكَلاً (dict) لا نصّاً حرّاً"
        message = detail["message"]
        # الرسالة يجب أن تذكر CDSE والاعتمادات والطريقة البديلة
        assert "CDSE" in message or "cdse" in message.lower(), "رسالة الخطأ يجب أن تُشير إلى CDSE"
        assert "element84" in message.lower() or "HISTORICAL_SEARCH_PROVIDER" in message, (
            "رسالة الخطأ يجب أن تُرشد إلى HISTORICAL_SEARCH_PROVIDER=element84 كبديل"
        )
        # الاقتراح الاحتياطيّ المُهيكَل يوجّه صراحةً إلى element84
        suggestion = detail["fallback_suggestion"]
        assert suggestion["suggested_provider"] == "element84"
        assert "HISTORICAL_SEARCH_PROVIDER=element84" in suggestion["action"]
