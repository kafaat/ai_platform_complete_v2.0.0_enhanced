# Element84 calibration: supported C1 path

Base `6e8cc0f9952c037550ae1644919f88c475dd89a7`; no deployment/DB mutation by this evidence run.

The runtime now selects Earth Search v1 `sentinel-2-c1-l2a`. Its three existing
processing entrypoints accept only exact C1 item/asset/capture identities with
explicit finite calibration agreeing with the actual TIFF metadata. Field tenant,
polygon clip (maximum 1,000,000 target pixels), SCL and raw QA remain mandatory.
The direct route resolves catalogue metadata itself rather than trusting supplied
coefficients. The provider URI is allowlisted to the C1 bucket/item/band, and
VRT sidecars live only for the synchronous processing call.

**Legacy `sentinel-2-l2a` remains rejected.** Provider issue66 documents internally
contradictory BOA metadata; guessing a correction would be unsafe. This change does
not repair old products, run their inventory, or certify every C1 scene. API v2 is
not enabled. Collection1 coverage may differ; no silent fallback to legacy scenes.

Three dispatch witnesses fail on exact main router/worker source and pass after
repair. Twenty-four new tests cover real synthetic TIFF/VRT calibration, bounded
clipping, asset/tenant/QA rejection, all three entrypoints, bundle cleanup, and
captured-provider replay. Existing containment witnesses are preserved.

`provider/` contains eight public, real 64×64 window captures obtained on
2026-10-16 from C1 item `S2A_T38PNC_20261015T073428_L2A`, centred near
45.50E/16.15N in Al Jawf. Metadata, transforms and sample SHA256s are retained.
The seven reflectance TIFFs agree with STAC `scale=0.0001, offset=-0.1`; SCL is
categorical `1/0`. A replay through the real VRT, pixel processing, SCL QA,
validated-product contract and local COG writer produced EVI mean
`0.04385126754641533`, identical to an independently computed formula on direct
captured samples. Raw-DN EVI would be `0.08374159783124924`; applying the offset
twice would yield `0.042878955602645874`. 3,600 pixels survived polygon/QA.

This replay is reproducible offline in `test_stac_c1_processing.py`; it is not a
fresh live test on each CI run. Only source reads were redirected to captured
windows and output upload to local files. Pixel math, GDAL, QA, product validation
and COG writes were not mocked. No production job/catalogue write occurred.

Data attribution: contains modified Copernicus Sentinel data (2026), distributed
as Collection1 COGs by Element84 Earth Search. Windows are cropped original DN
samples with no reflectance transformation applied to the captured arrays.

Primary references:
- https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md
- https://github.com/Element84/earth-search/issues/66

The complete commands, read adapters, replay script, logs and resume notes remain
in the continuation workspace at `evidence/closure-nine/radiometry/`.
