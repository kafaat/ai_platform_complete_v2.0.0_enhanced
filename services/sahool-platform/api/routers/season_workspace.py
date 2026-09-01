"""Season workspace API — unified full-season user journey for one field.

This router composes the field, active season, readiness, recommendations, tasks,
activities, soil tests, and timeline into one read model for web/mobile clients.
It does not fabricate values: every unavailable source is returned in `gaps`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.field_models import _FIELD_DETAIL_SELECT, _row_to_field_detail
from api.main import (
    _SOIL_TEST_SELECT,
    _TASK_COLS,
    Permission,
    UserSchema,
    _assert_field_in_tenant,
    _db_unavailable,
    _field_season_context,
    _historical_rain_3d_mm,
    _load_recommendation_policy,
    _row_to_activity,
    _row_to_soil_test,
    _row_to_task,
    require_permission,
    tenant_connection,
)
from api.season_models import _SEASON_SELECT_COLS, _row_to_season
from api.weather_advice import complete_rain_total

router = APIRouter()


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return value


def _truthy(v: Any) -> bool:
    return v is not None and str(v).strip() not in {"", "[]", "{}", "null", "None"}


def _latest_published_soil(soil_tests: list[dict]) -> dict | None:
    for t in soil_tests:
        if t.get("status") == "published" and isinstance(t.get("result"), dict):
            return t["result"]
    for t in soil_tests:
        if isinstance(t.get("result"), dict) and t["result"]:
            return t["result"]
    return None


def _readiness(
    field: dict, season: dict | None, soil_tests: list[dict], state: dict | None
) -> dict:
    """Compute a transparent data-readiness score for full-season guidance."""
    checks: list[dict] = []

    def add(key: str, label_ar: str, ok: bool, required: bool = True, action_ar: str = "") -> None:
        checks.append(
            {
                "key": key,
                "label_ar": label_ar,
                "ok": bool(ok),
                "required": bool(required),
                "action_ar": action_ar,
            }
        )

    soil = _latest_published_soil(soil_tests) or {}
    add(
        "boundary",
        "حدود الحقل مرسومة",
        _truthy(field.get("geometry")),
        True,
        "ارسم حدود الحقل أو استورد GeoJSON/KML.",
    )
    add(
        "location",
        "مركز الحقل متوفر",
        _truthy(field.get("lat")) and _truthy(field.get("lon")),
        True,
        "أضف موقع الحقل لتفعيل الطقس والاستشعار.",
    )
    add(
        "crop",
        "المحصول محدد",
        _truthy(field.get("crop")) or bool((season or {}).get("crops")),
        True,
        "حدد المحصول الرئيسي.",
    )
    add(
        "season",
        "موسم نشط موجود",
        season is not None,
        True,
        "أنشئ الموسم الحالي مع تواريخ الزراعة والحصاد.",
    )
    add(
        "sowing_date",
        "تاريخ الزراعة",
        _truthy((season or {}).get("sowing_date")),
        True,
        "أدخل تاريخ الزراعة لحساب مرحلة النمو و Kc.",
    )
    add(
        "target_yield",
        "هدف الإنتاج",
        _truthy((season or {}).get("target_yield_kg_ha")),
        False,
        "أدخل هدف الإنتاج للمقارنة أثناء الإغلاق.",
    )
    add(
        "soil_ph",
        "pH التربة",
        _truthy(soil.get("ph") or soil.get("soil_ph") or field.get("soil_ph")),
        False,
        "أضف نتيجة pH من المختبر.",
    )
    add(
        "soil_ec",
        "EC/ملوحة التربة",
        _truthy(
            soil.get("ec_ds_m") or soil.get("ec") or soil.get("soil_ec") or field.get("soil_ec")
        ),
        True,
        "أضف EC لأنها تحكم ملوحة القرار.",
    )
    add(
        "water_ec",
        "EC ماء الري",
        _truthy(soil.get("water_ec_ds_m") or soil.get("water_ec") or field.get("water_ec")),
        False,
        "أضف ملوحة ماء الري لتحسين الري والغسيل.",
    )
    add(
        "nutrients",
        "N/P/K",
        any(_truthy(soil.get(k)) for k in ("n_ppm", "p_ppm", "k_ppm", "n", "p", "k")),
        False,
        "أضف N/P/K لتحسين التسميد.",
    )
    add(
        "field_state",
        "الحالة الموحدة محسوبة",
        state is not None and _truthy(state.get("validity")),
        True,
        "أعد حساب حالة الحقل.",
    )

    total_weight = sum(2 if c["required"] else 1 for c in checks)
    ok_weight = sum((2 if c["required"] else 1) for c in checks if c["ok"])
    score = round((ok_weight / total_weight) * 100) if total_weight else 0
    missing = [c for c in checks if not c["ok"]]
    if score >= 85:
        label = "جاهز لتوصيات دقيقة"
        level = "ready"
    elif score >= 60:
        label = "جاهز جزئياً — توصيات استرشادية"
        level = "partial"
    else:
        label = "بيانات ناقصة — يلزم استكمال ملف الحقل"
        level = "insufficient"
    return {"score": score, "level": level, "label_ar": label, "checks": checks, "missing": missing}


def _next_actions(readiness: dict, recommendations: dict | None, tasks: list[dict]) -> list[dict]:
    actions: list[dict] = []
    for gap in readiness.get("missing", [])[:4]:
        actions.append(
            {
                "type": "data_gap",
                "priority": 1 if gap.get("required") else 3,
                "title_ar": gap.get("label_ar"),
                "action_ar": gap.get("action_ar"),
                "executable": False,
            }
        )
    for rec in (recommendations or {}).get("recommendations", [])[:5]:
        actions.append(
            {
                "type": "recommendation",
                "priority": rec.get("priority", 3),
                "title_ar": rec.get("title_ar") or rec.get("title") or rec.get("kind", "توصية"),
                "action_ar": rec.get("action_ar")
                or rec.get("rationale_ar")
                or rec.get("message_ar"),
                "requires_review": (recommendations or {}).get("requires_review", True),
                "executable": not (recommendations or {}).get("requires_review", True),
            }
        )
    for task in tasks[:5]:
        actions.append(
            {
                "type": "task",
                "priority": task.get("priority", 3),
                "title_ar": task.get("notes") or task.get("task_type") or "مهمة ميدانية",
                "action_ar": task.get("status"),
                "task_id": task.get("task_id"),
                "executable": True,
            }
        )
    return sorted(actions, key=lambda a: int(a.get("priority") or 3))[:8]


@router.get("/api/v1/fields/{field_id}/season-workspace")
async def season_workspace(
    field_id: str,
    user: UserSchema = Depends(require_permission(Permission.FIELD_VIEW)),
):
    """Unified read model for a complete season user journey.

    Returns one honest payload for the mobile/web "My Fields → Field Workspace" flow:
    field profile, active season, readiness score, canonical state, recommendations,
    tasks, activities, soil tests, timeline and next actions. External/weather-derived
    recommendations are best-effort and reported in `gaps` when unavailable.
    """
    from api.connectors.openmeteo import fetch_current, fetch_daily_forecast
    from api.field_state_projection import recompute_field_state
    from api.recommendations_hub import RecommendationContext, build_recommendations

    gaps: list[dict] = []
    recommendations: dict | None = None

    try:
        async with tenant_connection(user) as conn:
            await _assert_field_in_tenant(conn, field_id)
            field_row = await conn.fetchrow(
                f"SELECT {_FIELD_DETAIL_SELECT} FROM fields WHERE field_id = $1 AND tenant_id = $2::uuid",
                field_id,
                str(user.tenant_id),
            )
            if field_row is None:
                raise HTTPException(status_code=404, detail="الحقل غير موجود ضمن هذا المستأجِر")
            field = _jsonable(_row_to_field_detail(field_row))

            season_row = await conn.fetchrow(
                f"SELECT {_SEASON_SELECT_COLS} FROM seasons WHERE field_id = $1 "
                "ORDER BY CASE WHEN status='active' THEN 0 ELSE 1 END, created_at DESC LIMIT 1",
                field_id,
            )
            season = _jsonable(_row_to_season(season_row)) if season_row else None

            activity_rows = await conn.fetch(
                "SELECT activity_id, field_id, season_id, activity_type, title_ar, details, "
                "scheduled_for, performed_on, status, created_at FROM activities "
                "WHERE field_id = $1 ORDER BY COALESCE(performed_on, scheduled_for, created_at) DESC LIMIT 50",
                field_id,
            )
            activities = [_jsonable(_row_to_activity(r)) for r in activity_rows]

            soil_rows = await conn.fetch(
                f"SELECT {_SOIL_TEST_SELECT} FROM soil_lab_tests WHERE field_id = $1 ORDER BY created_at DESC LIMIT 20",
                field_id,
            )
            soil_tests = [_jsonable(_row_to_soil_test(r)) for r in soil_rows]

            task_rows = await conn.fetch(
                f"SELECT {_TASK_COLS} FROM field_tasks WHERE field_id = $1 "
                "AND status NOT IN ('done','completed','cancelled') "
                "ORDER BY priority ASC, recommended_date ASC NULLS LAST, created_at DESC LIMIT 20",
                field_id,
            )
            tasks = [_jsonable(_row_to_task(r)) for r in task_rows]

            try:
                state = _jsonable((await recompute_field_state(conn, field_id))["state"])
            except Exception as e:  # noqa: BLE001
                state = None
                gaps.append(
                    {
                        "source": "field_state",
                        "message_ar": f"تعذّر حساب الحالة الموحدة: {type(e).__name__}",
                    }
                )

            try:
                lat, lon, crop, stage, sowing_date = await _field_season_context(conn, field_id)
                enabled_ids = await _load_recommendation_policy(conn)
            except Exception as e:  # noqa: BLE001
                lat = lon = None
                crop = field.get("crop") or ((season or {}).get("crops") or [None])[0]
                stage = None
                sowing_date = None
                enabled_ids = None
                gaps.append(
                    {
                        "source": "recommendation_context",
                        "message_ar": f"سياق التوصيات غير مكتمل: {type(e).__name__}",
                    }
                )

        # Recommendations use live weather best-effort after releasing DB connection.
        try:
            ctx = RecommendationContext(
                field_id=field_id,
                crop=crop,
                stage=stage,
                today=date.today(),
                sowing_date=sowing_date,
            )
            truths = ((state or {}).get("agronomic") or {}).get("operational_truths") or {}
            ctx.salinity_class = truths.get("salinity_class")
            ctx.crop_vigor = truths.get("crop_vigor")
            weather_available = False
            if lat is not None and lon is not None:
                forecast = await fetch_daily_forecast(lat, lon, days=3)
                current = await fetch_current(lat, lon)
                today_fc = forecast[0] if forecast else None
                ctx.et0_mm = today_fc.et0_mm if today_fc and today_fc.et0_mm is not None else None
                # الغيابُ يمرّ `None` — والقواعدُ تصمت عليه بدل أن تُوصي على صفرٍ مُختلَق.
                ctx.rain_recent_mm = current.precipitation_mm
                ctx.forecast_rain_mm, _ = complete_rain_total(
                    [f.precipitation_mm for f in forecast[1:3]], expected_count=2
                )
                ctx.temp_c = current.temperature_c
                ctx.humidity_pct = current.humidity_pct
                _fc3, _ = complete_rain_total(
                    [f.precipitation_mm for f in forecast[:3]], expected_count=3
                )
                ctx.rain_mm_3d = await _historical_rain_3d_mm(lat, lon, _fc3)
                weather_available = True
            recs = [r.to_dict() for r in build_recommendations(ctx, enabled_ids=enabled_ids)]
            recommendations = {
                "field_id": field_id,
                "crop": crop,
                "stage": stage,
                "weather_available": weather_available,
                "field_state": {
                    "validity": (state or {}).get("validity"),
                    "execution_mode": (state or {}).get("execution_mode"),
                    "confidence_level": (state or {}).get("confidence_level"),
                    "reasons_ar": (state or {}).get("reasons_ar", []),
                },
                "requires_review": (state or {}).get("execution_mode") != "auto",
                "recommendations": recs,
            }
        except Exception as e:  # noqa: BLE001
            gaps.append(
                {
                    "source": "recommendations",
                    "message_ar": f"تعذّر توليد التوصيات: {type(e).__name__}",
                }
            )

        timeline = {
            "events": [
                {
                    "timestamp": a.get("performed_on")
                    or a.get("scheduled_for")
                    or a.get("created_at"),
                    "category": "operation",
                    "event_type": a.get("activity_type"),
                    "summary_ar": a.get("title_ar") or a.get("activity_type"),
                    "payload": a,
                }
                for a in activities[:30]
            ],
            "source": "activities_snapshot",
        }
        readiness = _readiness(field, season, soil_tests, state)
        return {
            "field_id": field_id,
            "field": field,
            "active_season": season,
            "readiness": readiness,
            "canonical_state": state,
            "recommendations": recommendations,
            "tasks": tasks,
            "activities": activities,
            "soil_tests": soil_tests,
            "timeline": timeline,
            "next_actions": _next_actions(readiness, recommendations, tasks),
            "gaps": gaps,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _db_unavailable("قراءة مساحة عمل الموسم", e) from e
