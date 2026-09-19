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
    guarded = _function(ADAPTER, "guarded_runtime_context")
    assert guarded is not None, "اختفى المُهيّئ المحروس — حدِّث القسم"

    # **النوعُ يُطابَق، لا وجودُ `raise`.** أوّلُ صياغةٍ قبلت أيَّ استثناء ووجودَ الاسم في
    # النصّ — وإعلانُ الصنف وحده يُرضيها. فاستبدالُ `MissingCanonicalFieldState` بـ
    # `RuntimeError` كان يُبقيها خضراء والشرطُ المسجَّل قد تغيّر (مراجعة #1020).
    raised = {
        node.exc.func.id
        for node in ast.walk(guarded)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
    }
    assert "MissingCanonicalFieldState" in raised, (
        f"المُهيّئ لم يعد يرفع `MissingCanonicalFieldState` (يرفع {sorted(raised)}) — "
        "الشرطُ القبليُّ تغيّر، حدِّث القسم"
    )

    # وقبليّةُ الشرط تُقاس بموضعه: يرفع قبل بناء أيّ مدخلٍ للمحرّك، لا بعده.
    guard_line = min(
        node.lineno
        for node in ast.walk(guarded)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "MissingCanonicalFieldState"
    )
    returns = [n.lineno for n in ast.walk(guarded) if isinstance(n, ast.Return)]
    assert returns and guard_line < min(returns), (
        "صار الرفعُ بعد تركيب المُخرَج — الشرطُ لم يعد قبليّاً، حدِّث القسم"
    )


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
        # **الاستيرادُ وحدَه لا يكفي.** `from api import main` ثمّ `main.tenant_connection(…)`
        # لا يُسجَّل اسماً مستورَداً، فتمرّ الوحدةُ وقد نالت الاتّصالَ الذي يقول العائقُ إنّها
        # تفتقده (مراجعة #1020). فيُقرأ **استعمالُ** الاسم أيضاً: نداءً أو سمة.
        used = _attribute_or_call_names(path)
        assert "tenant_connection" not in used and not any(
            "tenant_connection" in n for n in names
        ), f"{path.name}: صار يملك اتّصالاً محدوداً بالمستأجر — حدِّث القسم"


def _attribute_or_call_names(path: Path) -> set[str]:
    """أسماءُ ما يُستعمَل نداءً أو سمةً في الوحدة — لا ما يُستورَد فقط."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    return names


def _handler_call_line(tree: ast.AST) -> int:
    """سطرُ **نداء** المحرّك نفسِه، لا سطرُ النصّ الحرفيّ الذي يسبقه دائماً."""
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "handle_recommendation_request"
    ]
    assert lines, "اختفى نداءُ `handle_recommendation_request` من المسار — حدِّث القسم"
    return min(lines)


def test_the_route_reads_canonical_after_the_engine_not_before() -> None:
    """العائقُ (ج): ترتيبُ اللقطة يُقاس بنداء المحرّك نفسِه، لا بنصٍّ يسبقه.

    أوّلُ صياغةٍ أرست المقارنةَ على النصّ الحرفيّ `path="…"` الذي يُبنى به الطلب — وهو
    مكتوبٌ قبل النداء دائماً، فتقديمُ القراءة إلى ما بين البناء والنداء كان يمرّ أخضر
    (مراجعة #1020). والمرساةُ الآن نداءُ `handle_recommendation_request` في شجرة النحو.

    **والمسارانِ يُقاسان معاً:** القسمُ يسمّي `/api/v1/recommendations` مدخلاً إنتاجيّاً،
    و`load_agronomic_context` تقع في نظيره `/for-field`. فيلزم إثباتُ الاثنين: أنّ
    الأساسيّ ما زال بلا قراءةٍ قانونيّة أصلاً، وأنّ نظيرَه يقرؤها **بعد** المحرّك.
    """
    base = _function(ROUTE, "recommendations")
    assert base is not None
    base_body = ast.dump(base)
    assert "load_agronomic_context" not in base_body, (
        "المدخلُ الأساسيّ `/api/v1/recommendations` صار يقرأ الحالةَ القانونيّة — "
        "العائقُ (ب) تغيّر على المسار الذي يسمّيه القسم، فحدِّثه قبل البناء عليه"
    )

    for_field = _function(ROUTE, "recommendations_for_field")
    assert for_field is not None
    engine_call = _handler_call_line(for_field)
    canonical_read = min(
        node.lineno
        for node in ast.walk(for_field)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_agronomic_context"
    )
    assert engine_call < canonical_read, (
        "صارت قراءةُ السياق القانونيّ تسبق نداءَ المحرّك — العائقُ (ج) زال أو تغيّر، "
        "فحدِّث قسمَ AI-RUNTIME-WIRING-01 قبل البناء عليه"
    )


#: كلُّ عائقٍ ونصٌّ مميِّزٌ له في القسم. العناوينُ وحدَها لا تكفي: يمكن أن يسقط أيُّ عائقٍ
#: ويبقى العنوانان فيمرّ الشاهد (مراجعة #1020). فيُثبَّت **لبُّ** كلّ دعوى لا ترويستُها.
NARRATED_OBSTACLES = {
    "تعارضُ التزامن": "`async`",
    "الحالةُ مطلوبةٌ قبل المحرّك": "قبل** توليد التوصية",
    "ترتيبُ اللقطة مقصود": "لقطةٌ واحدة",
    "تصحيحُ الاستدلال": "تصحيحٌ لاستدلالٍ لي",
    "ثمنُ المعاملة الممتدّة معلَن": "معاملةُ مستأجرٍ مفتوحةٌ طوال حساب المحرّك",
}


def test_the_registry_still_narrates_these_three_obstacles() -> None:
    """الاتّجاهُ الآخر: شاهدٌ بلا قسمٍ يرويه دعوًى بلا موضع — ويُقاس لبُّ كلّ عائق."""
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index("## AI-RUNTIME-WIRING-01")
    section = text[start : text.find("\n## ", start + 1)]
    assert "قياسُ موضع التوصيل قبل بناء الخطوة ②" in section
    assert "ما يترتّب على القياس" in section
    missing = [name for name, needle in NARRATED_OBSTACLES.items() if needle not in section]
    assert not missing, (
        f"سقط من القسم سردُ: {missing} — الشاهدُ يحرس الدعوى، فأعِدها أو أعِد صياغة الشاهد معها"
    )
