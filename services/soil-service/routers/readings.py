"""routers/readings.py — قراءات مستشعر التربة واستيعابها (Readings/Ingest)
======================================================================
شريحة من تفكيك ``main.py`` إلى وحدات ``APIRouter`` (سلوك محفوظ).

نُقلت المُعالِجات حرفيّاً مع تغيير ``@app`` إلى ``@router``؛ المسارات/المخرجات/
المصادقة مطابقة. النماذج/المساعِدات المشتركة (``SoilReading``/``_require_*``)
تبقى في ``main`` وتُشار إليها عبر ``main.X``. ``register_routers(app)`` يضمّ هذا
الراوتر بلا prefix.
"""

from __future__ import annotations

import main
import soil_store
from fastapi import APIRouter, Header, HTTPException

from shared.contracts.soil import SoilObservation, SoilObservationQuality, SoilObservationSource

router = APIRouter()
_OBSERVATION_KEY_MAX_LENGTH = next(
    constraint.max_length
    for constraint in SoilObservation.model_fields["idempotency_key"].metadata
    if getattr(constraint, "max_length", None) is not None
)


@router.get("/v1/soil/readings/{field_id}")
async def get_readings(field_id: str, limit: int = 100, x_agent_token: str = Header(None)):
    """Compatibility view over canonical soil_observations; soil_readings is no longer read SoR."""
    main._require_service_token(x_agent_token)
    await main._require_field_tenant(field_id)
    tenant_id = main._REQ_TENANT.get()
    if not tenant_id:
        raise HTTPException(400, "X-Tenant-Id required")
    if not main._pool:
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")
    return await soil_store.canonical_sensor_readings(
        main._pool, tenant_id=tenant_id, field_id=field_id, limit=limit
    )


@router.post("/v1/soil/ingest")
async def ingest_reading(reading: main.SoilReading, x_agent_token: str = Header(None)):
    """Ingest IoT soil sensor data — يتطلّب توكن خدمة + تحقّق Pydantic.

    أمان: لا نثق بـtenant_id من جسم الطلب أبداً (قابل للتزوير). نشتقّه من المالك
    المُثبَت للحقل (جدول fields عبر دالّة SECURITY DEFINER) أو من X-Tenant-Id
    الموثوق. مالكٌ معروف ≠ مستأجِر الطلب ⇒ 403 (منع كتابة عبر المستأجرين). إن حمل
    الجسم tenant_id يخالف المالك المُثبَت ⇒ نرفض (409). fail-closed عند تعذّر إثبات
    الملكيّة (قاعدة مُهيّأة) ⇒ 503."""
    main._require_service_token(x_agent_token)
    # تفويض ملكيّة الحقل + اشتقاق المالك الموثوق (لا من الجسم). owner=None يعني
    # DB-less مقصود/الحقل غير موجود (لا حجب — يُحفَظ السلوك ليبقى CI أخضر).
    owner = await main._require_field_tenant(reading.field_id)
    # اشتقاق tenant_id الموثوق: المالك المُثبَت أوّلاً، وإلّا X-Tenant-Id الموثوق.
    # لا يُؤخَذ tenant_id من الجسم إطلاقاً (يُتجاهَل، ويُرفَض إن خالف المالك المُثبَت).
    resolved_tenant = owner or main._REQ_TENANT.get()
    body_tenant = (reading.tenant_id or "").strip() or None
    if not resolved_tenant:
        raise HTTPException(400, "X-Tenant-Id required for soil ingestion")
    if owner and body_tenant and body_tenant != owner:
        # الجسم يحمل tenant_id يخالف المالك الحقيقيّ للحقل ⇒ محاولة انتحال ⇒ رفض.
        raise HTTPException(409, "tenant_id في الجسم يخالف مالك الحقل — مرفوض")
    if not main._pool:
        # fail-closed: قاعدة البيانات غير موصولة ⇒ 503 (لا 200 بجسم خطأ يخدع
        # المستدعي ويُمرَّر للمكوّنات كأنّه نجاح). متّسق مع بقيّة الخدمات.
        raise HTTPException(503, "قاعدة البيانات غير متاحة — حاول لاحقاً")

    # Canonical dual-write: one immutable observation per property. Legacy wide row remains
    # compatibility-only during migration; soil_observations is the governed evidence store.
    property_values = {
        "soil_temperature": (reading.temperature, "degC"),
        "soil_moisture": (reading.moisture_pct, "%"),
        "ph": (reading.ph_level, "pH"),
        "ec": (reading.ec_level, "dS/m"),
        "nitrogen": (reading.n_ppm, "mg/kg"),
        "phosphorus": (reading.p_ppm, "mg/kg"),
        "potassium": (reading.k_ppm, "mg/kg"),
    }
    observations: list[SoilObservation] = []
    base_key = (
        reading.idempotency_key or f"legacy:{reading.sensor_id}:{reading.observed_at.isoformat()}"
    )
    for property_name, (value, unit) in property_values.items():
        if value is None:
            continue
        observation_key = f"{base_key}:{property_name}"
        if len(observation_key) > _OBSERVATION_KEY_MAX_LENGTH:
            raise HTTPException(422, "idempotency_key is too long for this measurement")
        observation = SoilObservation(
            tenant_id=str(resolved_tenant),
            field_id=reading.field_id,
            property=property_name,
            value=float(value),
            unit=unit,
            depth_from_cm=0,
            depth_to_cm=reading.depth_cm,
            observed_at=reading.observed_at,
            source_type=SoilObservationSource.SENSOR,
            source_id=reading.sensor_id,
            quality_status=SoilObservationQuality.UNCALIBRATED,
            quality_flags=["legacy_wide_ingest", "calibration_not_provided"],
            confidence=0.65,
            idempotency_key=observation_key,
            provenance={"legacy_contract": "SoilReading.v9.1"},
        )
        observations.append(observation)

    if not observations:
        raise HTTPException(422, "at least one soil measurement is required")

    canonical_ids: list[str] = []
    async with soil_store.tenant_transaction(main._pool, str(resolved_tenant)) as conn:
        # A key is tenant-wide; two fields must not claim different subsets of it.
        # Always take this lock before the field/projection lock.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"soil-ingest:{resolved_tenant}:{base_key}",
        )
        # Serialise this field before taking the projection-job row lock. Evidence,
        # the compatibility row and the current profile commit together.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"soil-profile:{resolved_tenant}:{reading.field_id}",
        )

        any_inserted = False
        try:
            canonical_ids = await soil_store.ingest_retry_ids(
                conn,
                observations,
                base_key,
                check_observed_at="observed_at" in reading.model_fields_set,
            )
            if canonical_ids is None:
                for observation in observations:
                    inserted = await soil_store.persist_observation_in_transaction(
                        conn, observation
                    )
                    any_inserted = any_inserted or inserted
                canonical_ids = await soil_store.ingest_retry_ids(
                    conn,
                    observations,
                    base_key,
                    check_observed_at="observed_at" in reading.model_fields_set,
                )
                if canonical_ids is None:
                    raise RuntimeError("soil_ingest_persist_or_load_failed")
        except soil_store.SoilIngestConflict:
            raise HTTPException(409, "idempotency_key conflicts with soil reading") from None
        # soil_readings has no natural-key uniqueness constraint. An idempotent
        # canonical retry must not append another compatibility row.
        if any_inserted:
            await conn.execute(
                """
                INSERT INTO soil_readings
                (field_id, sensor_id, temperature_c, moisture_pct,
                 ph, ec_ds_m, nitrogen_mg_kg, phosphorus_mg_kg, potassium_mg_kg,
                 recorded_at, tenant_id, depth_cm)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT DO NOTHING
            """,
                reading.field_id,
                reading.sensor_id,
                reading.temperature,
                reading.moisture_pct,
                reading.ph_level,
                reading.ec_level,
                reading.n_ppm,
                reading.p_ppm,
                reading.k_ppm,
                reading.observed_at,
                resolved_tenant,
                reading.depth_cm,
            )
        snapshot = await soil_store.rebuild_snapshot_in_transaction(
            conn, tenant_id=str(resolved_tenant), field_id=reading.field_id
        )
    return {
        "status": "ingested",
        "canonical_observation_ids": canonical_ids,
        "profile_id": snapshot.profile_id,
        "profile_hash": snapshot.profile_hash,
    }
