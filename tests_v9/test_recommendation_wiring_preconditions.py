"""`AI-RUNTIME-WIRING-01` الخطوة ② — الشروطُ المقيسة لموضع التوصيل، مربوطةً بالشجرة.

قسمُ الفجوة يقول إنّ البند «وصِّل في `orchestrate_recommendation`» غيرُ قابلٍ للتنفيذ
حرفيّاً، ويبني عليه قرارَ نطاق. **ودعوى كهذه تتعفّن بصمت**: تُصلَح الشجرةُ يوماً فيبقى
السجلُّ يروي عائقاً زال، أو تُنقَل دالّةٌ فيبطل الاستشهاد. فهذا الملفّ يُثبّت الشروطَ
الثلاثةَ في الشجرة نفسِها: إن زال عائقٌ احمرّ الشاهدُ **وطالب بتحديث القسم**، لا العكس.

لا يقيس هذا الملفّ سلوكاً إنتاجيّاً ولا يفرض تصميماً؛ يقيس أنّ الوصفَ المسجَّل صادق.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests_v9.static_reading import imports_of

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services/sahool-platform"
PIPELINE = ROOT / "shared/ai/recommendation_runtime/recommendation_runtime_pipeline.py"
ADAPTER = ROOT / "shared/ai/recommendation_runtime/runtime_guardrail_adapter.py"
ORCHESTRATOR = PLATFORM / "core/internal_orchestrator.py"
API_ADAPTER = PLATFORM / "core/api_adapter.py"
ROUTE = PLATFORM / "api/routers/recommendations.py"
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"


def _function(path: Path, name: str) -> ast.AST | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_the_pipeline_entry_is_async_while_the_orchestrator_is_not() -> None:
    """العائقُ (أ): لا يُستدعى `async` من دالّةٍ متزامنة داخل حلقةٍ عاملة بلا إعادة هيكلة."""
    execute = _function(PIPELINE, "execute")
    assert isinstance(execute, ast.AsyncFunctionDef), "مدخلُ الخطّ لم يعد `async` — حدِّث القسم"

    orchestrate = _function(ORCHESTRATOR, "orchestrate_recommendation")
    assert isinstance(orchestrate, ast.FunctionDef) and not isinstance(
        orchestrate, ast.AsyncFunctionDef
    ), "المايسترو صار `async` — العائقُ (أ) زال، فحدِّث القسمَ قبل البناء عليه"

    handle = _function(API_ADAPTER, "handle_recommendation_request")
    assert isinstance(handle, ast.FunctionDef) and not isinstance(handle, ast.AsyncFunctionDef), (
        "المحوّلُ صار `async` — حدِّث القسم"
    )


def test_the_guarded_adapter_still_requires_canonical_state_before_the_engine() -> None:
    """العائقُ (ب): الشرطُ قبليٌّ لا بعديّ — يرفع قبل أن يُبنى أيُّ مدخلٍ للمحرّك."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert "MissingCanonicalFieldState" in source
    guarded = _function(ADAPTER, "guarded_runtime_context")
    assert guarded is not None
    raises = [n for n in ast.walk(guarded) if isinstance(n, ast.Raise)]
    assert raises, "المُهيّئ لم يعد يرفع عند غياب الحالة القانونيّة — حدِّث القسم"


#: مصادرُ الحالة القانونيّة المقيسة في الشجرة — تُسمّى صراحةً لا تُلتقَط بكلمةٍ مفتاحيّة.
#: `core.canonical_schemas` **ليست** منها: مخطَّطاتُ كيانات (`UserSchema`) يستوردها
#: المايسترو للتوقيع، لا حالةُ حقلٍ مقروءةٌ من مصدر. أوّلُ صياغةٍ لهذا الشاهد التقطتها
#: بكلمة «canonical» فاحمرّ على دعوًى صادقة — قارئٌ أوسعُ من دعواه يُنتج حمرةً كاذبة
#: كما يُنتج الأضيقُ خُضرةً كاذبة.
CANONICAL_STATE_SOURCES = (
    "persisted_canonical_repositories",
    "agronomic_state_consumers",
    "canonical_water_state",
    "canonical_soil_state",
    "canonical_spectral_state",
    "field_state_projection",
)


def test_no_module_that_reaches_the_engine_can_read_the_canonical_state() -> None:
    """العائقُ (ب) تتمّةً: المايسترو والمحوّلُ بلا اتّصالٍ ولا مصدرِ حالةٍ قانونيّة."""
    for path in (ORCHESTRATOR, API_ADAPTER):
        names = imports_of(path)
        offenders = [n for n in names if any(src in n for src in CANONICAL_STATE_SOURCES)]
        assert not offenders, (
            f"{path.name}: صار يستورد مصدرَ حالةٍ قانونيّة ({offenders}) — "
            "العائقُ (ب) تغيّر، حدِّث القسمَ قبل البناء عليه"
        )
        assert not any("tenant_connection" in n for n in names), (
            f"{path.name}: صار يملك اتّصالاً محدوداً بالمستأجر — حدِّث القسم"
        )


def test_the_route_reads_canonical_after_the_engine_not_before() -> None:
    """العائقُ (ج): ترتيبُ اللقطة مقصودٌ وموثَّق — يُقاس بموضعه لا بالذاكرة."""
    source = ROUTE.read_text(encoding="utf-8")
    engine_call = source.index('path="/api/v1/recommendations/for-field"')
    canonical_read = source.index("load_agronomic_context(conn")
    assert engine_call < canonical_read, (
        "صارت قراءةُ السياق القانونيّ تسبق المحرّك — العائقُ (ج) زال أو تغيّر، "
        "فحدِّث قسمَ AI-RUNTIME-WIRING-01 قبل البناء عليه"
    )


def test_the_registry_still_narrates_these_three_obstacles() -> None:
    """الاتّجاهُ الآخر: شاهدٌ بلا قسمٍ يرويه دعوًى بلا موضع."""
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index("## AI-RUNTIME-WIRING-01")
    section = text[start : text.find("\n## ", start + 1)]
    assert "قياسُ موضع التوصيل قبل بناء الخطوة ②" in section
    assert "ما يترتّب على القياس" in section
