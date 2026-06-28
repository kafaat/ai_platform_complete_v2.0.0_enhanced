"""WS-4 جودة الغيوم — يُثبت سدّ فجوتين في معالجة Sentinel-2:

1) ``cloud_pct`` (مسار Element84): حساب نسبة غيوم المشهد من نطاق SCL تركيبيّ
   بنسبة غيوم معلومة (``main.compute_cloud_pct`` — دالّة نقيّة بلا rasterio).
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
import main  # noqa: E402

pytestmark = pytest.mark.unit


# ─── (١) cloud_pct من SCL تركيبيّ ──────────────────────────────────
def test_compute_cloud_pct_known_fraction():
    """SCL تركيبيّ: 100 بكسل صالح، 25 منها غيوم ⇒ cloud_pct == 25.0."""
    # 25 بكسل صنف 9 (غيمة عالية) + 75 بكسل صنف 4 (غطاء نباتي، غير غيمة).
    scl = np.array([9] * 25 + [4] * 75, dtype=np.uint8)
    assert main.compute_cloud_pct(scl, np) == pytest.approx(25.0)


def test_compute_cloud_pct_excludes_nodata_from_denominator():
    """بكسلات SCL=0 (لا-بيانات) تُستبعَد من المقام.

    40 غيمة + 40 نبات + 20 لا-بيانات ⇒ المقام 80 ⇒ 40/80 = 50%.
    """
    scl = np.array([3] * 40 + [4] * 40 + [0] * 20, dtype=np.uint8)
    assert main.compute_cloud_pct(scl, np) == pytest.approx(50.0)


def test_compute_cloud_pct_all_cloud_classes_counted():
    """كلّ أصناف الغيوم {3,8,9,10,11} تُحسب غيوماً (بكسل لكلّ صنف من 5)."""
    scl = np.array([3, 8, 9, 10, 11], dtype=np.uint8)
    assert main.compute_cloud_pct(scl, np) == pytest.approx(100.0)
    # صنف غير-غيمة (صفّ صافٍ) ⇒ 0%.
    clear = np.array([4, 5, 6, 7], dtype=np.uint8)
    assert main.compute_cloud_pct(clear, np) == pytest.approx(0.0)


def test_compute_cloud_pct_no_valid_returns_none():
    """لا بكسلات صالحة (كلّها SCL=0) ⇒ None (تفادي القسمة على صفر)."""
    scl = np.zeros(16, dtype=np.uint8)
    assert main.compute_cloud_pct(scl, np) is None
    assert main.compute_cloud_pct(None, np) is None


def test_warn_threshold_is_positive_default():
    """عتبة التحذير الافتراضيّة موجبة (تُستخدم لإلحاق تحذير التلوّث بالغيوم)."""
    assert main.CLOUD_PCT_WARN_THRESHOLD > 0
    assert main.SCL_CLOUD_CLASSES == (3, 8, 9, 10, 11)


# ─── (٢) evalscript CDSE يقنّع الغيوم per-pixel ────────────────────
def test_cdse_evalscript_requests_scl_band():
    """النصّ يطلب نطاق "SCL" ضمن مدخلات setup() إلى جانب dataMask."""
    es = cdse_client.build_evalscript("ndvi")
    assert '"SCL"' in es
    assert '"dataMask"' in es


def test_cdse_evalscript_excludes_cloud_classes():
    """النصّ يستبعد أصناف الغيوم {3,8,9,10,11} ويُرجِع NaN عندها."""
    es = cdse_client.build_evalscript("ndvi")
    # مجموعة أصناف الغيوم مصرَّح بها في النصّ.
    assert "SCL_CLOUD = [3, 8, 9, 10, 11]" in es
    # منطق الاستبعاد: غيمة ⇒ NaN، ويستعمل s.SCL.
    assert "s.SCL" in es
    assert "isCloud" in es
    assert "NaN" in es
    # القناع يجمع dataMask مع استبعاد الغيوم.
    assert "s.dataMask === 1 && !isCloud" in es


def test_cdse_evalscript_cloud_classes_match_element84_path():
    """أصناف الغيوم في CDSE تطابق مسار Element84 (تماسُك المعالجة)."""
    assert cdse_client.SCL_CLOUD_CLASSES == main.SCL_CLOUD_CLASSES


def test_cdse_evalscript_pure_builder_all_indices():
    """باني النصّ نقيّ: كلّ مؤشّر مدعوم يُنتج نصّاً يحوي SCL + dataMask."""
    for idx in cdse_client.supported_indices():
        es = cdse_client.build_evalscript(idx)
        assert '"SCL"' in es and '"dataMask"' in es and "isCloud" in es
