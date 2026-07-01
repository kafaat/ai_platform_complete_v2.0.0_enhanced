"""إسقاط شفافيّة الـHarness للواجهة (V55 — المرحلة ٥).

الواجهة يجب أن تُظهر للمستخدم بصدق: ماذا يرى الوكيل، ما قدراته، أيّ أداة استُخدمت،
وهل الإجراء تمّ أم ينتظر موافقة. هذه الدالّة تبني **إسقاطاً آمناً للعرض** من لقطة الرصد
(المرحلة ٣) ونتائج الأدوات (المرحلة ٢) وطلبات الموافقة (المرحلة ٤) — بلا تسريب أسرار
أو حمولات خام (بيانات الأدوات لا تُعرَض هنا، فقط بيانات وصفيّة: أداة/نتيجة/خطورة).
"""

from __future__ import annotations

from typing import Any


def _tool_call_view(tc: dict[str, Any]) -> dict[str, Any]:
    """إسقاط وصفيّ لاستدعاء أداة (بلا الحمولة الخام)."""
    return {
        "tool": tc.get("tool"),
        "outcome": tc.get("outcome"),
        "risk": tc.get("risk"),
        "capability": tc.get("capability"),
        "requires_approval": bool(tc.get("requires_approval", False)),
        "reason": tc.get("reason"),
    }


def _approval_view(pa: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pa.get("id"),
        "tool": pa.get("tool"),
        "risk": pa.get("risk"),
        "status": pa.get("status"),
        "decided_by": pa.get("decided_by"),
    }


def build_transparency(
    *,
    observation: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]] | None = None,
    pending_approvals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """يبني إسقاط الشفافيّة الذي تعرضه واجهة الشات."""
    obs = observation or {}
    policy = obs.get("policy") or {}
    raster = obs.get("raster") or {}
    return {
        "sees": {
            "field_id": obs.get("field_id"),
            "active_layer": obs.get("active_layer"),
            "selected_date": obs.get("selected_date"),
            "raster_ready": bool(raster.get("ready", False)),
            "weather_source": obs.get("weather_source"),
            "blind": bool(obs.get("blind", True)),
        },
        "notes": list(obs.get("notes") or []),
        "capabilities": list(policy.get("allowed_capabilities") or []),
        "data_sharing_level": policy.get("data_sharing_level") or "local_only",
        "tool_calls": [_tool_call_view(t) for t in (tool_calls or []) if isinstance(t, dict)],
        "pending_approvals": [
            _approval_view(p) for p in (pending_approvals or []) if isinstance(p, dict)
        ],
    }
