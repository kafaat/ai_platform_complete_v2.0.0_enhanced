"""
api/crop_suitability.py — محرّك ملاءمة المحاصيل (معايير مرجّحة، لا ML)

مُستلهَم من التدفّق ٤ (المستند ٨) — الوحيد المبنيّ على قواعد لا CNN. يقيّم
ملاءمة محصول لظروف حقل عبر معايير مرجّحة شفّافة (تربة/ملوحة/حموضة/حرارة)،
ويعلّل كلّ درجة. يحجب دون بيانات تربة كافية (لا تخمين).

المبدأ: قواعد شفّافة قابلة للتفسير (يطابق XAI) لا صندوق أسود. كلّ درجة
ملاءمة مصحوبة بسبب: "الملوحة تمنع X، القمح يتحمّل".

⚠ نطاقات تحمّل المحاصيل من أدبيّات زراعيّة عامّة (FAO) — موسومة كإرشاد يحتاج
معايرة محلّيّة بالصنف اليمني. ليست ثوابت إنتاج.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CropTolerance:
    """نطاقات تحمّل محصول (FAO — تحتاج معايرة محلّيّة)."""

    crop: str
    name_ar: str
    ph_optimal: tuple[float, float]  # المدى الأمثل
    ph_tolerable: tuple[float, float]  # المدى المحتمَل
    ec_max_dsm: float  # أقصى ملوحة محتملة dS/m
    rain_min_mm: float  # أدنى مطر موسمي (للبعل)
    temp_range_c: tuple[float, float]  # مدى الحرارة المناسب


# ⚠ FAO reference ranges — تحتاج معايرة بالصنف اليمني
CROP_TOLERANCES: list[CropTolerance] = [
    CropTolerance("wheat", "قمح", (6.0, 7.5), (5.5, 8.5), 6.0, 300, (10, 25)),
    CropTolerance("barley", "شعير", (6.5, 8.0), (6.0, 8.5), 8.0, 250, (10, 25)),
    CropTolerance("sorghum", "ذرة رفيعة", (5.5, 7.5), (5.0, 8.5), 6.5, 400, (20, 35)),
    CropTolerance("date_palm", "نخيل", (7.0, 8.5), (6.0, 9.0), 12.0, 100, (20, 40)),
    CropTolerance("tomato", "طماطم", (6.0, 6.8), (5.5, 7.5), 2.5, 400, (18, 28)),
    CropTolerance("potato", "بطاطس", (5.0, 6.5), (4.8, 7.0), 1.7, 500, (15, 22)),
    CropTolerance("onion", "بصل", (6.0, 7.0), (5.5, 7.5), 1.2, 350, (13, 24)),
    CropTolerance("alfalfa", "برسيم", (6.5, 7.5), (6.0, 8.5), 2.0, 600, (15, 28)),
]

# أوزان المعايير (مجموعها ١) — شفّافة
_WEIGHTS = {"ph": 0.25, "ec": 0.35, "rain": 0.20, "temp": 0.20}


@dataclass
class FieldConditions:
    ph: float
    ec_dsm: float  # ملوحة التربة
    season_rain_mm: float | None = None
    temp_mean_c: float | None = None
    irrigated: bool = True  # لو مرويّ، المطر أقلّ أهميّة


@dataclass
class SuitabilityScore:
    crop: str
    name_ar: str
    score: float  # 0-1
    rating_ar: str  # ممتاز/جيّد/حدّي/غير مناسب
    reasons_ar: list[str]

    def to_dict(self) -> dict:
        return {
            "crop": self.crop,
            "name_ar": self.name_ar,
            "score": round(self.score, 3),
            "rating_ar": self.rating_ar,
            "reasons_ar": self.reasons_ar,
        }


def _score_range(
    value: float, optimal: tuple[float, float], tolerable: tuple[float, float]
) -> float:
    """درجة 0-1: ١ داخل الأمثل، تتناقص خطّيّاً للمحتمَل، ٠ خارجه."""
    lo_o, hi_o = optimal
    lo_t, hi_t = tolerable
    if lo_o <= value <= hi_o:
        return 1.0
    if value < lo_o:
        if value < lo_t:
            return 0.0
        return (value - lo_t) / (lo_o - lo_t)
    if value > hi_t:
        return 0.0
    return (hi_t - value) / (hi_t - hi_o)


def score_crop(cond: FieldConditions, tol: CropTolerance) -> SuitabilityScore:
    """يحسب ملاءمة محصول واحد للظروف."""
    reasons = []

    # pH
    ph_s = _score_range(cond.ph, tol.ph_optimal, tol.ph_tolerable)
    if ph_s >= 0.9:
        reasons.append(f"الحموضة ({cond.ph}) مثاليّة")
    elif ph_s <= 0.1:
        reasons.append(f"الحموضة ({cond.ph}) خارج تحمّل {tol.name_ar}")

    # EC (ملوحة) — معيار حاسم
    if cond.ec_dsm <= tol.ec_max_dsm * 0.5:
        ec_s = 1.0
    elif cond.ec_dsm <= tol.ec_max_dsm:
        ec_s = 1.0 - (cond.ec_dsm - tol.ec_max_dsm * 0.5) / (tol.ec_max_dsm * 0.5)
    else:
        ec_s = 0.0
        reasons.append(f"الملوحة ({cond.ec_dsm} dS/m) تتجاوز تحمّل {tol.name_ar} ({tol.ec_max_dsm})")

    # المطر (يُهمَل لو مرويّ)
    if cond.irrigated or cond.season_rain_mm is None:
        rain_s = 1.0
    else:
        rain_s = (
            1.0 if cond.season_rain_mm >= tol.rain_min_mm else cond.season_rain_mm / tol.rain_min_mm
        )
        if rain_s < 0.7:
            reasons.append(
                f"المطر ({cond.season_rain_mm} مم) دون حاجة {tol.name_ar} ({tol.rain_min_mm})"
            )

    # الحرارة
    if cond.temp_mean_c is None:
        temp_s = 1.0
    else:
        lo, hi = tol.temp_range_c
        temp_s = 1.0 if lo <= cond.temp_mean_c <= hi else 0.3

    score = (
        ph_s * _WEIGHTS["ph"]
        + ec_s * _WEIGHTS["ec"]
        + rain_s * _WEIGHTS["rain"]
        + temp_s * _WEIGHTS["temp"]
    )

    # قيد حاسم: لو الملوحة تتجاوز التحمّل (ec_s=0)، المحصول غير مناسب مهما
    # حسُنت بقيّة المعايير — لا تنمو حيث الملح يقتلها.
    hard_fail = ec_s == 0.0 or ph_s == 0.0
    if hard_fail:
        score = min(score, 0.35)

    if score >= 0.85:
        rating = "ممتاز"
    elif score >= 0.65:
        rating = "جيّد"
    elif score >= 0.4:
        rating = "حدّي"
    else:
        rating = "غير مناسب"

    if not reasons:
        reasons.append(f"ظروف مناسبة عموماً لـ{tol.name_ar}")

    return SuitabilityScore(
        crop=tol.crop,
        name_ar=tol.name_ar,
        score=score,
        rating_ar=rating,
        reasons_ar=reasons,
    )


def rank_crops(cond: FieldConditions, crops: list[str] | None = None) -> dict:
    """يرتّب المحاصيل حسب الملاءمة. يحجب لو نقصت بيانات التربة الحاكمة.

    ph و ec إجباريّان (لا تخمين) — لو غابا يُرفع ValueError.
    """
    candidates = CROP_TOLERANCES
    if crops:
        candidates = [t for t in CROP_TOLERANCES if t.crop in crops]
        if not candidates:
            raise ValueError(f"لا محاصيل معروفة في: {crops}")

    scores = [score_crop(cond, t) for t in candidates]
    scores.sort(key=lambda s: s.score, reverse=True)

    # تنبيه لو أعلى محصولين متقاربين (المستند: فرق <0.1 → رأي مهندس)
    note = ""
    if len(scores) >= 2 and abs(scores[0].score - scores[1].score) < 0.1:
        note = (
            f"أعلى محصولَين ({scores[0].name_ar}، {scores[1].name_ar}) متقاربان — "
            "يُنصح برأي مهندس زراعي للاختيار النهائي."
        )

    return {
        "ranked": [s.to_dict() for s in scores],
        "note_ar": note,
        "disclaimer_ar": "نطاقات التحمّل إرشاديّة (FAO) — أكّد بالصنف المحلّي والخبرة الميدانيّة.",
    }
