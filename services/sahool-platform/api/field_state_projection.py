"""
api/field_state_projection.py — إسقاط الحالة القانونيّة الموحّدة (Phase 2)

يرفع بوّابة القراءة (field_state_gateway) إلى **read model مُخزَّن** (جدول
field_state، هجرة v53): يُعيد الحساب من المصادر القانونيّة ثمّ يحفظ النتيجة
(UPSERT) كي يقرأها كلّ المستهلكين (التوصيات/التنبيهات/guardrails) بسرعة وبتدقيق.

ما يفعله (وما لا يفعله — صدق):
  ✓ يجمع المدخلات من قاعدة المنصّة (نفس مصادر البوّابة) ضمن tenant_connection (RLS).
  ✓ يركّب الحالة عبر resolve_field_state (لا يكرّر التركيب).
  ✓ يحفظ الإسقاط (UPSERT) ويُرجِع changed=هل تبدّلت الصلاحيّة/نمط التنفيذ — كي
    يقرّر المتّصِل إصدار حدث field.state_changed (لا حدث على كلّ قراءة).
  ✗ لا منطق أحداث هنا (لتفادي دورة استيراد مع main) — الإصدار في المتّصِل.
  ✗ لا يختلق مدخلات: غياب المصدر ⇒ None ⇒ resolve_field_state يعلن INSUFFICIENT.

يُستدعى دائماً ضمن tenant_connection (app.current_tenant مضبوط) — UPSERT يمرّ
سياسة عزل المستأجِر (tenant_id = المستأجِر الحاليّ).
"""

from __future__ import annotations

import json
import logging
from datetime import date

from .field_operational_state import resolve_field_state
from .field_state_gateway import build_state_inputs

logger = logging.getLogger("sahool.field_state")


def _derive_alerts_from_state(state: dict) -> list[dict]:
    """يشتقّ تنبيهات صادقة (للعرض فقط) من dict الحالة القانونيّة الموحّدة.

    دالّة نقيّة بلا I/O (قابلة للاختبار بلا قاعدة): تقرأ الحقائق الزراعيّة من
    agronomic.operational_truths + نمط التنفيذ، فتشتقّ تنبيهات بسيطة لا تُلفِّق:
      • salinity_class == "critical" ⇒ تنبيه عالي الخطورة «ملوحة تربة حرجة».
      • execution_mode في (blocked, human_review) ⇒ تنبيه «القرار يحتاج مراجعة بشريّة».
    صدق: غياب الحقائق ⇒ قائمة فارغة (لا تنبيه مُلفَّق). لا تُكتب في جدول alerts.
    كلّ تنبيه يحمل source="canonical_field_state" (مصدر الاشتقاق صريح للتدقيق).
    """
    if not isinstance(state, dict):
        return []
    alerts: list[dict] = []
    truths = (state.get("agronomic") or {}).get("operational_truths") or {}

    if truths.get("salinity_class") == "critical":
        alerts.append(
            {
                "alert_type": "salinity_critical",
                "severity": "high",
                "title_ar": "ملوحة تربة حرجة",
                "message_ar": (
                    "الحالة القانونيّة الموحّدة تُظهر ملوحة تربة حرجة — غسيل وتحسين "
                    "الصرف عاجلاً، وتجنّب الريّ المالح."
                ),
                "source": "canonical_field_state",
            }
        )

    if state.get("execution_mode") in ("blocked", "human_review"):
        alerts.append(
            {
                "alert_type": "human_review_required",
                "severity": "medium",
                "title_ar": "القرار يحتاج مراجعة بشريّة",
                "message_ar": (
                    "نمط تنفيذ الحالة القانونيّة الموحّدة ليس تلقائيّاً — يلزم تأكيد "
                    "المهندس/المزارع قبل التنفيذ."
                ),
                "source": "canonical_field_state",
            }
        )

    return alerts


async def gather_field_freshness(conn, field_id: str) -> dict:
    """يقرأ مصادر النضارة القانونيّة للحقل من قاعدة المنصّة.

    يُرجِع {last_image_date, latest_soil_sampled_on, weather_age_hours, ndvi_mean,
    ndvi_date} — أيّ مصدر غائب يكون None (يدع resolve_field_state يعلن «بيانات
    ناقصة» بصدق، وتُعلَن قيمة NDVI غير متاحة بدل رقم مُلفَّق).
    """
    # نضارة الصورة (عمود قديم دائم الوجود) — استعلام أساسيّ لا يفشل.
    last_image_date = await conn.fetchval(
        "SELECT last_image_date FROM imagery_automation_fields WHERE field_id = $1",
        field_id,
    )
    # Stage D: قيمة NDVI الحقيقيّة (أعمدة v54) — داخل SAVEPOINT كي لا يكسر فشلُها
    # (UndefinedColumn قبل تطبيق v54 في نشر متدرّج) المعاملةَ الخارجيّة ⇒ تراجع رشيق
    # إلى لا-قيمة (fail-safe، صدق: NULL لا رقم مُلفَّق).
    ndvi_mean = None
    ndvi_date = None
    try:
        async with conn.transaction():  # SAVEPOINT
            row = await conn.fetchrow(
                "SELECT last_ndvi_mean, last_ndvi_date "
                "FROM imagery_automation_fields WHERE field_id = $1",
                field_id,
            )
            if row:
                ndvi_mean = row["last_ndvi_mean"]
                ndvi_date = row["last_ndvi_date"]
    except Exception:  # noqa: BLE001 — v54 غير مطبّقة بعد ⇒ تخطٍّ آمن
        ndvi_mean = None
        ndvi_date = None
    # آخر فحص تربة معتمَد/منشور — صفّ واحد يعطي النضارة (sampled_on) + EC (من result)،
    # فنتفادى استعلامين ونربط EC بأحدث عيّنة فعلاً (مراجعة Copilot).
    soil_row = await conn.fetchrow(
        "SELECT sampled_on, result FROM soil_lab_tests "
        "WHERE field_id = $1 AND status IN ('approved', 'published') AND sampled_on IS NOT NULL "
        "ORDER BY sampled_on DESC LIMIT 1",
        field_id,
    )
    soil_sampled_on = soil_row["sampled_on"] if soil_row else None
    soil_ec = _extract_ec(soil_row["result"]) if soil_row else None
    weather_age_hours = await conn.fetchval(
        "SELECT EXTRACT(EPOCH FROM (NOW() - c.fetched_at)) / 3600.0 "
        "FROM weather_automation_cache c "
        "JOIN weather_automation_locations l ON l.location_key = c.location_key "
        "WHERE l.field_id = $1 ORDER BY c.fetched_at DESC LIMIT 1",
        field_id,
    )
    return {
        "last_image_date": last_image_date,
        "latest_soil_sampled_on": soil_sampled_on,
        "weather_age_hours": float(weather_age_hours) if weather_age_hours is not None else None,
        "ndvi_mean": float(ndvi_mean) if ndvi_mean is not None else None,
        "ndvi_date": ndvi_date,
        "soil_ec": soil_ec,
    }


def _extract_ec(soil_result) -> float | None:
    """يستخرج التوصيل الكهربائيّ (EC، dS/m) من نتيجة فحص التربة (JSONB) — قرينة
    الملوحة للنواة الزراعيّة. يتسامح مع أسماء المفاتيح الشائعة. None إن غاب."""
    if not soil_result:
        return None
    if isinstance(soil_result, str):
        try:
            soil_result = json.loads(soil_result)
        except (ValueError, TypeError):
            return None
    if not isinstance(soil_result, dict):
        return None
    for k in ("ec", "ec_ds_m", "ece", "salinity_ec", "ec_dsm"):
        v = soil_result.get(k)
        if isinstance(v, int | float):
            return float(v)
    return None


def _compose_agronomic(field_id: str, tenant_id, ndvi_mean, soil_ec) -> dict | None:
    """يستدعي النواة الزراعيّة الغنيّة compose_field_state (دالّة نقيّة بلا شبكة)
    لدمج الحقائق الزراعيّة + التحكيم (Salinity>Vigor) في الحالة القانونيّة.

    صدق + fail-safe: لا إشارات ⇒ None؛ وأيّ تعذّر استيراد/حساب ⇒ None دون كسر
    recompute (الحالة التشغيليّة تبقى من resolve_field_state).
    """
    try:
        from core.agronomic_state_engine import SignalInput, compose_field_state

        signals = []
        if ndvi_mean is not None:
            signals.append(SignalInput(source="ndvi", value=float(ndvi_mean)))
        if soil_ec is not None:
            signals.append(SignalInput(source="soil_ec", value=float(soil_ec)))
        if not signals:
            return None
        cs = compose_field_state(field_id, signals, tenant_id=str(tenant_id) if tenant_id else None)
        return {
            "operational_truths": dict(cs.operational_truths),
            "confidence": cs.confidence,
            "confidence_reason": cs.confidence_reason,
            "contradictions": list(cs.contradictions),
            "provenance": list(cs.provenance),
        }
    except Exception:  # noqa: BLE001 — توحيد best-effort، لا يكسر الحالة التشغيليّة
        # هذا المسار يُفعّل تصعيد السلامة (Salinity>Vigor) — الفشل الصامت يعطّل
        # التحكيم. نُسجّل الأثر (مع إبقاء fail-safe) ليُكشَف تشخيصيّاً (مراجعة Copilot).
        logger.warning("compose_field_state تعذّر للحقل %s — تخطّي التحكيم", field_id, exc_info=True)
        return None


async def recompute_field_state(conn, field_id: str) -> dict:
    """يعيد حساب الحالة القانونيّة للحقل ويحفظها في إسقاط field_state (UPSERT).

    يُرجِع {"state": <dict>, "changed": <bool>} حيث changed = تبدّلت الصلاحيّة أو
    نمط التنفيذ عن المحفوظ سابقاً (أو لا صفّ سابق). يُستدعى ضمن tenant_connection.
    صدق: غياب tenant_id للحقل (غير موجود) ⇒ لا حفظ، تُعاد الحالة المحسوبة فقط.
    """
    fresh = await gather_field_freshness(conn, field_id)
    inputs = build_state_inputs(
        last_image_date=fresh["last_image_date"],
        latest_soil_sampled_on=fresh["latest_soil_sampled_on"],
        weather_age_hours=fresh["weather_age_hours"],
        today=date.today(),
    )
    state = resolve_field_state(field_id, **inputs).to_dict()
    state["inputs"] = inputs  # شفافيّة التدقيق: المصادر التي دخلت القرار
    # Stage D: قيمة NDVI الحقيقيّة (من Sentinel عبر raster، مزوّدون مجّانيّون) —
    # معلوماتيّة لا تُغيّر صلاحيّة القرار (تغيير عتبات أغرونوميّة يحتاج تحقّقاً
    # ميدانيّاً). صدق: لا قيمة محسوبة ⇒ available=false لا رقم مُلفَّق.
    _ndvi = fresh.get("ndvi_mean")
    state["remote_sensing"] = {
        "available": _ndvi is not None,
        "ndvi_mean": _ndvi,
        "ndvi_date": fresh["ndvi_date"].isoformat() if fresh.get("ndvi_date") else None,
        "source": "sentinel-2 (raster-service)" if _ndvi is not None else None,
    }

    tenant_id = await conn.fetchval("SELECT tenant_id FROM fields WHERE field_id = $1", field_id)
    if tenant_id is None:
        # الحقل غير موجود ضمن المستأجِر — لا نحفظ إسقاطاً يتيماً (الحالة تُعاد فقط).
        return {"state": state, "changed": False}

    # Stage E (توحيد النواة): ادمج الحقائق الزراعيّة الغنيّة (compose_field_state)
    # في الحالة القانونيّة — فيصبح الإسقاط مصدر الحقيقة الموحّد (حقائق + جاهزيّة).
    # التحكيم يَحكُم فعليّاً: ملوحة تربة حرجة تُصعّد نمط التنفيذ للمراجعة البشريّة
    # رغم خُضرة NDVI (Salinity>Vigor) — تصعيد سلامة لا تخفيض، ولا يغيّر أرقاماً
    # زراعيّة (يطبّق منطق النواة الموجود فقط).
    agronomic = _compose_agronomic(
        field_id, tenant_id, fresh.get("ndvi_mean"), fresh.get("soil_ec")
    )
    if agronomic is not None:
        state["agronomic"] = agronomic
        if (
            agronomic["operational_truths"].get("salinity_class") == "critical"
            and state["execution_mode"] == "auto"
        ):
            state["execution_mode"] = "human_review"
            if state["validity"] == "valid":
                state["validity"] = "degraded"
            state.setdefault("reasons_ar", []).append(
                "ملوحة تربة حرجة (تحكيم النواة الزراعيّة: الملوحة تَحكُم رغم خُضرة "
                "NDVI) — تتطلّب مراجعة بشريّة."
            )

    prev = await conn.fetchrow(
        "SELECT validity, execution_mode FROM field_state WHERE field_id = $1",
        field_id,
    )
    changed = (
        prev is None
        or prev["validity"] != state["validity"]
        or prev["execution_mode"] != state["execution_mode"]
    )

    await conn.execute(
        """
        INSERT INTO field_state
            (field_id, tenant_id, validity, execution_mode, confidence_level,
             ndvi_age_days, soil_age_days, weather_age_hours,
             reasons_ar, conflicts, freshness_warnings, inputs, agronomic, computed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, NOW())
        ON CONFLICT (field_id) DO UPDATE SET
            validity = EXCLUDED.validity,
            execution_mode = EXCLUDED.execution_mode,
            confidence_level = EXCLUDED.confidence_level,
            ndvi_age_days = EXCLUDED.ndvi_age_days,
            soil_age_days = EXCLUDED.soil_age_days,
            weather_age_hours = EXCLUDED.weather_age_hours,
            reasons_ar = EXCLUDED.reasons_ar,
            conflicts = EXCLUDED.conflicts,
            freshness_warnings = EXCLUDED.freshness_warnings,
            inputs = EXCLUDED.inputs,
            agronomic = EXCLUDED.agronomic,
            computed_at = NOW()
        """,
        field_id,
        tenant_id,
        state["validity"],
        state["execution_mode"],
        state.get("confidence_level"),
        inputs.get("ndvi_age_days"),
        inputs.get("soil_age_days"),
        inputs.get("weather_age_hours"),
        json.dumps(state.get("reasons_ar", [])),
        json.dumps(state.get("conflicts", [])),
        json.dumps(state.get("freshness_warnings", [])),
        json.dumps(inputs),
        json.dumps(state.get("agronomic")),  # الحقائق الزراعيّة (NULL إن لا إشارات)
    )
    return {"state": state, "changed": changed}
