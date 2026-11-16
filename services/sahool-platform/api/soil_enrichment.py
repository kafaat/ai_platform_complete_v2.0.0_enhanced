"""soil_enrichment.py — نَسَب مصدر بارامترات ماء التربة + خفض الثقة (WS-D.2b).

قرار المستخدم: ميّز صراحةً بين مصادر كلّ مُدخَل تربة، **واخفض الثقة (أو أعلِن قيداً)
عند استخدام fallback عامّ** — لا تُقدَّم قيمة مُنمذَجة عامّة كأنّها مقيسة مخبريّاً.

الحقيقة الميدانيّة (جرد المصادر): TAW **لا يُخزَّن قطّ** — يُشتقّ دوماً من نسيج +
عمق (FAO-56 Table 19). النسيج يُقاس مخبريّاً فقط: نتيجة ``texture`` معتمدة في المخزن القانونيّ
``soil_lab_results`` (W1-03)، و``soil_lab_tests`` القديم مصدراً احتياطيّاً موسوماً (غالباً غائب). لذا التمييز الصادق:

  • texture:  ``lab_measured`` (من فحص مخبريّ معتمَد، بعمر) | ``unavailable_fallback``
  • taw:      دائماً مُنمذَج FAO-56 — ``modelled_from_lab_texture`` (نسيج مقيس) |
              ``modelled_generic_fallback`` (نسيج مجهول ⇒ منتصف عامّ)
  • root_depth: ``client_supplied`` | ``default_assumed``

(``sensor_observed`` غير منطبق هنا — لا مستشعر رطوبة يُغذّي النسيج/الـTAW.)
"""

from __future__ import annotations

# مفردات مصدر البيانات (بوابة WS-E ستستهلكها). بلا اختلاق: كلّ قيمة مصدرها مُعلَن.
TEXTURE_LAB_MEASURED = "lab_measured"
TEXTURE_FALLBACK = "unavailable_fallback"
TAW_MODELLED_FROM_LAB = "modelled_from_lab_texture"
TAW_MODELLED_FALLBACK = "modelled_generic_fallback"
ROOT_CLIENT = "client_supplied"
ROOT_DEFAULT = "default_assumed"

# عقوبات ثقة (تُطرَح من ثقة الأساس) — عند كلّ fallback عامّ. غير معايَرة، شفّافة.
_PENALTY_TEXTURE_FALLBACK = 0.15
_PENALTY_ROOT_DEFAULT = 0.10


def soil_water_provenance(
    *,
    texture_known: bool,
    texture_value: str | None,
    texture_sampled_on: str | None,
    texture_age_days: float | None,
    root_depth_supplied: bool,
    evidence_ref: str | None = None,
) -> dict:
    """يبني نَسَب مصدر ماء التربة + قيود + عقوبة ثقة إجماليّة. نقيّ حتميّ.

    ``texture_known`` من ``soil_water_params`` (هل مُرِّر نسيج معروف). صدق: النسيج
    المخبريّ يُعلَن بعمره؛ غيابه ⇒ fallback عامّ صريح + عقوبة ثقة.
    """
    limitations: list[str] = []
    penalty = 0.0

    if texture_known:
        texture_source = TEXTURE_LAB_MEASURED
        taw_source = TAW_MODELLED_FROM_LAB
    else:
        texture_source = TEXTURE_FALLBACK
        taw_source = TAW_MODELLED_FALLBACK
        penalty += _PENALTY_TEXTURE_FALLBACK
        limitations.append(
            "soil texture not lab-measured — TAW from generic FAO-56 midpoint (fallback)"
        )

    root_source = ROOT_CLIENT if root_depth_supplied else ROOT_DEFAULT
    texture = {
        "value": texture_value,
        "source": texture_source,
        "sampled_on": texture_sampled_on,
        "age_days": round(texture_age_days, 1) if texture_age_days is not None else None,
    }
    if texture_source == TEXTURE_LAB_MEASURED and evidence_ref:
        # The TAW feature cites the exact lab row the texture came from.
        texture["evidence_ref"] = evidence_ref
    if not root_depth_supplied:
        penalty += _PENALTY_ROOT_DEFAULT
        limitations.append("root depth not provided — assumed default (uncalibrated)")

    return {
        "texture": texture,
        "taw": {"source": taw_source, "calibrated": False},
        "root_depth": {"source": root_source},
        "limitations": limitations,
        "confidence_penalty": round(penalty, 3),
    }


def extract_texture(soil_result) -> str | None:
    """يستخرج النسيج من نتيجة فحص التربة (JSONB) — لا عمود مُصنَّف اليوم (جرد المصادر).

    يتسامح مع أسماء المفاتيح الشائعة (``texture``/``soil_texture``/``textural_class``).
    None إن غاب.
    """
    if not soil_result:
        return None
    if isinstance(soil_result, str):
        import json

        try:
            soil_result = json.loads(soil_result)
        except (ValueError, TypeError):
            return None
    if not isinstance(soil_result, dict):
        return None
    for key in ("texture", "soil_texture", "textural_class", "texture_class"):
        val = soil_result.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


async def latest_lab_texture_row(conn, field_id: str):
    """أحدث نسيج مخبريّ مؤهَّل للحقل (تحت RLS المستأجِر)، أو None.

    Candidates, newest collection date first: an approved ``texture`` result of a soil sample
    (``soil_lab_results``; a detailed result wins a date tie) or the legacy ``soil_lab_tests``
    row. No future dates or observations. A texture result stays eligible while its sample is
    reopened for a correction of another analyte; only a rejected/cancelled sample withdraws
    it. A label the TAW table does not recognise is skipped (it would only buy the loam
    fallback). The row carries ``evidence_ref`` naming its source row
    (``soil_lab_results:<result_id>`` or the legacy ``soil_lab_tests:<test_id>``).
    """
    from core.engines.fao56 import taw_mm_per_m_for_texture

    from api.lab_store import soil_analyte_candidates

    # W1-03: the canonical lab store's one candidate query (lab_store) — v156 first, the
    # frozen soil_lab_tests only as the labelled legacy fallback.
    rows = await soil_analyte_candidates(conn, field_id=field_id, analyte="texture")
    return next(
        (r for r in rows if taw_mm_per_m_for_texture(extract_texture(r["result"]))[1]), None
    )
