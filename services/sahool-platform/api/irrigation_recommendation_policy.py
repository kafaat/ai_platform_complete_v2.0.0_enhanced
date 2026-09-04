"""سياسة توصية الريّ المشروطة بالملوحة (H5) — دالّة نقيّة قابلة للضبط والاختبار.

توحّد صيغتَي الريّ (مع/بلا ملوحة) في **سياسة واحدة** تختار بحسب **توفّر البيانات**،
وتتدهور بصدق عند نقصها (لا تُضيف ماءً ولا تُخفيه دون أساس):

  1. ``net`` دائماً (FAO-56: ETc − المطر الفعّال) عبر ``weather_advice.irrigation_advice``.
  2. **إجهاد الملوحة Ks** (Maas-Hoffman) يُطبَّق على الاحتياج الصافي حين يتوفّر فحص EC
     مخبريّ موثوق (حديث) + عتبة تحمّل المحصول معروفة.
  3. **كسر الغسل (leaching) مشروط**: يُضاف **فقط** عند توفّر (ECw ماء الريّ + صرف مقبول
     + كفاءة ريّ). نقص أيٍّ منها ⇒ لا غسل (تجنّب إفراط ريّ دون أساس).
  4. **ملوحة حرجة بلا بيانات غسل** ⇒ ``blocked_for_review`` (يحتاج خبيراً — لا نُخرج خطّة
     غسل مسؤولة دون صرف/ECw).

السياسات الأربع: ``net_only`` · ``salinity_adjusted`` · ``salinity_with_leaching`` ·
``blocked_for_review``. كلٌّ يُعيد الأرقام الثلاثة (net/leaching/gross) + ``requires_expert_review``.

**صدق:** هذه السياسة برمجيّة قابلة للضبط، لكنّ ربط القيم بمستوى ملوحة فعليّ يحتاج
**معايرة ميدانيّة** (عيّنات EC أرضيّة) — تبقى ``fixed`` لا ``verified``.
"""

from __future__ import annotations

import os

from core.engines.fao56 import leaching_requirement
from core.thresholds import SALINITY_CRITICAL_ECE, SALINITY_MODERATE_ECE

from .irrigation_policy import IrrigationPolicy, policy_params
from .weather_advice import irrigation_advice

# كفاءة ريّ افتراضيّة (تنقيط/رشّ نموذجيّ) حين لا تُمرَّر — مُعلَنة في المخرَج.
DEFAULT_IRRIGATION_EFFICIENCY = 0.85
# نافذة موثوقيّة فحص EC المخبريّ: أقدم منها ⇒ يُعدّ غير موثوق (لا تصحيح ملوحة).
DEFAULT_EC_MAX_AGE_DAYS = 365
# صرفٌ يسمح بالغسل (الغسل يحتاج صرفاً كافياً؛ البطيء يحبس الأملاح فلا نضيف ماءً).
_DRAINAGE_OK = {"fast", "medium"}
# قيم env التي تُجبر المسار الصافي فقط (تعطيل سياسة الملوحة عمداً).
_FORCE_NET_ONLY = {"0", "false", "off", "no", "net_only", "disabled"}


def salinity_policy_forced_off(env_value: str | None) -> bool:
    """هل تُجبَر سياسة الملوحة على ``net_only`` عبر العلم؟ (افتراضيّ: آليّ بحسب البيانات).

    دالّة نقيّة — تُمرَّر قيمة ``SAHOOL_IRRIGATION_SALINITY_POLICY`` صراحةً (لا وصول env).
    """
    return (env_value or "").strip().lower() in _FORCE_NET_ONLY


def recommend_irrigation(
    *,
    et0_mm: float,
    crop: str | None,
    stage: str = "mid",
    # **لا افتراضَ صفراً هنا.** «لا بياناتِ مطر» ليست «لا مطر»: الصفرُ المُقنَّع يُنقِص
    # المطروحَ من الحاجة فيرفع الكمّيّةَ الموصى بها — أي أنّ الانحياز في اتّجاه
    # **الإذن بالريّ**، وهو الاتّجاه الذي يُغرِق. وقد أُغلِق هذا الصنفُ في
    # `recommendations_hub` (`required_inputs` تضمّ المطرَ) وفي
    # `routers/fields.py` (٥٠٣ عند نقص المطر) — وبقي مفتوحاً هنا.
    #
    # و`None` تصل النواةَ ⇒ **استثناء**، لا حسابٌ بقيمةٍ بديلة: الرفضُ عند الحدّ
    # يجعل كلَّ مسارٍ يُقرّر صراحةً ماذا يفعل بالغياب، بدل أن يرثه صامتاً.
    rain_recent_mm: float | None = None,
    forecast_rain_mm: float | None = None,
    soil_moisture_pct: float | None = None,
    kc_override: float | None = None,
    # ── مدخلات الملوحة (فحص مخبريّ) ──
    soil_ece: float | None = None,
    soil_ec_age_days: int | None = None,
    crop_salt_tolerance_ece: float | None = None,
    salt_slope_pct: float | None = None,
    # ── مدخلات الغسل (مشروطة) ──
    water_ec: float | None = None,
    drainage: str | None = None,
    irrigation_efficiency: float | None = None,
    # ── مدخلات الإجهاد المائيّ / استنزاف منطقة الجذور (FAO-56) — تقود قرار الإطلاق ──
    depletion_mm: float | None = None,
    taw_mm: float | None = None,
    raw_fraction: float = 0.5,
    water_stress_class: str | None = None,
    # ── سياسة الريّ (مقابض الإطلاق/الملء) ──
    policy: IrrigationPolicy | str | None = None,
    water_price_per_m3: float | None = None,
    yield_value_per_ha: float | None = None,
    # ── ضبط ──
    force_net_only: bool | None = None,
    ec_max_age_days: int = DEFAULT_EC_MAX_AGE_DAYS,
) -> dict:
    """يُرجِع توصية ريّ موحَّدة تختار الصيغة بحسب توفّر بيانات الملوحة.

    Args (المهمّة):
        et0_mm: التبخّر-نتح المرجعيّ اليوميّ (FAO-56) — محسوب مسبقاً.
        crop/stage/soil_moisture_pct/kc_override: تُمرَّر كما هي إلى ``irrigation_advice``.
        rain_recent_mm/forecast_rain_mm: **إلزاميّتان** (mm). ``None`` ⇒ ``ValueError``
            — لا حسابَ على مطرٍ مفقود، ولا تصفيرَ له. على كلّ مسارٍ أن يُقرّر ما يفعله
            بالغياب صراحةً (٥٠٣ / ``dependency_unavailable``)، لا أن يرثه صامتاً.
        soil_ece: ECe من فحص مخبريّ (dS/m). None ⇒ لا تقييم ملوحة (``net_only``).
        soil_ec_age_days: عُمر الفحص بالأيّام. أقدم من ``ec_max_age_days`` ⇒ غير موثوق.
        crop_salt_tolerance_ece: عتبة المحصول (FAO-56 T23). None ⇒ لا تصحيح ملوحة.
        water_ec: ECw ماء الريّ (dS/m) — مطلوب لحساب الغسل.
        drainage: ``fast``/``medium``/``slow`` — الغسل يحتاج صرفاً غير بطيء.
        irrigation_efficiency: كفاءة الريّ (0..1). None ⇒ افتراضيّ معلَن 0.85.
        depletion_mm: استنزاف منطقة الجذور Dr (من ``water_ledger`` عبر الحالة الكنسيّة).
            None ⇒ لا قرار إطلاق (``no_depletion_data``، لا اختلاق).
        taw_mm: الماء المتاح الكلّيّ TAW (من ``soil_water_params``). ≤0/None ⇒ لا إطلاق.
        raw_fraction: p (نسبة الاستنزاف المسموح قبل الإجهاد، FAO-56، افتراضيّ 0.5).
        water_stress_class: ``normal``/``watch``/``critical`` من ``canonical_water_stress``
            (اختياريّ، يرفع الإلحاح فقط — لا يختلق قراراً).
        policy: سياسة الريّ (enum/نصّ). None ⇒ الأحوط WATER_SAVING. تحدّد مقبضَي
            ``trigger_fraction`` (× RAW) و``refill_fraction`` (× Dr).
        water_price_per_m3/yield_value_per_ha: لـ PROFIT_MAX (غيابها ⇒ تراجع موسوم).
        force_net_only: تجاوز يدويّ (None ⇒ يُقرأ من علم البيئة).

    Returns dict:
        ``net_irrigation_mm`` · ``salinity_leaching_mm`` · ``gross_irrigation_mm`` ·
        ``salinity_ks`` · ``policy`` · ``requires_expert_review`` · ``urgency`` ·
        ``timing_ar`` · ``rationale_ar`` · ``evidence`` (قائمة {source, value, note_ar}) ·
        **(الإجهاد المائيّ)** ``should_irrigate`` (bool|None) · ``trigger_reason`` ·
        ``target_refill_mm`` (= refill_fraction × Dr) · ``raw_mm`` · ``depletion_mm`` ·
        ``water_stress_class`` · ``policy_knobs`` · ``calibrated`` (=False، غير معايَر يمنيّاً).

    صدق: قرار الإطلاق يحتاج Dr+TAW فعليَّين؛ غيابهما ⇒ ``should_irrigate=None`` و
    ``trigger_reason="no_depletion_data"`` (يبقى الصافي معروضاً، لا قرار على غياب).
    """
    # مطرٌ مفقود يقف هنا. صياغةُ `float = 0.0` السابقة كانت تجعل الغيابَ يُحسَب «صفر مطر»
    # في المطروح من الحاجة، فتخرج كمّيّةٌ أعلى بثقةٍ لا تستحقّها — ولا يظهر في المخرَج
    # ما يقول إنّ المطرَ لم يُعرَف. والرفضُ عند الحدّ يمنع وراثةَ الافتراض صامتاً.
    missing_rain = [
        name
        for name, value in (
            ("rain_recent_mm", rain_recent_mm),
            ("forecast_rain_mm", forecast_rain_mm),
        )
        if value is None
    ]
    if missing_rain:
        raise ValueError("recommend_irrigation: مطرٌ مفقود لا يُصفَّر — " + "، ".join(missing_rain))

    # سياسة الإطلاق/الملء تُلتقَط الآن: المتغيّر ``policy`` يُعاد استخدامه لاحقاً لتصنيف
    # سياسة الملوحة (net_only/…)، فلا نقرأ منه بعد ذلك لمقابض الإطلاق.
    irrigation_strategy = policy

    if force_net_only is None:
        force_net_only = salinity_policy_forced_off(os.getenv("SAHOOL_IRRIGATION_SALINITY_POLICY"))

    # موثوقيّة فحص EC: موجود + ليس قديماً + لم تُعطَّل السياسة.
    ec_reliable = (
        not force_net_only
        and soil_ece is not None
        and (soil_ec_age_days is None or int(soil_ec_age_days) <= int(ec_max_age_days))
    )
    ece = float(soil_ece) if ec_reliable else None

    evidence: list[dict] = []
    if soil_ece is not None and not ec_reliable:
        evidence.append(
            {
                "source": "soil_lab_tests",
                "value": float(soil_ece),
                "note_ar": "فحص ملوحة قديم أو السياسة معطّلة ⇒ يُهمَل (صافٍ فقط).",
            }
        )

    # (1)+(2) الصافي + Ks عبر المصدر الموحَّد (irrigation_advice يطبّق Ks فقط عند EC≥العتبة).
    base = irrigation_advice(
        et0_mm=et0_mm,
        crop=crop,
        stage=stage,
        rain_recent_mm=rain_recent_mm,
        forecast_rain_mm=forecast_rain_mm,
        soil_moisture_pct=soil_moisture_pct,
        kc_override=kc_override,
        soil_ece=ece,
        crop_salt_tolerance_ece=crop_salt_tolerance_ece if ec_reliable else None,
        salt_slope_pct=salt_slope_pct,
    )
    net = float(base["recommended_mm"])
    salinity_ks = float(base["salinity_ks"])

    # (3) شروط الغسل المشروط.
    eff = float(irrigation_efficiency) if irrigation_efficiency else DEFAULT_IRRIGATION_EFFICIENCY
    leaching_possible = (
        ec_reliable
        and crop_salt_tolerance_ece is not None
        and water_ec is not None
        and irrigation_efficiency is not None
        and (drainage or "").strip().lower() in _DRAINAGE_OK
    )

    leaching_mm = 0.0
    if leaching_possible:
        lr = leaching_requirement(float(water_ec), float(crop_salt_tolerance_ece))
        leaching_mm = round(net * lr, 1)

    gross = round((net + leaching_mm) / eff, 1)

    # ── تصنيف السياسة + هل يلزم خبير ──
    requires_expert_review = False
    if ece is None:
        policy = "net_only"
    elif leaching_mm > 0:
        policy = "salinity_with_leaching"
        requires_expert_review = ece >= SALINITY_CRITICAL_ECE
    elif ece >= SALINITY_CRITICAL_ECE:
        # ملوحة حرجة لكن بيانات الغسل ناقصة ⇒ لا خطّة غسل مسؤولة ⇒ مراجعة خبير.
        policy = "blocked_for_review"
        requires_expert_review = True
    elif salinity_ks < 1.0:
        policy = "salinity_adjusted"
    else:
        # فحص موثوق لكنّ ECe دون العتبة المتوسّطة ⇒ لا أثر ملوحة (صافٍ فعليّاً).
        policy = "net_only"

    # أدلّة + تبرير.
    if ece is not None:
        evidence.append(
            {
                "source": "soil_lab_tests",
                "value": ece,
                "note_ar": (
                    f"ECe={ece:.1f} dS/m (عتبة متوسّطة {SALINITY_MODERATE_ECE}، "
                    f"حرجة {SALINITY_CRITICAL_ECE})."
                ),
            }
        )
    if salinity_ks < 1.0:
        evidence.append(
            {
                "source": "fao56.salinity_stress_ks",
                "value": salinity_ks,
                "note_ar": "إجهاد ملوحة خفّض الاحتياج الصافي (Maas-Hoffman، بلا غسل تلقائيّ).",
            }
        )
    if leaching_mm > 0:
        evidence.append(
            {
                "source": "fao56.leaching_requirement",
                "value": leaching_mm,
                "note_ar": f"غسل مشروط +{leaching_mm} مم (ECw + صرف {drainage} + كفاءة {eff}).",
            }
        )

    # ── قرار الإطلاق المُشتقّ من استنزاف منطقة الجذور (FAO-56) ──
    # الفجوة المُغلَقة: منتِج التوصية كان يحسب الصافي (ETc − مطر) فقط ويتجاهل Dr
    # المخزَّن رغم توفّره؛ هنا نُدخِل مقبضَي السياسة: نُطلق حين Dr ≥ trigger×RAW،
    # ونملأ refill×Dr. غياب Dr/TAW ⇒ لا قرار (fail-safe، لا اختلاق).
    pp = policy_params(
        irrigation_strategy if irrigation_strategy is not None else IrrigationPolicy.WATER_SAVING,
        water_price_per_m3=water_price_per_m3,
        yield_value_per_ha=yield_value_per_ha,
    )
    should_irrigate: bool | None = None
    trigger_reason = "no_depletion_data"
    target_refill_mm: float | None = None
    raw_mm: float | None = None
    dr_out: float | None = None
    taw_v = float(taw_mm) if taw_mm is not None else None
    if depletion_mm is not None and taw_v is not None and taw_v > 0:
        dr_out = max(0.0, float(depletion_mm))
        p_frac = max(0.0, min(1.0, float(raw_fraction)))
        raw_mm = round(p_frac * taw_v, 1)
        trigger_mm = pp.trigger_fraction * raw_mm
        should_irrigate = dr_out >= trigger_mm
        trigger_reason = (
            "depletion_at_or_above_trigger" if should_irrigate else "defer_below_trigger"
        )
        target_refill_mm = round(pp.refill_fraction * dr_out, 1)
        evidence.append(
            {
                "source": "fao56.root_zone_depletion",
                "value": dr_out,
                "note_ar": (
                    f"Dr={dr_out:.1f} مم مقابل عتبة الإطلاق {trigger_mm:.1f} مم "
                    f"(RAW={raw_mm} مم × trigger {pp.trigger_fraction}) — "
                    f"{'إطلاق' if should_irrigate else 'تأجيل'}؛ ملء الهدف "
                    f"{target_refill_mm} مم (refill {pp.refill_fraction}×Dr)."
                ),
            }
        )

    # الإلحاح (مفردات irrigation_advice: none|low|moderate|high): الإجهاد الحرج يرفعه
    # صراحةً؛ لا يختلق قراراً (يبقى should_irrigate كما هو).
    urgency = base.get("urgency")
    if water_stress_class == "critical":
        urgency = "high"
    elif water_stress_class == "watch" and urgency in (None, "none", "low"):
        urgency = "moderate"

    rationale_ar = str(base.get("rationale_ar", ""))
    if should_irrigate is None:
        rationale_ar += " (قرار الإطلاق غير محسوب — لا استنزاف Dr/TAW موثوق للحقل.)"
    elif should_irrigate:
        rationale_ar += (
            f" الاستنزاف بلغ عتبة الإطلاق ({pp.policy.value}) — يُوصى بريّ ملء "
            f"≈{target_refill_mm} مم (غير معايَر يمنيّاً)."
        )
    else:
        rationale_ar += (
            f" الاستنزاف دون عتبة الإطلاق ({pp.policy.value}) — يُفضَّل التأجيل ومراقبة Dr."
        )
    if policy == "blocked_for_review":
        rationale_ar += (
            f" ⚠ ملوحة حرجة (ECe={ece:.1f}) ونقص بيانات الغسل (ECw/صرف/كفاءة) — "
            "التوصية الصافية فقط؛ يلزم مراجعة خبير لخطّة غسل/صرف."
        )
    elif policy == "salinity_adjusted":
        rationale_ar += " (تقييم الملوحة: Ks مُطبَّق؛ الغسل غير محسوب لنقص ECw/صرف/كفاءة.)"
    elif policy == "net_only" and soil_ece is None:
        rationale_ar += " (تقييم الملوحة غير مكتمل — لا فحص EC مخبريّ.)"

    return {
        "net_irrigation_mm": net,
        "salinity_leaching_mm": leaching_mm,
        "gross_irrigation_mm": gross,
        "irrigation_efficiency": eff,
        "salinity_ks": salinity_ks,
        "policy": policy,
        "requires_expert_review": requires_expert_review,
        "urgency": urgency,
        "timing_ar": base.get("timing_ar"),
        "rationale_ar": rationale_ar,
        "evidence": evidence,
        # ── قرار الإطلاق المُشتقّ من الاستنزاف (FAO-56) ──
        "should_irrigate": should_irrigate,
        "trigger_reason": trigger_reason,
        "target_refill_mm": target_refill_mm,
        "raw_mm": raw_mm,
        "depletion_mm": round(dr_out, 1) if dr_out is not None else None,
        "water_stress_class": water_stress_class,
        "policy_knobs": pp.to_dict(),
        "calibrated": False,
    }
