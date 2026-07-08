"""core/eo_stage_mismatch.py — كاشف تعارض الاستشعار مع المرحلة (EO ↔ Stage) — VNext مكوّن #5.

يقارن ما **يُتوقَّع** من غطاء نباتيّ للمرحلة الطوريّة الحاليّة مع ما **يُرصَد** فعليّاً
(NDVI/NDMI). إن قال الموسم «نموّ نشط» (development/mid ⇒ NDVI مرتفع متوقّع) لكنّ NDVI
المرصود منخفض، **وجودة الصورة جيّدة** ⇒ تعارض (إجهاد/مشكلة محتملة). NDMI المنخفض يعزّز
تفسير الإجهاد المائيّ.

قاعدة صدق حاسمة (كما طُلِب): **جودة الصورة الضعيفة ⇒ لا إنذار قويّ** (سُحُب/بكسلات صالحة قليلة
⇒ inconclusive + ثقة منخفضة)؛ لا نُنذِر على صورة رديئة.

نطاقات NDVI المتوقّعة هنا **عامّة محايدة للمحصول وتقريبيّة** (مُعلَّمة) — الأقوى مستقبلاً استبدالها
بـ«أساس السلوك الطبيعيّ للحقل» (NDVI الطبيعيّ لهذا الحقل حسب الشهر/المرحلة/سنواته). يُصرَّح بذلك.

دالّة نقيّة (لا شبكة/قاعدة) — تُغذّي إسقاط حالة الحقل-الموسم (#5 الموحِّد) وبطاقة أدلّة الموسم.
"""

from __future__ import annotations

# نطاقات NDVI المتوقّعة لكلّ مرحلة (عامّة تقريبيّة — تُستبدَل لاحقاً بأساس الحقل نفسه).
_EXPECTED_NDVI: dict[str, tuple[float, float]] = {
    "initial": (0.10, 0.35),  # تربة عارية/بادرات
    "development": (0.35, 0.70),  # ارتفاع الغطاء
    "mid": (0.55, 0.90),  # ذروة الغطاء (التزهير/الإثمار)
    "late": (0.30, 0.65),  # شيخوخة/نضج (انخفاض طبيعيّ)
}
# المراحل التي يُنذَر فيها انخفاض NDVI (النشِطة)؛ الانخفاض في initial/late طبيعيّ.
_ACTIVE_STAGES = {"development", "mid"}
_NDMI_DRY = 0.10  # تحت هذا ⇒ إجهاد مائيّ يعزّز تفسير انخفاض NDVI
# عتبات جودة المشهد (فوق/تحتها ⇒ ضعيف ⇒ لا إنذار قويّ).
_MIN_VALID_PIXEL_RATIO = 0.60
_MAX_CLOUD_PCT = 35.0


def _scene_quality_ok(valid_pixel_ratio: float | None, cloud_pct: float | None) -> bool | None:
    """جودة المشهد: True جيّدة / False ضعيفة / None غير معروفة (لا إشارات جودة)."""
    if valid_pixel_ratio is None and cloud_pct is None:
        return None
    if valid_pixel_ratio is not None and valid_pixel_ratio < _MIN_VALID_PIXEL_RATIO:
        return False
    if cloud_pct is not None and cloud_pct > _MAX_CLOUD_PCT:
        return False
    return True


def detect_eo_stage_mismatch(
    stage: str | None,
    observed_ndvi: float | None,
    observed_ndmi: float | None = None,
    *,
    valid_pixel_ratio: float | None = None,
    cloud_pct: float | None = None,
) -> dict:
    """يكشف تعارض الغطاء المرصود مع المتوقّع للمرحلة، بحارس جودة صورة صادق.

    يُعيد: ``status`` (aligned/below_expected/above_expected/inconclusive)، ``severity``،
    ``corroborated_by_ndmi``، ``scene_quality_ok``، ``expected_ndvi_range``، ``reason_ar``،
    ``confidence``، ``evidence_used``/``evidence_missing``.
    """
    used = []
    if observed_ndvi is not None:
        used.append("ndvi")
    if observed_ndmi is not None:
        used.append("ndmi")
    if valid_pixel_ratio is not None:
        used.append("valid_pixel_ratio")
    if cloud_pct is not None:
        used.append("cloud_pct")

    base = {
        "stage": stage,
        "observed_ndvi": observed_ndvi,
        "observed_ndmi": observed_ndmi,
        "expected_ndvi_range": _EXPECTED_NDVI.get(stage) if stage else None,
        "scene_quality_ok": _scene_quality_ok(valid_pixel_ratio, cloud_pct),
        "corroborated_by_ndmi": False,
        "evidence_used": used,
        "baseline_note_ar": (
            "النطاقات عامّة تقريبيّة — الأقوى مستقبلاً «أساس السلوك الطبيعيّ للحقل» (تاريخه نفسه)."
        ),
    }

    if stage is None or stage not in _EXPECTED_NDVI:
        return {
            **base,
            "status": "inconclusive",
            "severity": "none",
            "confidence": "low",
            "evidence_missing": ["current_stage"],
            "reason_ar": "لا مرحلة طوريّة معروفة — يتعذّر مقارنة الغطاء بالمتوقّع.",
        }
    if observed_ndvi is None:
        return {
            **base,
            "status": "inconclusive",
            "severity": "none",
            "confidence": "low",
            "evidence_missing": ["ndvi"],
            "reason_ar": "لا NDVI مرصود — يتعذّر كشف التعارض.",
        }

    # حارس جودة الصورة: الضعيفة ⇒ لا إنذار قويّ (قاعدة صدق).
    if base["scene_quality_ok"] is False:
        return {
            **base,
            "status": "inconclusive",
            "severity": "none",
            "confidence": "low",
            "evidence_missing": [],
            "reason_ar": (
                "جودة الصورة ضعيفة (سُحُب/بكسلات صالحة قليلة) — لا إنذار قويّ؛ انتظر مشهداً أنقى."
            ),
        }

    low, high = _EXPECTED_NDVI[stage]
    ndmi_dry = observed_ndmi is not None and observed_ndmi < _NDMI_DRY
    base["corroborated_by_ndmi"] = ndmi_dry
    # الثقة سقفها MEDIUM؛ تنزل قليلاً إن غابت جودة الصورة (لم تُؤكَّد).
    conf = "medium" if base["scene_quality_ok"] is True else "low"
    missing = [] if base["scene_quality_ok"] is not None else ["scene_quality"]

    if observed_ndvi < low:
        if stage in _ACTIVE_STAGES:
            severity = "high" if ndmi_dry else "medium"
            reason = (
                f"مرحلة نشطة ({stage}) تتوقّع NDVI ≥ {low} لكنّ المرصود {observed_ndvi} — "
                f"تعارض يشير لإجهاد/مشكلة"
                + ("، ويعزّزه NDMI منخفض (إجهاد مائيّ)." if ndmi_dry else ".")
            )
            status = "below_expected"
        else:
            severity, status = "low", "aligned"  # انخفاض طبيعيّ في initial/late
            reason = f"NDVI {observed_ndvi} منخفض لكنّه متوقّع في مرحلة {stage} (لا إنذار)."
    elif observed_ndvi > high:
        severity, status = "low", "above_expected"
        reason = (
            f"NDVI {observed_ndvi} أعلى من المتوقّع ({high}) للمرحلة — "
            "قد يشير لحشائش/خطأ مرحلة (تحقّق)."
        )
    else:
        severity, status = "none", "aligned"
        reason = f"NDVI {observed_ndvi} ضمن المتوقّع للمرحلة ({low}–{high}) — متّسق."

    return {
        **base,
        "status": status,
        "severity": severity,
        "confidence": conf,
        "evidence_missing": missing,
        "reason_ar": reason,
    }
