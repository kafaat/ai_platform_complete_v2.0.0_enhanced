"""Reference COGs for the TiTiler parity run (deterministic, no network)."""

import sys

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

out = sys.argv[1]
W = H = 512
# NDVI-like float32 in EPSG:4326 over a field near Sana'a, NaN nodata in one corner.
west, south, east, north = 44.180, 15.330, 44.200, 15.350
yy, xx = np.mgrid[0:H, 0:W]
ndvi = (-0.2 + 1.1 * (xx + yy) / (W + H - 2)).astype("float32")
ndvi[:64, :64] = np.nan
prof = dict(
    driver="GTiff",
    width=W,
    height=H,
    count=1,
    dtype="float32",
    crs="EPSG:4326",
    transform=from_bounds(west, south, east, north, W, H),
    nodata=float("nan"),
)
with rasterio.MemoryFile() as mem:
    with mem.open(**prof) as ds:
        ds.write(ndvi, 1)
    with mem.open() as src:
        cog_translate(
            src, f"{out}/ndvi_float32_epsg4326.tif", cog_profiles.get("deflate"), quiet=True
        )
# uint8 RGB in UTM 38N (EPSG:32638) over the same area, nodata 0 border.
e0, n0 = 411000.0, 1695000.0
rgb = np.stack([(xx % 256), (yy % 256), ((xx + yy) % 256)]).astype("uint8")
rgb[:, :, :16] = 0
prof = dict(
    driver="GTiff",
    width=W,
    height=H,
    count=3,
    dtype="uint8",
    crs="EPSG:32638",
    transform=from_bounds(e0, n0, e0 + 2048, n0 + 2048, W, H),
    nodata=0,
)
with rasterio.MemoryFile() as mem:
    with mem.open(**prof) as ds:
        ds.write(rgb)
    with mem.open() as src:
        cog_translate(
            src, f"{out}/rgb_uint8_epsg32638.tif", cog_profiles.get("deflate"), quiet=True
        )
for name in ("ndvi_float32_epsg4326.tif", "rgb_uint8_epsg32638.tif"):
    print(name, cog_validate(f"{out}/{name}")[0])
