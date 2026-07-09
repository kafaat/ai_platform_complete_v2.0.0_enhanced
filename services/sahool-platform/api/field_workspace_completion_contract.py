"""Field Workspace completion contract (UI-34).

ثابت توثيقي/اختباري يحدد القراءات التي أصبحت مملوكة للـ backend بعد إغلاق
UI-31..UI-35. لا يُستخدم لتوليد بيانات تشغيلية.
"""

FIELD_WORKSPACE_COMPLETION_CONTRACT = {
    "context": ["field_id", "season_id"],
    "backend_owned_reads": [
        "GET /api/v1/fields/{field_id}/readiness",
        "GET /api/v1/fields/{field_id}/data-completeness",
        "GET /api/v1/fields/{field_id}/unified-timeline",
        "GET /api/v1/fields/{field_id}/priority-queue",
        "GET /api/v1/fields/{field_id}/available-dates",
        "GET /api/v1/fields/{field_id}/imagery/timeline",
        "GET /api/v1/fields/{field_id}/weather/operation-windows",
        "GET /api/v1/fields/{field_id}/weather/disease-risk",
        "GET /api/v1/fields/{field_id}/weather/irrigation-advice",
        "GET /api/v1/irrigation/schedules?field_id={field_id}",
    ],
    "fields_router_allowed_workspace_routes": [],
    "no_frontend_fabrication": [
        "timeline-events",
        "recommendations",
        "reports",
        "irrigation-plans",
        "imagery-dates",
    ],
}
