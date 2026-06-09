"""
api/gdd_tracker.py — تتبّع درجات النموّ الحراريّة (GDD)

خارطة الطريق: المرحلة ٣، البند ١٥.

النموّ يُقاس بالحرارة المتراكمة لا بالأيّام. GDD يتنبّأ بمراحل المحصول
(إنبات، تفرّع، إزهار، نضج) بدقّة أعلى من التقويم — مهمّ لتوقيت الريّ
والتسميد والحصاد. يربط بـcrop_stages وKC_BY_CROP_STAGE في water_balance.

المعادلة المعياريّة:
  GDD_يومي = max(0, (Tmax + Tmin)/2 − T_base)
  مع تحديد سقف اختياري: لو Tmax > T_upper نقصّه إلى T_upper

T_base وعتبات المراحل تختلف حسب المحصول. القيم من أدبيّات الزراعة.

⚠ عتبات GDD تقديريّة (تختلف حسب الصنف والإقليم) — موسومة. تحتاج معايرة محلّيّة.
"""

from __future__ import annotations

from dataclasses import dataclass

# قواعد الحرارة وعتبات المراحل التراكميّة (°C·يوم)
# ⚠ قيم أدبيّات عامّة — تحتاج معايرة بالصنف اليمني والإقليم
# T_base = الحرارة تحت أيّ نموّ يتوقّف؛ stages = GDD تراكمي لبداية كلّ مرحلة
GDD_CROP_PARAMS: dict[str, dict] = {
    "wheat": {
        "t_base": 0.0,
        "t_upper": 30.0,
        "stages": [
            ("emergence", 120),
            ("tillering", 400),
            ("heading", 900),
            ("flowering", 1100),
            ("maturity", 1600),
        ],
    },
    "barley": {
        "t_base": 0.0,
        "t_upper": 30.0,
        "stages": [
            ("emergence", 110),
            ("tillering", 370),
            ("heading", 820),
            ("flowering", 1000),
            ("maturity", 1450),
        ],
    },
    "sorghum": {
        "t_base": 10.0,
        "t_upper": 38.0,
        "stages": [
            ("emergence", 100),
            ("vegetative", 450),
            ("flowering", 900),
            ("grain_fill", 1300),
            ("maturity", 1700),
        ],
    },
    "tomato": {
        "t_base": 10.0,
        "t_upper": 30.0,
        "stages": [
            ("emergence", 90),
            ("flowering", 550),
            ("fruit_set", 800),
            ("ripening", 1200),
            ("maturity", 1400),
        ],
    },
    "maize": {
        "t_base": 10.0,
        "t_upper": 30.0,
        "stages": [
            ("emergence", 120),
            ("vegetative", 500),
            ("silking", 900),
            ("grain_fill", 1300),
            ("maturity", 1600),
        ],
    },
}


@dataclass
class DailyTemp:
    """حرارة يوم واحد."""

    t_min_c: float
    t_max_c: float


@dataclass
class GDDResult:
    crop: str
    t_base: float
    days_counted: int
    cumulative_gdd: float
    current_stage: str
    next_stage: str | None
    gdd_to_next_stage: float | None
    stage_progress: list[dict]
    notes_ar: str

    def to_dict(self) -> dict:
        return {
            "crop": self.crop,
            "t_base": self.t_base,
            "days_counted": self.days_counted,
            "cumulative_gdd": round(self.cumulative_gdd, 1),
            "current_stage": self.current_stage,
            "next_stage": self.next_stage,
            "gdd_to_next_stage": round(self.gdd_to_next_stage, 1)
            if self.gdd_to_next_stage is not None
            else None,
            "stage_progress": self.stage_progress,
            "notes_ar": self.notes_ar,
        }


def daily_gdd(t_min: float, t_max: float, t_base: float, t_upper: float | None = None) -> float:
    """GDD ليوم واحد = max(0, (Tmax+Tmin)/2 − T_base) مع سقف اختياري."""
    tmax = min(t_max, t_upper) if t_upper is not None else t_max
    tmin = t_min
    # بعض المراجع تقصّ Tmin أيضاً عند T_base
    mean = (tmax + tmin) / 2
    return max(0.0, mean - t_base)


def track_gdd(crop: str, temps: list[DailyTemp]) -> GDDResult:
    """يتراكم GDD عبر سلسلة أيّام ويحدّد المرحلة الحاليّة.

    يرفع ValueError لو المحصول غير معروف.
    """
    params = GDD_CROP_PARAMS.get(crop)
    if params is None:
        raise ValueError(f"محصول غير معروف لـGDD: {crop}. المتاح: {list(GDD_CROP_PARAMS)}")
    t_base = params["t_base"]
    t_upper = params["t_upper"]
    stages: list[tuple[str, float]] = params["stages"]

    cumulative = 0.0
    for d in temps:
        cumulative += daily_gdd(d.t_min_c, d.t_max_c, t_base, t_upper)

    # حدّد المرحلة الحاليّة (آخر مرحلة بلغ GDD عتبتها)
    current = "planting"
    next_stage: str | None = stages[0][0] if stages else None
    gdd_to_next: float | None = stages[0][1] if stages else None
    for i, (name, threshold) in enumerate(stages):
        if cumulative >= threshold:
            current = name
            if i + 1 < len(stages):
                next_stage = stages[i + 1][0]
                gdd_to_next = stages[i + 1][1] - cumulative
            else:
                next_stage = None
                gdd_to_next = None
        else:
            next_stage = name
            gdd_to_next = threshold - cumulative
            break

    progress = [
        {"stage": name, "gdd_threshold": thr, "reached": cumulative >= thr} for name, thr in stages
    ]

    if next_stage:
        notes = (
            f"تراكم {cumulative:.0f} GDD خلال {len(temps)} يوم. "
            f"المرحلة الحاليّة: {current}. المتبقّي لـ{next_stage}: {gdd_to_next:.0f} GDD."
        )
    else:
        notes = f"تراكم {cumulative:.0f} GDD. بلغ المحصول النضج ({current})."

    return GDDResult(
        crop=crop,
        t_base=t_base,
        days_counted=len(temps),
        cumulative_gdd=cumulative,
        current_stage=current,
        next_stage=next_stage,
        gdd_to_next_stage=gdd_to_next,
        stage_progress=progress,
        notes_ar=notes,
    )
