"""
sahool_core.recommendation_replay
==================================
Forensic Agriculture — لماذا خرجت التوصية؟

الفجوة المسدودة: المراجعتان (2026-05-28) أكّدتا أنّ التتبّع
(traceability/provenance) أهمّ من الميزات. لو سأل مزارع بعد 8 أشهر
"لماذا قلت أن أزرع قمحاً؟" يجب أن نستطيع الإجابة بدقّة:
  • أيّ نموذج وأيّ نسخته؟
  • أيّ مصدر طقس؟ في أيّ تاريخ؟
  • ما قيم NDVI/EC/الرطوبة وقت التوصية؟
  • أيّ محرّكات شاركت في القرار؟
  • هل البيانات الحالية تنتج نفس التوصية (consistency)؟

هذه ليست "enterprise luxury" — هي **شرط بقاء** لمنصّة استشارية تخاطب
السلامة الغذائية والبيئية.

المبادئ المحفوظة:
  • الصدق: التوصية المُسترجَعة هي ما حدث فعلاً، لا ما "كنّا نتمنّى"
  • النواة محايدة: لا تُغيّر السجلّات، تقرأها فقط
  • الكشف عن الانحراف: إن أنتج نفس المدخل توصية مختلفة الآن،
    نُعلن السبب (نموذج تغيّر، معايرة جديدة، قاعدة جديدة)

التكامل:
  ← يقرأ من recommendation_log (RecommendationRecord.provenance)
  ← يقارن ضدّ التشغيل الحالي عبر "replay simulation"
  → يكشف الانحرافات (model drift) للمراجعة البشرية
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReplayReport:
    """تقرير forensic — لماذا خرجت التوصية؟ هل ما زالت متّسقة؟"""

    rec_id: str
    issued_date: str
    has_provenance: bool  # هل التوصية كانت موثّقة كاملاً؟
    model_versions: dict  # نسخة كل محرّك وقت التوصية
    weather_source: str | None
    input_snapshot: dict  # قيم المدخلات وقت التوصية
    engines_used: list
    consistency_check: dict  # هل تنتج نفس النتيجة الآن؟
    drift_detected: bool  # هل اختلف شيء؟
    drift_reasons_ar: list[str] = field(default_factory=list)
    summary_ar: str = ""


def explain_recommendation(rec_record) -> dict:
    """يستخرج 'لماذا' من سجلّ توصية واحد. التفسير القابل للقراءة.

    إن غاب provenance (توصية قديمة قبل الإضافة): يُعلن ذلك صراحةً،
    لا يخترع. هذا يتسق مع مبدأ 'صفر اختراع' الجوهري."""
    if not getattr(rec_record, "provenance", None):
        return {
            "rec_id": rec_record.rec_id,
            "has_provenance": False,
            "explanation_ar": ("هذه التوصية صدرت قبل تفعيل التتبّع — لا يمكن إعادة بنائها بدقّة"),
            "issued_date": rec_record.issued_date,
            "recommendation_ar": rec_record.recommendation_ar,
        }

    prov = rec_record.provenance
    # دعم provenance كـdict (من JSON) أو كـRecommendationProvenance
    if hasattr(prov, "model_versions"):
        prov_dict = {
            "model_versions": prov.model_versions,
            "weather_source": prov.weather_source,
            "weather_data_date": prov.weather_data_date,
            "input_snapshot": prov.input_snapshot,
            "engines_used": prov.engines_used,
            "calibration_set_id": prov.calibration_set_id,
            "knowledge_snippets_ids": prov.knowledge_snippets_ids,
        }
    else:
        prov_dict = dict(prov)

    # شرح إنساني للسبب
    engines = prov_dict.get("engines_used", [])
    snapshot = prov_dict.get("input_snapshot", {})
    weather = prov_dict.get("weather_source", "غير محدّد")

    snapshot_str = "، ".join(f"{k}={v}" for k, v in snapshot.items())
    explanation = (
        f"التوصية '{rec_record.recommendation_ar}' صدرت بتاريخ "
        f"{rec_record.issued_date}. شاركت المحرّكات: {', '.join(engines)}. "
        f"مصدر الطقس: {weather}. المدخلات وقت القرار: {snapshot_str}. "
        f"الثقة: {rec_record.confidence}."
    )

    return {
        "rec_id": rec_record.rec_id,
        "has_provenance": True,
        "explanation_ar": explanation,
        "provenance": prov_dict,
        "issued_date": rec_record.issued_date,
        "recommendation_ar": rec_record.recommendation_ar,
        "confidence": rec_record.confidence,
        "predicted_yield_t_ha": rec_record.predicted_yield_t_ha,
        "actual_yield_t_ha": rec_record.actual_yield_t_ha,
        "error_pct": rec_record.error_pct,
    }


def detect_drift(rec_record, current_model_versions: dict) -> ReplayReport:
    """يكشف انحراف النموذج: هل النسخ الحالية مختلفة عن وقت التوصية؟

    drift شائع وحتمي مع تطوّر الكود. الخطر ليس وجوده، بل **خفاؤه**.
    هذه الدالة تُعلنه صراحةً."""
    has_prov = bool(getattr(rec_record, "provenance", None))

    if not has_prov:
        return ReplayReport(
            rec_id=rec_record.rec_id,
            issued_date=rec_record.issued_date,
            has_provenance=False,
            model_versions={},
            weather_source=None,
            input_snapshot={},
            engines_used=[],
            consistency_check={
                "status": "unknown",
                "reason_ar": "لا تتبّع — التوصية أقدم من النظام",
            },
            drift_detected=False,  # لا نُعلن drift بدون مرجع
            drift_reasons_ar=[],
            summary_ar="توصية بلا تتبّع — لا يمكن كشف الانحراف",
        )

    prov = rec_record.provenance
    historical_versions = (
        prov.get("model_versions", {}) if isinstance(prov, dict) else prov.model_versions
    )

    # قارن بين النسخ التاريخية والحالية لكل محرّك مشترك
    drift_reasons = []
    for engine, hist_version in historical_versions.items():
        current = current_model_versions.get(engine)
        if current and current != hist_version:
            drift_reasons.append(
                f"المحرّك '{engine}': النسخة وقت التوصية {hist_version}، "
                f"الحالية {current} — أعد التشغيل للتحقّق"
            )

    drift = len(drift_reasons) > 0
    consistency = {
        "status": "drift_detected" if drift else "stable",
        "checked_engines": list(historical_versions.keys()),
        "reason_ar": (
            "النموذج تطوّر منذ إصدار التوصية"
            if drift
            else "النسخ متطابقة — التوصية قابلة لإعادة الإنتاج"
        ),
    }

    if isinstance(prov, dict):
        weather_src = prov.get("weather_source")
        snap = prov.get("input_snapshot", {})
        engines = prov.get("engines_used", [])
    else:
        weather_src = prov.weather_source
        snap = prov.input_snapshot
        engines = prov.engines_used

    return ReplayReport(
        rec_id=rec_record.rec_id,
        issued_date=rec_record.issued_date,
        has_provenance=True,
        model_versions=historical_versions,
        weather_source=weather_src,
        input_snapshot=snap,
        engines_used=engines,
        consistency_check=consistency,
        drift_detected=drift,
        drift_reasons_ar=drift_reasons,
        summary_ar=(
            f"التوصية صادرة في {rec_record.issued_date}. "
            + ("⚠️ انحراف نموذج مكتشف — راجع التفاصيل" if drift else "✅ النموذج مستقرّ منذ الإصدار")
        ),
    )


def audit_chain(rec_records: list, current_model_versions: dict) -> dict:
    """تقرير شامل: كم نسبة التوصيات المُتتبَّعة؟ كم منها بانحراف؟

    مقياس صحّي للنظام — يكشف 'الديون التتبّعية' المتراكمة."""
    total = len(rec_records)
    if not total:
        return {"total": 0, "summary_ar": "لا توصيات في السجلّ"}

    traced = sum(1 for r in rec_records if getattr(r, "provenance", None))
    untraced = total - traced

    drift_count = 0
    drift_details = []
    for r in rec_records:
        if getattr(r, "provenance", None):
            report = detect_drift(r, current_model_versions)
            if report.drift_detected:
                drift_count += 1
                drift_details.append(
                    {
                        "rec_id": report.rec_id,
                        "reasons": report.drift_reasons_ar,
                    }
                )

    trace_rate = round(traced / total, 2)
    return {
        "total": total,
        "traced": traced,
        "untraced": untraced,
        "trace_rate": trace_rate,
        "drift_detected_count": drift_count,
        "drift_details_preview": drift_details[:5],
        "summary_ar": (
            f"إجمالي {total} توصية، {traced} متتبَّعة "
            f"({trace_rate:.0%})، {drift_count} منها بانحراف نموذج. "
            + (
                f"{untraced} توصية قديمة بلا تتبّع — لا يمكن مراجعتها."
                if untraced
                else "كل التوصيات قابلة للمراجعة."
            )
        ),
    }
