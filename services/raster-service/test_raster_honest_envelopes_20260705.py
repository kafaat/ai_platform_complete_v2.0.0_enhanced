"""حارس صدق: cog_writer.write_cog وterrain.compute_slope_aspect يُرجعان مظروفاً
صريحاً عند المدخل غير الصالح (لا انهيار) — مطابقة عقد «لا اختلاق» (تدقيق 2026-07-05).
"""

from __future__ import annotations

import sys
from pathlib import Path

_RASTER = Path(__file__).resolve().parent
if str(_RASTER) not in sys.path:
    sys.path.insert(0, str(_RASTER))


def test_write_cog_none_array_returns_envelope_not_crash():
    import cog_writer

    out = cog_writer.write_cog(None, "/tmp/x.tif", transform=None)
    assert out["written"] is False
    assert "غير صالحة" in out["reason"]


def test_compute_slope_aspect_missing_dem_returns_envelope():
    import terrain_analysis

    out = terrain_analysis.compute_slope_aspect("/tmp/does_not_exist_x.tif")
    # إمّا مظروف «غير موجود» (rasterio متاح) أو «غير متوفّر» (بيئة بلا rasterio) — كلاهما صادق.
    assert out["computed"] is False
    assert "reason" in out
