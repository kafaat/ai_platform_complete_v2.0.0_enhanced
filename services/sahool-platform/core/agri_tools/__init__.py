"""Agri Tools Center — سجلّ أدوات زراعيّة معياريّ (اكتشاف تلقائيّ عند الاستيراد)."""

from __future__ import annotations

from .registry import (  # noqa: F401
    CATEGORIES,
    Tool,
    ToolParam,
    discover,
    get_tool,
    list_tools,
    register,
    run_tool,
)

# اكتشاف تلقائيّ: استيراد الحزمة يُسجّل كلّ الأدوات في tools/.
discover()
