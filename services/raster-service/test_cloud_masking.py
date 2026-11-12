"""WS-4 جودة الغيوم — يُثبت سدّ فجوتين في معالجة Sentinel-2:

1) ``cloud_pct`` (مسار Element84): حساب نسبة غيوم المشهد من نطاق SCL تركيبيّ
   بنسبة غيوم معلومة (``raster_quality.compute_cloud_pct`` — دالّة نقيّة بلا rasterio).
2) قناع الغيوم per-pixel في CDSE (``cdse_client.build_evalscript``): يطلب نطاق
   "SCL" ويستبعد أصناف الغيوم/الظلال/السيرس/الثلج (تأكيدات على النصّ).

صدق: تصحيح evalscript النهائيّ يحتاج تشغيلاً حقيقيّاً ضدّ CDSE Process API (تحقّق
ميدانيّ)؛ هذه الاختبارات تؤكّد بنية النصّ فقط — لا تستبدل التحقّق ضدّ الـAPI الحيّ.

محلّيّ بالكامل (بلا شبكة، بلا CDSE). يحتاج numpy فقط (لا rasterio).
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cdse_client  # noqa: E402
import raster_quality  # noqa: E402
import raster_settings  # noqa: E402

pytestmark = pytest.mark.unit


# ─── (١) cloud_pct من SCL تركيبيّ ──────────────────────────────────
def test_compute_cloud_pct_known_fraction():
    """SCL تركيبيّ: 100 بكسل صالح، 25 منها غيوم ⇒ cloud_pct == 25.0."""
    # 25 بكسل صنف 9 (غيمة عالية) + 75 بكسل صنف 4 (غطاء نباتي، غير غيمة).
    scl = np.array([9] * 25 + [4] * 75, dtype=np.uint8)
    assert raster_quality.compute_cloud_pct(
        scl, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES
    ) == pytest.approx(25.0)


def test_compute_cloud_pct_excludes_nodata_from_denominator():
    """بكسلات SCL=0 (لا-بيانات) تُستبعَد من المقام.

    40 غيمة + 40 نبات + 20 لا-بيانات ⇒ المقام 80 ⇒ 40/80 = 50%.
    """
    scl = np.array([3] * 40 + [4] * 40 + [0] * 20, dtype=np.uint8)
    assert raster_quality.compute_cloud_pct(
        scl, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES
    ) == pytest.approx(50.0)


def test_compute_cloud_pct_all_cloud_classes_counted():
    """كلّ أصناف الغيوم {3,8,9,10,11} تُحسب غيوماً (بكسل لكلّ صنف من 5)."""
    scl = np.array([3, 8, 9, 10, 11], dtype=np.uint8)
    assert raster_quality.compute_cloud_pct(
        scl, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES
    ) == pytest.approx(100.0)
    # صنف غير-غيمة (صفّ صافٍ) ⇒ 0%.
    clear = np.array([4, 5, 6, 7], dtype=np.uint8)
    assert raster_quality.compute_cloud_pct(
        clear, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES
    ) == pytest.approx(0.0)


def test_compute_cloud_pct_no_valid_returns_none():
    """لا بكسلات صالحة (كلّها SCL=0) ⇒ None (تفادي القسمة على صفر)."""
    scl = np.zeros(16, dtype=np.uint8)
    assert (
        raster_quality.compute_cloud_pct(scl, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES)
        is None
    )
    assert (
        raster_quality.compute_cloud_pct(None, np, cloud_classes=cdse_client.SCL_CLOUD_CLASSES)
        is None
    )


def test_warn_threshold_is_positive_default():
    """عتبة التحذير الافتراضيّة موجبة (تُستخدم لإلحاق تحذير التلوّث بالغيوم)."""
    assert raster_settings.CLOUD_PCT_WARN_THRESHOLD > 0
    assert cdse_client.SCL_CLOUD_CLASSES == (3, 8, 9, 10, 11)


# ─── (٢) evalscript CDSE يقنّع الغيوم per-pixel ────────────────────
def test_cdse_evalscript_requests_scl_band():
    """النصّ يطلب نطاق "SCL" ضمن مدخلات setup() إلى جانب dataMask."""
    es = cdse_client.build_evalscript("ndvi")
    assert '"SCL"' in es
    assert '"dataMask"' in es


def test_cdse_evalscript_excludes_cloud_classes():
    """النصّ يستبعد أصناف الغيوم {3,8,9,10,11} ويُرجِع NaN عندها."""
    es = cdse_client.build_evalscript("ndvi")
    assert "s.SCL" in es and "NaN" in es


def test_live_evalscript_masks_invalid_scl_and_nonfinite_scalar():
    """Execute both ordinary scripts; invalid classes never produce a visible pixel."""
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to run generated provider JavaScript")
    for name in ("msi", "truecolor"):
        script = cdse_client.build_evalscript(name)
        driver = """
            const s = {B02:.1,B03:.2,B04:.3,B08:.5,B11:.25,dataMask:1};
            const visible = p => p.length === 4 ? p[3] > 0 : Number.isFinite(p[0]);
            const labels = Array.from({length:12}, (_,i) => i).concat([-1,12,2.5,null]);
            const accepted = labels.filter(SCL => visible(evaluatePixel({...s,SCL})));
            const absent = visible(evaluatePixel({...s,SCL:4,dataMask:0}));
            const singular = evaluatePixel({...s,SCL:4,B08:0})[0];
            console.log(JSON.stringify({accepted,absent,singularIsNaN:Number.isNaN(singular)}));
        """
        result = subprocess.run(
            [node, "-"], input=script + driver, text=True, check=True, capture_output=True
        )
        observed = json.loads(result.stdout)
        assert observed["accepted"] == [2, 4, 5, 6, 7]
        assert observed["absent"] is False
        if name == "msi":
            assert observed["singularIsNaN"] is True


def test_cdse_evalscript_pure_builder_all_indices():
    """باني النصّ نقيّ: كلّ مؤشّر مدعوم يُنتج نصّاً يحوي SCL + dataMask."""
    for idx in cdse_client.supported_indices():
        es = cdse_client.build_evalscript(idx)
        assert '"SCL"' in es and '"dataMask"' in es and "s.SCL" in es


def test_ordinary_and_native_scripts_apply_physical_domain():
    """Run provider JS for valid controls, finite invalid ratios and SIPI endpoints."""
    import json
    import shutil
    import subprocess

    import cdse_native_product

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to run generated provider JavaScript")
    base = dict(B02=0.06, B03=0.2, B04=0.16, B05=0.25, B08=0.52, B11=0.28, SCL=4, dataMask=1)
    invalid = {
        "sipi": dict(B04=0.4, B08=0.41),
        "ccci": dict(B04=0.4, B08=0.41),
        "evi": dict(B02=0.25),
        "arvi": dict(B02=0.47),
        "vari": dict(B02=0.359),
        "msi": dict(B08=0.001),
        "reci": dict(B05=0.001),
        "gci": dict(B03=0.001),
        "gli": dict(B02=0.0006, B03=0.0007, B04=0.0008),
        "savi": dict(B04=-0.01),
    }
    jobs = []
    for name, change in invalid.items():
        samples = [base, base | change]
        if name == "sipi":
            for dns in ((2384, 3424, 4464), (2772, 4208, 5644), (2771, 4208, 5644)):
                bands = (np.asarray(dns, dtype="float32") * 0.0001 - 0.1).tolist()
                samples.append(base | dict(zip(("B02", "B04", "B08"), bands, strict=True)))
        for native in (False, True):
            script = (
                cdse_native_product.build_evalscript(name, cdse_client.INDEX_EXPR)
                if native
                else cdse_client.build_evalscript(name)
            )
            jobs.append(dict(name=name, script=script, samples=samples, native=native))
    driver = """
        const vm = require('node:vm');
        const jobs = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
        const values = jobs.map(j => {
            const ctx = vm.createContext({});
            vm.runInContext(j.script, ctx);
            return j.samples.map(s => ctx.evaluatePixel(j.native ? [s] : s)[0]);
        });
        console.log(JSON.stringify(values));
    """
    proc = subprocess.run(
        [node, "-e", driver], input=json.dumps(jobs), text=True, check=True, capture_output=True
    )
    for job, vals in zip(jobs, json.loads(proc.stdout), strict=True):
        assert np.isfinite(vals[0]), job["name"]
        assert vals[1] is None, job["name"]
        if job["name"] == "sipi":
            assert vals[2:4] == pytest.approx([2.0, 2.0])
            assert vals[4] is None
