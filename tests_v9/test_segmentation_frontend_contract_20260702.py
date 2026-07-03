"""حارس عقد التقطيع بين الواجهة والخدمة (frontend ↔ field-segmentation) + توكيل المنصّة.

يُثبّت في CI إصلاحَي علّتين حقيقيّتين ظهرتا في تشغيل حيّ (SAM2 على المضيف):

  1) عدم تطابق الأسماء: الواجهة (`SegmentFieldInput` في `api.ts`) ترسل `bbox`/`hints`،
     بينما العقد الداخليّ مع خادم الاستدلال يستخدم `field_bbox`/`user_polygon`. بلا
     قبولٍ للاسمين يبقى `field_bbox=None` فيردّ SAM2 خطأ 422 (no_image_and_no_bbox).
     الإصلاح: `SegmentRequest` يقبل الاسمين، والمُعالِج يحلّهما
     (`req.field_bbox or req.bbox` / `req.user_polygon or req.hints`) قبل تمريرهما.

  2) `SAHOOL_AGENT_TOKEN` غائب عن كتلة بيئة `sahool-platform` في compose. المنصّة تحقن
     `X-Agent-Token` عبر `service_proxy._service_token()` الذي يرفع 503 بدون التوكن — قبل
     أن يصل الطلب إلى الخدمة. الإصلاح: إضافته لكتلة المنصّة (`:?required`، يفشل الإقلاع بوضوح).

مسح ساكن + استيراد الوحدة (importorskip للتبعيّات الغائبة في طبقة CI الدنيا).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_SVC_DIR = _ROOT / "services" / "field-segmentation"
_SEG_MAIN = _SVC_DIR / "main.py"


def _load_seg_main():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    if str(_SVC_DIR) not in sys.path:
        sys.path.insert(0, str(_SVC_DIR))
    # اسم 'main' عامّ عبر الخدمات — أخلِ أيّ نسخة سابقة لغير field-segmentation.
    mod = sys.modules.get("main")
    if mod is not None and "field-segmentation" not in getattr(mod, "__file__", "").replace(
        "\\", "/"
    ):
        sys.modules.pop("main", None)
    import main

    assert hasattr(main, "SegmentRequest"), "استُورِدت وحدة main لخدمة أخرى (تصادم اسم)"
    return main


# ── العلّة 1: SegmentRequest يقبل أسماء الواجهة (bbox/hints) + المُعالِج يحلّها ──────
def test_segment_request_accepts_frontend_field_names():
    main = _load_seg_main()
    # الواجهة ترسل bbox/hints؛ يجب أن يقبلهما النموذج بلا خطأ تحقّق.
    r = main.SegmentRequest(mode="auto", bbox=[46.0, 24.0, 46.1, 24.1], hints=[[46.0, 24.0]])
    assert r.bbox == [46.0, 24.0, 46.1, 24.1], "الحقل bbox (اسم الواجهة) غير مقبول"
    assert r.hints == [[46.0, 24.0]], "الحقل hints (اسم الواجهة) غير مقبول"


def test_segment_endpoint_resolves_frontend_aliases():
    # مسح ساكن: المُعالِج يوحّد أسماء الواجهة نحو العقد الداخليّ قبل تمريرها للنموذج.
    src = _SEG_MAIN.read_text(encoding="utf-8")
    assert "req.field_bbox or req.bbox" in src, "المُعالِج لا يحلّ bbox الواجهة نحو field_bbox"
    assert "req.user_polygon or req.hints" in src, "المُعالِج لا يحلّ hints الواجهة نحو user_polygon"


# ── العلّة 2: المنصّة تحمل SAHOOL_AGENT_TOKEN (وإلّا service_proxy يردّ 503) ──────
def test_platform_has_agent_token_for_service_proxy():
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((_ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    env = compose["services"]["sahool-platform"]["environment"]
    token = env.get("SAHOOL_AGENT_TOKEN")
    assert token, "sahool-platform تفتقد SAHOOL_AGENT_TOKEN ⇒ service_proxy يردّ 503 قبل الخدمة"
    assert "SAHOOL_AGENT_TOKEN" in str(token), "قيمة التوكن يجب أن تُشتقّ من متغيّر البيئة"


# ── تحسين مُستلهَم (بحث FTW/OpenFarm): تمرير درجة ثقة SAM2 «اقتراح ثمّ قبول» ──────
def test_sam2_confidence_flows_end_to_end():
    """درجة ثقة SAM2 تُخرَج من الاستدلال → تُمرَّر عبر field-segmentation → تُعرَض في الواجهة.

    الواجهة كانت جاهزة لعرضها (ثقة ٪) لكنّ الخلفيّة كانت تُسقِطها؛ الحارس يمنع الانحدار.
    """
    sam2 = (_ROOT / "services" / "sam2-inference" / "main.py").read_text(encoding="utf-8")
    assert '"confidence": confidence' in sam2, "sam2-inference لا يُخرِج درجة الثقة"

    seg = _SEG_MAIN.read_text(encoding="utf-8")
    assert 'body["confidence"]' in seg, "field-segmentation لا يستخرج درجة الثقة من الخادم"
    assert '"confidence": confidence' in seg, "field-segmentation لا يُمرِّر الثقة في الاستجابة"

    ui = (_ROOT / "frontend" / "src" / "components" / "AddFieldWithMap.tsx").read_text(
        encoding="utf-8"
    )
    assert "res?.confidence" in ui, "الواجهة لا تقرأ درجة الثقة من نتيجة التقطيع"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
