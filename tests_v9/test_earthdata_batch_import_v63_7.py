"""تحقّق V63.7 — قناة استيراد Earthdata الدفعيّ + نَسَب الأصول المُستورَدة (صدق + أمن).

- earthdata_wget_batch مُسجَّل كـmanual_batch_download (غير مزوّد حيّ، active_provider=False).
- يدعم HLS/ASTER/SRTM/NASADEM/MODIS/VIIRS/MERRA2 عبر Earthdata Login.
- نَسَب الأصل المُستورَد: يجب checksum + source_url + acquisition_date؛ أيّ سرّ ⇒ رفض.

منطق صرف — وظيفة Unit Tests.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_RASTER = _ROOT / "services" / "raster-service"
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))

import raster_scene_model as M  # noqa: E402


def test_earthdata_batch_registered_as_manual_channel():
    e = M.EXTERNAL_SOURCE_REGISTRY["earthdata_wget_batch"]
    assert e["source_type"] == "manual_batch_download"
    assert e["active_provider"] is False and e["requires_earthdata_login"] is True
    assert "hls" in e["supports"] and "aster_gdem" in e["supports"]
    assert "earthdata_wget_batch" in M.sources_by_type("manual_batch_download")


def test_import_provenance_requires_full_lineage():
    ok = M.imported_asset_provenance_ok(
        {
            "checksum": "abc",
            "source_url": "https://data.lpdaac...",
            "acquisition_date": "2026-07-01",
        }
    )
    assert ok["ok"] is True and ok["missing"] == []
    # ناقص المصدر/التحقّق ⇒ يُرفَض (لا أصل يتيم).
    bad = M.imported_asset_provenance_ok({"checksum": "abc"})
    assert bad["ok"] is False
    assert "source_url" in bad["missing"] and "acquisition_date" in bad["missing"]


def test_import_provenance_rejects_leaked_secrets():
    # أمن: كلمة مرور/توكن في السجلّ ⇒ رفض (الاعتماد عبر .netrc لا السجلّ).
    leaked = M.imported_asset_provenance_ok(
        {
            "checksum": "abc",
            "source_url": "https://x",
            "acquisition_date": "2026-07-01",
            "password": "hunter2",
        }
    )
    assert leaked["ok"] is False and "password" in leaked["leaked_secret_fields"]


def test_batch_channel_stays_out_of_providers_and_active():
    assert "earthdata_wget_batch" not in M.PROVIDER_REGISTRY
    assert "earthdata_wget_batch" not in M.active_providers()
