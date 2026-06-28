"""api/field_sustainability.py — مؤشّر استدامة الحقل (Field Sustainability Index).

الغرض:
   درجة **واحدة مُفسَّرة** لكلّ حقل عبر ثلاثة أبعاد — **تربة + مياه + مغذّيات** (بلا كربون):
   «كم إدارة هذا الحقل مستدامة؟». تجميع نقيّ من إشارات **موجودة أصلاً** (لا حساب جديد، لا
   اختلاق): يُعيد استخدام `salinity_class`/`water_stress_class` الكنسيّين + تحليل التربة (pH/
   مادة عضويّة) + نضارة التحليل.

صدق صريح — ما هذا وما ليس هو:
   - **تجميع لا قرار:** معلوماتيّ بحت، لا يغيّر `validity`/`execution_mode`.
   - **يُعيد استخدام لا يكرّر:** `salinity_class`/`water_stress_class` يُؤخَذان من الحالة
     القانونيّة كما هما (لا إعادة حساب).
   - **المغذّيات `needs_data` بصدق:** توازن NPK الكامل **غير مقيس** (P محجوب بلا تحليل، K
     معطّل، N غير معايَر) ⇒ بُعد المغذّيات لا يُسجَّل درجةً (`score=None`)، يُعلَن صراحةً —
     **لا «NPK Index» مُلفَّق**. يُستبعَد من المتوسّط (لا عقاب على ما لا يُقاس).
   - **أوزان/عتبات مُعلَنة لا معايَرة:** موسوم `calibrated=False`. **بلا كربون** صراحةً.
   - دالّة **نقيّة** (لا I/O)، fail-safe: مدخل غير صالح ⇒ كتلة insufficient (لا رمي).
"""

from __future__ import annotations

# أوزان الأبعاد (مُعلَنة، غير معايَرة) — تُعاد تسويتها على الأبعاد المتاحة فقط.
_WEIGHTS = {"soil": 0.45, "water": 0.35, "nutrients": 0.20}

# يُعاد استخدامهما من الحالة القانونيّة (لا حساب).
_SALINITY_SCORE = {"low": 1.0, "moderate": 0.5, "critical": 0.1}
_STRESS_SCORE = {"normal": 1.0, "watch": 0.6, "critical": 0.2}

# نضارة تحليل التربة (نظير عتبات field_readiness الموسميّة).
_SOIL_FRESH_D, _SOIL_STALE_D = 90.0, 365.0

_LEVELS = ((80.0, "excellent"), (60.0, "good"), (40.0, "fair"), (20.0, "poor"))

_NUTRIENT_NOTE = (
    "توازن NPK غير مقيس — P محجوب (لا تحليل)، K معطّل، N غير معايَر؛ أضِف تحليل تربة كامل (N/P/K)."
)


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ramp(age, fresh, stale):
    a = _num(age)
    if a is None:
        return None
    if a <= fresh:
        return 1.0
    if a >= stale:
        return 0.0
    return round(1.0 - (a - fresh) / (stale - fresh), 3)


def _ph_score(ph):
    """درجة pH (عتبات مُعلَنة): مثاليّ 6.0–7.5؛ كلسيّ/حمضيّ أدنى. None ⇒ None."""
    p = _num(ph)
    if p is None:
        return None
    if 6.0 <= p <= 7.5:
        return 1.0
    if 5.5 <= p < 6.0 or 7.5 < p <= 7.8:
        return 0.7
    return 0.4  # حمضيّ <5.5 أو كلسيّ >7.8 (شائع في اليمن)


def _om_score(om):
    """درجة المادة العضويّة % (عتبات مُعلَنة): ≥2 جيّد، 1–2 متوسّط، <1 ضعيف."""
    o = _num(om)
    if o is None:
        return None
    if o >= 2.0:
        return 1.0
    if o >= 1.0:
        return 0.6
    return 0.3


def _mean(vals):
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def compute_field_sustainability(signals: dict | None) -> dict:
    """يحسب مؤشّر استدامة الحقل من إشارات مُجمَّعة. مدخل فاسد ⇒ كتلة insufficient.

    المُدخل ``signals`` (يجمعه المستدعي): ``salinity_class`` · ``ph`` · ``organic_matter``
    · ``soil_age_days`` · ``water_stress_class`` · ``water_use_efficiency`` (اختياريّ) ·
    ``n_kg_ha``/``p_ppm``/``k_mg_kg`` (معلوماتيّ — المغذّيات needs_data).
    """
    if not isinstance(signals, dict):
        signals = {}

    # ── بُعد التربة (يُعاد استخدام salinity_class) ──
    sal_cls = signals.get("salinity_class")
    salinity = _SALINITY_SCORE.get(sal_cls) if isinstance(sal_cls, str) else None
    ph_val = _num(signals.get("ph"))
    om_val = _num(signals.get("organic_matter"))
    soil_age = _num(signals.get("soil_age_days"))
    soil = _mean(
        [
            salinity,
            _ph_score(ph_val),
            _om_score(om_val),
            _ramp(soil_age, _SOIL_FRESH_D, _SOIL_STALE_D),
        ]
    )

    # ── بُعد المياه (يُعاد استخدام water_stress_class) ──
    ws_cls = signals.get("water_stress_class")
    water_stress = _STRESS_SCORE.get(ws_cls) if isinstance(ws_cls, str) else None
    wue = _num(signals.get("water_use_efficiency"))  # اختياريّ، 0..1
    water = _mean([water_stress, wue])

    # ── بُعد المغذّيات: needs_data بصدق (NPK غير مقيس) — score=None (مُستبعَد) ──
    n_avail, p_avail, k_avail = (
        _num(signals.get("n_kg_ha")),
        _num(signals.get("p_ppm")),
        _num(signals.get("k_mg_kg")),
    )

    dims = {"soil": soil, "water": water, "nutrients": None}
    avail = {k: v for k, v in dims.items() if v is not None}
    if avail:
        wsum = sum(_WEIGHTS[k] for k in avail)
        overall = round(100.0 * sum(_WEIGHTS[k] * v for k, v in avail.items()) / wsum, 1)
    else:
        overall = 0.0
    level = "insufficient"
    for threshold, name in _LEVELS:
        if overall >= threshold:
            level = name
            break

    return {
        "overall_score": overall,
        "level": level,
        "dimensions": {
            "soil": {
                "score": round(soil, 3) if soil is not None else None,
                "salinity_class": sal_cls if isinstance(sal_cls, str) else None,
                "ph": ph_val,
                "organic_matter": om_val,
                "soil_age_days": soil_age,
            },
            "water": {
                "score": round(water, 3) if water is not None else None,
                "water_stress_class": ws_cls if isinstance(ws_cls, str) else None,
                "water_use_efficiency": wue,
            },
            "nutrients": {
                "score": None,
                "status": "needs_data",
                "n_available": n_avail,
                "p_available": p_avail,
                "k_available": k_avail,
                "note_ar": _NUTRIENT_NOTE,
            },
        },
        "needs_ar": _needs(soil, water, soil_age),
        "carbon": "excluded",  # بلا كربون صراحةً (لا قيمة للمزارع اليمنيّ، بيانات غائبة)
        "calibrated": False,
        "source": "field_state.canonical + soil_lab",
    }


def _needs(soil, water, soil_age) -> list[str]:
    """إرشاد عمليّ صادق لرفع الاستدامة (يبدأ بأكبر الفجوات)."""
    out: list[str] = []
    out.append("أضِف تحليل تربة كامل (N/P/K) لقياس استدامة المغذّيات")  # المغذّيات دائماً needs_data
    if soil is None:
        out.append("أضِف تحليل تربة (pH/مادة عضويّة) — لا بيانات تربة")
    elif soil_age is not None and soil_age > _SOIL_STALE_D * 0.7:
        out.append("حدِّث تحليل التربة (قديم)")
    if water is None:
        out.append("سجّل دفتر المياه لتقييم استدامة الريّ")
    return out[:3]
