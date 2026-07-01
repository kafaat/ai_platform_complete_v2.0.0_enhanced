"""Tool-call governance hardening (V58.2b) — arg validation + result sanitization.

Two defenses on the governed tool loop:

1. ``validate_tool_args`` — reject a call whose params are malformed / missing a required
   field / violate a known enum BEFORE execution, returning an explicit
   ``malformed_tool_call`` outcome instead of silently running with ``{}``.
2. ``sanitize_tool_result`` — before a read-tool result is fed back to the LLM, cap its
   size, allowlist fields, strip HTML/markdown/zero-width chars from strings, and tag the
   source. A tool result is untrusted input to the model — this blocks tool-result
   prompt-injection ("tool poisoning").

Pure Python + stdlib. Enum/required knowledge is read from the tool registry/schema.
"""

from __future__ import annotations

import json
import re
from typing import Any

from shared.ai.tool_registry import TOOLS

# Known enum constraints (mirror shared/ai/tool_schema); unknown params are unconstrained.
_ENUMS: dict[str, set[str]] = {
    "source": {"truecolor", "ndvi", "multi_index", "falsecolor"},
    "basis": {"multi_index", "ndvi_stability", "soil", "yield", "weather", "hybrid"},
    "lab_panel": {
        "fertility",
        "salinity",
        "micronutrients",
        "irrigation_suitability",
        "comprehensive",
        "standard",
        "full",
        "complete",
        "advanced",
    },
    "product_type": {"fertilizer", "lime", "seed", "irrigation"},
    "sampling_strategy": {"zone", "grid", "hybrid"},
}

_REQUIRED_BY_TOOL: dict[str, list[str]] = {
    t.name: [p for p, spec in t.params.items() if not str(spec).endswith("?")] for t in TOOLS
}

# result sanitization
_HTML_TAG = re.compile(r"<[^>]+>")
_ZERO_WIDTH = re.compile(r"[​-‏‪-‮﻿]")
_ALLOWED_RESULT_KEYS = {
    "tool_call_id",
    "tool",
    "outcome",
    "reason",
    "risk",
    "capability",
    "requires_approval",
    "data",
    "approval_id",
    "params",
    "input_hash",
    "field_id",
    "result_summary",
    "index",
    "layer",
    "ui_action",
    "imagery_timeline",
    "weather_history",
    "alerts_context",
    "drawing_context",
    "operation_windows",
    "readiness",
    "provider_native",
}
_MAX_RESULT_BYTES = 8000


def validate_tool_args(tool_name: str, params: Any) -> tuple[bool, str | None]:
    """(ok, reason). Malformed/missing-required/bad-enum ⇒ (False, reason)."""
    if not isinstance(params, dict):
        return False, "invalid_arguments_not_object"
    for req in _REQUIRED_BY_TOOL.get(tool_name, []):
        if params.get(req) in (None, ""):
            return False, f"missing_required:{req}"
    for key, allowed in _ENUMS.items():
        val = params.get(key)
        if val is not None and str(val).strip().lower() not in allowed:
            return False, f"invalid_enum:{key}"
    return True, None


def malformed_result(tool_name: str, call_id: str, reason: str) -> dict[str, Any]:
    """Explicit non-executed result for a malformed tool call (fail-closed)."""
    return {
        "tool_call_id": call_id,
        "tool": tool_name,
        "outcome": "malformed_tool_call",
        "reason": reason,
        "data": None,
        "requires_approval": False,
        "result_summary": f"rejected:{reason}",
    }


def _clean_str(s: str) -> str:
    s = _HTML_TAG.sub("", s)
    s = _ZERO_WIDTH.sub("", s)
    return s


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated-depth]"
    if isinstance(value, str):
        return _clean_str(value)
    if isinstance(value, dict):
        return {k: _scrub(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, depth + 1) for v in value[:200]]
    return value


def sanitize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Allowlist fields, strip HTML/zero-width, cap size, tag source. Never raises."""
    if not isinstance(result, dict):
        return {"outcome": "sanitized_non_dict_result", "data": None, "_sanitized": True}
    out = {k: _scrub(v) for k, v in result.items() if k in _ALLOWED_RESULT_KEYS}
    # size cap on the serialized payload (defence against oversized/poisoned results).
    try:
        blob = json.dumps(out, ensure_ascii=False)
        if len(blob.encode("utf-8")) > _MAX_RESULT_BYTES:
            out["data"] = "[omitted:result_too_large]"
            out["result_summary"] = "truncated_oversized_result"
    except Exception:  # noqa: BLE001 — تسلسل فشل ⇒ لا نمرّر حمولة غير موثوقة
        out = {"tool": out.get("tool"), "outcome": out.get("outcome"), "data": None}
    out["_sanitized"] = True
    out["_source"] = "governed_tool"
    return out
