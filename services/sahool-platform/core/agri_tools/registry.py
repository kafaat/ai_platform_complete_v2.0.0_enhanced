"""core/agri_tools/registry.py — سجلّ أدوات زراعيّة معياريّ (Agri Tools Center).

استلهامٌ من it-tools لكن متخصّص زراعيّاً: مركز أدوات صغيرة عالية التردّد (حساب تغطية
الريّ المحوريّ، حجم الريّ، الأسمدة، مؤشّرات الغطاء، مساحة المضلّع…) في واجهة واحدة،
مربوطة بالحقول/المواسم/المؤشّرات.

**معياريّ:** إضافة أداة = إسقاط ملفّ في `tools/` يسجّل نفسه عبر `@register` — بلا تعديل
المنصّة (اكتشاف تلقائيّ عند الإقلاع). كلّ أداة دالّة **نقيّة حتميّة** (لا I/O، لا حالة):
`compute(inputs: dict) -> dict`. النقاء يجعلها قابلة للاختبار والتشغيل في المتصفّح أو
الخادم بلا فرق.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# فئات الأدوات (للتجميع في الواجهة).
CATEGORIES = ("irrigation", "nutrition", "geo", "remote_sensing", "conversion")


@dataclass(frozen=True)
class ToolParam:
    """وصف مُدخَل أداة (للتحقّق + توليد نموذج الواجهة تلقائيّاً)."""

    name: str
    kind: str  # number | text | select | geojson | bool
    label_ar: str
    unit: str = ""
    required: bool = True
    default: object = None
    options: tuple = ()  # لـkind=select
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Tool:
    """أداة زراعيّة: تعريف + دالّة حساب نقيّة."""

    id: str
    name_ar: str
    category: str
    description_ar: str
    params: list[ToolParam]
    compute: Callable[[dict], dict]
    result_unit_ar: str = ""
    tags: tuple = field(default_factory=tuple)


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    """يُسجّل أداة (يُرفَض المعرّف المكرّر أو الفئة المجهولة — منع انحدار صامت)."""
    if tool.id in _REGISTRY:
        raise ValueError(f"أداة بمعرّف مكرّر: {tool.id}")
    if tool.category not in CATEGORIES:
        raise ValueError(f"فئة مجهولة لـ{tool.id}: {tool.category} (المتاح: {CATEGORIES})")
    _REGISTRY[tool.id] = tool
    return tool


def get_tool(tool_id: str) -> Tool | None:
    return _REGISTRY.get(tool_id)


def list_tools(category: str | None = None) -> list[Tool]:
    tools = sorted(_REGISTRY.values(), key=lambda t: (t.category, t.id))
    return [t for t in tools if category is None or t.category == category]


def _coerce(param: ToolParam, value):
    """يتحقّق/يحوّل قيمة مُدخَل واحدة حسب نوعها (يرفع ValueError برسالة عربيّة)."""
    if value is None:
        if param.required and param.default is None:
            raise ValueError(f"مُدخَل مطلوب مفقود: {param.name}")
        value = param.default
    if value is None:
        return None
    if param.kind == "number":
        try:
            value = float(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{param.name}: قيمة عدديّة غير صالحة ({value})") from e
        if param.min is not None and value < param.min:
            raise ValueError(f"{param.name}: أقلّ من الحدّ الأدنى {param.min}")
        if param.max is not None and value > param.max:
            raise ValueError(f"{param.name}: أكبر من الحدّ الأقصى {param.max}")
    elif param.kind == "select" and param.options and value not in param.options:
        raise ValueError(f"{param.name}: خيار غير صالح ({value}) — المتاح {param.options}")
    elif param.kind == "bool":
        value = bool(value)
    return value


def run_tool(tool_id: str, inputs: dict) -> dict:
    """يُشغّل أداة بمُدخَلات: يتحقّق منها، يطبّق الافتراضات، ثمّ يستدعي الحساب النقيّ.

    يرفع KeyError إن لم تُعرَف الأداة، وValueError على مُدخَل غير صالح (fail-loud)."""
    tool = _REGISTRY.get(tool_id)
    if tool is None:
        raise KeyError(f"أداة غير معروفة: {tool_id}")
    inputs = inputs or {}
    validated = {p.name: _coerce(p, inputs.get(p.name)) for p in tool.params}
    return tool.compute(validated)


def discover() -> int:
    """يستورد كلّ وحدات `tools/` فتُسجّل نفسها (اكتشاف تلقائيّ). يُرجِع العدد المُكتشَف."""
    import importlib
    import pkgutil

    from . import tools as tools_pkg

    for mod in pkgutil.iter_modules(tools_pkg.__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{tools_pkg.__name__}.{mod.name}")
    return len(_REGISTRY)
