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
from datetime import date

from .field_operational_state import resolve_field_state
from .field_state_gateway import build_state_inputs


async def gather_field_freshness(conn, field_id: str) -> dict:
    """يقرأ مصادر النضارة القانونيّة للحقل من قاعدة المنصّة.

    يُرجِع {last_image_date, latest_soil_sampled_on, weather_age_hours} — أيّ
    مصدر غائب يكون None (يدع resolve_field_state يعلن «بيانات ناقصة» بصدق).
    """
    last_image_date = await conn.fetchval(
        "SELECT last_image_date FROM imagery_automation_fields WHERE field_id = $1",
        field_id,
    )
    soil_sampled_on = await conn.fetchval(
        "SELECT MAX(sampled_on) FROM soil_lab_tests "
        "WHERE field_id = $1 AND status IN ('approved', 'published')",
        field_id,
    )
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
    }


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

    tenant_id = await conn.fetchval("SELECT tenant_id FROM fields WHERE field_id = $1", field_id)
    if tenant_id is None:
        # الحقل غير موجود ضمن المستأجِر — لا نحفظ إسقاطاً يتيماً (الحالة تُعاد فقط).
        return {"state": state, "changed": False}

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
             reasons_ar, conflicts, freshness_warnings, inputs, computed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, NOW())
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
    )
    return {"state": state, "changed": changed}
