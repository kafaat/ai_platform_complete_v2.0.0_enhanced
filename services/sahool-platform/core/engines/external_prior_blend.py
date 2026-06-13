"""core/engines/external_prior_blend.py — مزج سابقة خارجيّة منشورة ببيانات اليمن.

السؤال (المستخدم): هل نستفيد من مشاريع/أوراق خارجيّة (مثل CropSight-US والمماثلة)
لمحاصيل **تُزرَع فعلاً في اليمن** (قمح/شعير/ذرة/دخن…)، بتظافر القرائن وأوزان
تدرّجيّة لحين وصول البيانات المحلّيّة للحجم المطلوب؟

الجواب الصادق: نعم — **سابقةً ضعيفة (weak prior) متلاشية**، لا حقيقةً مستورَدة.

⚠ التمييز الحاسم (ثابت من تحليلنا السابق لـCropSight-US):
  • نموذج/بيانات أمريكا **ليست قابلة للنقل مباشرة** — التواقيع الطيفيّة والمعايير
    تختلف بالمناخ والتربة والتقويم. استيراد قيمها كحقيقة = تأليف.
  • القابل للنقل: المنهجيّة + **سابقة عدديّة ضعيفة** للمحصول المزروع في اليمن،
    بثقة مقصوصة (≤0.5) لأنّها غير مُتحقّقة محلّيّاً، **تتلاشى** كلّما تراكم محلّيّ.

ما يضيفه (لا يكرّر القائم — يركّبه):
  • يعيد استخدام `confidence_weight(n)=n/(n+K)` من prediction_calibration (مصدر
    واحد لصيغة الانكماش — لا تكرار).
  • يكمّل `transfer_learning` (نقل بين مديريّات tenant واحد): هذا للسابقة
    **الخارجيّة المنشورة** (ورقة/مشروع) لا لمديريّة داخليّة.
  • يربط المخرَج بـ`human_escalation` (الثقة دون عتبة اليقين → تصعيد لمرشد).
  • يحترم `crop_classification_readiness`: قبل الحجم المطلوب = تلميح يُراجَع.

⚠ المبدأ:
  • تظافر قرائن بأوزان شفّافة: محلّي (يقوى) + سابقة خارجيّة (تتلاشى).
  • سقف ثقة السابقة الخارجيّة المنشورة ≤0.5 (غير متحقّقة محلّيّاً) — لا تُعامَل
    كمعايرة محلّيّة مهما قلّت البيانات.
  • صدق: محصول غير مزروع في اليمن → السابقة غير منطبقة (لا مزج، لا اختراع).
  • حتميّ شفّاف: يُظهر وزن كلّ قرينة، اعتماد السابقة، وقرار التصعيد.
"""

from __future__ import annotations

from core.engines.human_escalation import CONFIDENT_FLOOR, assess_escalation

# مصدر واحد لثابت الانكماش الافتراضيّ (صيغة n/(n+k) نفسها في prediction_calibration).
from core.learning.prediction_calibration import SHRINKAGE_K

# سقف مصداقيّة السابقة الخارجيّة المنشورة (غير متحقّقة محلّيّاً): حتّى عند n=0
# لا تتجاوز مساهمتها في ثقة المخرَج هذا الحدّ — تبقى «تلميحاً يُراجَع».
EXTERNAL_PRIOR_MAX_CREDIBILITY = 0.5

# عند تجاوز هذا الوزن المحلّي تُعتبر السابقة الخارجيّة «متلاشية» (مساهمة ضئيلة).
PRIOR_FADED_LOCAL_WEIGHT = 0.90  # n/(n+K) ≥ 0.90 ⇒ n ≥ 9·K


def blend_external_prior(
    external_prior: float | None,
    local_estimate: float | None,
    n_local: int,
    *,
    crop_grown_in_yemen: bool,
    external_credibility: float = EXTERNAL_PRIOR_MAX_CREDIBILITY,
    k: int = SHRINKAGE_K,
) -> dict:
    """يمزج سابقة خارجيّة منشورة ببيانات اليمن المتراكمة — وزن تدرّجي شفّاف.

    external_prior: قيمة عدديّة من مشروع/ورقة خارجيّة (لمحصول مزروع في اليمن).
    local_estimate: التقدير من بيانات اليمن (None إن لم يتراكم شيء بعد).
    n_local: عدد العيّنات المحلّيّة المتراكمة (يحكم الوزن: n/(n+K)).

    المخرَج: التقدير الممزوج + أوزان القرائن + ثقة + قرار تصعيد بشريّ.
    """
    # 1) المحصول ليس مزروعاً في اليمن ⇒ السابقة غير منطبقة (لا مزج، لا اختراع).
    if not crop_grown_in_yemen:
        return {
            "applicable": False,
            "blended_estimate": None,
            "reason_ar": (
                "السابقة الخارجيّة غير منطبقة: المحصول ليس مزروعاً في اليمن — "
                "لا مزج (المنهجيّة قد تُلهم، لكن القيمة الأجنبيّة لا تُستورَد)."
            ),
            "escalation": assess_escalation(None, source="external_prior_blend", has_answer=False),
        }

    # سقف ثقة السابقة: لا تتجاوز الحدّ مهما كان (غير متحقّقة محلّيّاً).
    cred = max(0.0, min(external_credibility, EXTERNAL_PRIOR_MAX_CREDIBILITY))

    # 2) الوزن التدرّجي للقرينة المحلّيّة: انكماش n/(n+k) (k=SHRINKAGE_K افتراضاً —
    #    نفس صيغة prediction_calibration.confidence_weight، لكن يحترم k المُمرَّر).
    w_local = n_local / (n_local + k) if n_local > 0 else 0.0
    w_external = 1.0 - w_local

    # 3) المزج — حسب توفّر القرائن (لا اختراع لقيمة غائبة).
    has_local = local_estimate is not None and n_local > 0
    if has_local and external_prior is not None:
        blended = w_local * local_estimate + w_external * external_prior
    elif has_local:  # لا سابقة خارجيّة — محلّي بحت.
        blended, w_local, w_external = local_estimate, 1.0, 0.0
    elif external_prior is not None:  # لا محلّي بعد — سابقة خارجيّة وحدها (تلميح).
        blended = external_prior
    else:  # لا قرينة إطلاقاً ⇒ لا إجابة، تصعيد حاكم.
        return {
            "applicable": True,
            "blended_estimate": None,
            "reason_ar": "لا سابقة خارجيّة ولا بيانات محلّيّة — لا تقدير (تصعيد).",
            "escalation": assess_escalation(None, source="external_prior_blend", has_answer=False),
        }

    # 4) ثقة المخرَج: المحلّي بكامل وزنه، والسابقة الخارجيّة بمصداقيّتها المقصوصة.
    # output_confidence = w_local·1 + w_external·cred — يبقى دون اليقين ما دامت
    # السابقة الخارجيّة مهيمنة (cred ≤ 0.5)، فيُصعَّد تلقائيّاً للمراجعة.
    output_confidence = round(w_local + w_external * cred, 3)

    prior_faded = w_local >= PRIOR_FADED_LOCAL_WEIGHT
    escalation = assess_escalation(
        output_confidence,
        source="external_prior_blend",
        uncertain_points=(
            [] if prior_faded else ["السابقة لا تزال خارجيّة (غير متحقّقة محلّيّاً) — راكم بيانات اليمن"]
        ),
    )

    return {
        "applicable": True,
        "blended_estimate": round(blended, 4),
        "local_estimate": local_estimate,
        "external_prior": external_prior,
        "n_local": n_local,
        "local_weight": round(w_local, 3),
        "external_weight": round(w_external, 3),
        "external_credibility": cred,
        "output_confidence": output_confidence,
        "prior_faded": prior_faded,
        "matured": prior_faded and output_confidence >= CONFIDENT_FLOOR,
        "escalation": escalation,
        "reason_ar": (
            f"مزج تدرّجي: محلّي ×{w_local:.2f} (n={n_local}) + سابقة خارجيّة "
            f"×{w_external:.2f} (مصداقيّة ≤{cred:.0%}) ⇒ {round(blended, 3)}. "
            + (
                "السابقة الخارجيّة تلاشت (بيانات اليمن مهيمنة)."
                if prior_faded
                else "السابقة الخارجيّة لا تزال مؤثّرة — تلميح يُراجَع حتّى يكبر المحلّي."
            )
        ),
        "honesty_note_ar": (
            "السابقة الخارجيّة (مشروع/ورقة) ليست حقيقة مستورَدة بل قرينة ضعيفة "
            "متلاشية بثقة ≤50% (غير متحقّقة محلّيّاً). تظافر القرائن بوزن تدرّجي "
            "n/(n+K): كلّما تراكمت بيانات اليمن، هيمن المحلّي وتلاشت السابقة. دون "
            "الحجم المطلوب: تلميح يُصعَّد لمرشد، لا توصية مُلزِمة."
        ),
    }


def blend_maturity(blends_by_context: dict[str, dict]) -> dict:
    """نضج المزج عبر السياقات (محصول×منطقة) — أين تلاشت السابقة، أين لا تزال مؤثّرة.

    blends_by_context: {context_key: مخرَج blend_external_prior}. يلخّص أين أصبح
    التقدير محلّيّاً ناضجاً وأين لا يزال يتّكئ على سابقة خارجيّة (يحتاج بيانات).
    """
    matured, still_external = [], []
    for ctx, b in blends_by_context.items():
        if not b.get("applicable") or b.get("blended_estimate") is None:
            continue
        (matured if b.get("matured") else still_external).append(ctx)
    return {
        "total_contexts": len(blends_by_context),
        "matured_local_contexts": sorted(matured),
        "still_external_dependent": sorted(still_external),
        "strategic_note_ar": (
            "الطريق للاستفادة من المشاريع الخارجيّة بصدق: (١) ابدأ بسابقة ضعيفة "
            "للمحصول المزروع في اليمن، (٢) راكم بيانات حقول اليمن، (٣) الوزن "
            "التدرّجي يحوّل الثقة من السابقة للمحلّي تلقائيّاً، (٤) عند الحجم "
            "المطلوب تتلاشى السابقة ويصبح التقدير محلّيّاً مُلزِماً. لا قفز فوق ما "
            "لا نملكه — كلّ خطوة مدفوعة بالبيانات وقابلة للتصعيد."
        ),
    }
