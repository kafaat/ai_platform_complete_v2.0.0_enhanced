"""`AI-RUNTIME-WIRING-01` — خطُّ التوصية المحروس بلا مستهلك، والحدُّ الذي يمنع توصيلَه خطأً.

**المقيس، لا المفترَض:** `RecommendationRuntimePipeline` (`services/ai_agronomist/`) له
صفرُ مراجع غير اختباريّة، ومستهلكُه الوحيد اختبارٌ بمحرّكٍ وهميّ. والمدخلُ الإنتاجيّ
الوحيد الذي يُنتج توصيةً ويُثبِتها يعيش في المنصّة، وصورةُ المنصّة **لا تنسخ**
`services/ai_agronomist` (`Dockerfile:33-34`) — فاستيرادُه من شيفرة المنصّة يعمل في
الاختبارات (الجذرُ على المسار) وينكسر في الحاوية. هذا الملفّ يحرس حقيقتين:

١) صفرُ المستهلكين مقيَّدٌ بحالة القسم في السجلّ: مستهلكٌ يظهر بلا قلبِ الحالة ⇒ أحمر،
   وقلبُ الحالة بلا مستهلك ⇒ أحمر. لا يُقاس «الإغلاق» من وجود الملفّ.
٢) لا شيفرةَ تدخل صورةَ المنصّة تستورد `ai_agronomist` عبر حدّ الحاوية — الحدُّ يُقرأ من
   `COPY` في الصورة لا من افتراض.

**حدودُ القراءة، مُصلَحةٌ بمراجعة #1018:** القارئُ الأوّل رأى أوّلَ مُعامِلٍ بعد `COPY`
وحده، فكانت `COPY --chown=… services/ai_agronomist /app/` و`COPY . /app` تمرّان؛ وأسقط
`from . import X` (وحدتُه `None`) و`importlib.import_module("…")` الحرفيّ؛ وقصر مسحَ
الحدّ على شجرة المنصّة بينما تنسخ الصورةُ `shared/` أيضاً. كلُّ واحدةٍ من هذه صارت
مُغطّاةً بشاهدٍ مباشر أدناه.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path, PurePosixPath

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
#: اسمُ الوحدة نفسُه في موضعَيها: القشرةُ في `services/ai_agronomist/` والأصلُ في
#: `shared/ai/recommendation_runtime/` — المستهلكُ يُقاس أينما استورد.
PIPELINE_MODULE = "recommendation_runtime_pipeline"
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"
PLATFORM = ROOT / "services/sahool-platform"
SHARED = ROOT / "shared"
PLATFORM_DOCKERFILE = PLATFORM / "Dockerfile"
#: الشجرةُ التي يمنع هذا الحدُّ دخولَها صورةَ المنصّة.
FORBIDDEN_IN_PLATFORM_IMAGE = "services/ai_agronomist"


def _is_test_path(path: Path) -> bool:
    """اختباريٌّ بالمجلَّد أو بأيٍّ من عُرفَي التسمية (`test_*.py` و`*_test.py`).

    العُرفُ الثاني قائمٌ في الشجرة (`services/sahool-platform/smoke_e2e_test.py`)، وإسقاطُه
    كان يُصنّف اختباراً مستهلكاً إنتاجيّاً.
    """
    parts = path.parts
    if any(p in {"tests", "tests_v9"} for p in parts):
        return True
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def _imports_of(path: Path) -> list[str]:
    """أسماءُ كلِّ ما تستورده الوحدة: المطلق · النسبيّ بلا وحدة · الحرفيّ الديناميكيّ."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
            else:
                # `from . import X` — الوحدةُ `None` والاسمُ المستورَد هو الوحدة.
                names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if target:
                names.append(target)
    return names


def _dynamic_import_target(node: ast.Call) -> str | None:
    """`importlib.import_module("x")` و`import_module("x")` و`__import__("x")` بوسيطٍ حرفيّ.

    الوسيطُ المحسوب لا يُقرأ بالتحليل الساكن؛ الحرفيُّ وحده مُغطّى، وهذا حدُّ العقد.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:
        return None
    if name not in {"import_module", "__import__"}:
        return None
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _copy_sources(dockerfile: Path) -> list[str]:
    """مُعامِلاتُ المصدر في كلّ سطر `COPY`: بلا الرايات وبلا الوِجهة (آخِرُ مُعامِل).

    مُغطًّى: `COPY a b /dst/` · `COPY --chown=u:g a /dst/` · صيغةُ مصفوفة JSON.
    مُستثنًى بقصد: `COPY --from=<stage>` — مصدرُه مسارٌ في مرحلةِ بناءٍ أخرى لا في
    المستودع، ومراحلُ البناء نفسُها تُقرأ بأسطر `COPY` الخاصّة بها في هذا الملفّ نفسِه.
    """
    sources: list[str] = []
    for raw in _logical_lines(dockerfile.read_text(encoding="utf-8")):
        line = raw.strip()
        if not re.match(r"(?i)^copy\s", line):
            continue
        rest = line[len("COPY") :].strip()
        flags = re.findall(r"(?i)^(?:--\S+\s+)*", rest)
        consumed = flags[0] if flags else ""
        if re.search(r"(?i)--from=", consumed):
            continue
        rest = rest[len(consumed) :].strip()
        if rest.startswith("["):
            try:
                operands = [str(x) for x in json.loads(rest)]
            except (ValueError, TypeError):
                operands = []
        else:
            operands = rest.split()
        if len(operands) >= 2:
            sources.extend(operands[:-1])
    return sources


def _logical_lines(text: str) -> list[str]:
    """يطوي استمرارَ السطر بـ`\\` كي لا تفلت مصادرُ موزّعةٌ على أسطر."""
    lines: list[str] = []
    buffer = ""
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        lines.append(buffer + stripped)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def _ships(source: str, target: str) -> bool:
    """هل يُدخِل مصدرُ `COPY` هذا المسارَ `target` (نسبيّاً للجذر) إلى الصورة؟"""
    normalized = source.strip().rstrip("/")
    if normalized in {"", ".", "./"}:
        return True
    src = PurePosixPath(normalized.removeprefix("./"))
    dst = PurePosixPath(target)
    return src == dst or src in dst.parents


def _production_consumers() -> list[Path]:
    consumers: list[Path] = []
    for base in (ROOT / "services", SHARED, ROOT / "bots", ROOT / "agents"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if _is_test_path(path) or path.name == f"{PIPELINE_MODULE}.py":
                continue
            if any(PIPELINE_MODULE in name for name in _imports_of(path)):
                consumers.append(path.relative_to(ROOT))
    return sorted(consumers)


def _gap_status(gap_id: str) -> str:
    text = REGISTRY.read_text(encoding="utf-8")
    start = text.index(f"## {gap_id}")
    section = text[start : text.find("\n## ", start + 1)]
    match = re.search(r"\*\*الحالة:\*\*\s*([a-z]+)", section)
    assert match, f"{gap_id}: لا سطرَ حالة في قسمه"
    return match.group(1)


def test_zero_consumers_is_bound_to_the_registry_status_in_both_directions() -> None:
    consumers = _production_consumers()
    status = _gap_status("AI-RUNTIME-WIRING-01")
    if consumers:
        assert status != "open", (
            f"ظهر مستهلكٌ إنتاجيّ للخطّ ({consumers}) والقسمُ ما يزال `open` — "
            "اقلب الحالة بقياسه (شاهدُ توصيل + شهادةٌ حيّة) في الالتزام نفسه"
        )
    else:
        assert status == "open", (
            "القسمُ يقول إنّ الفجوة أُغلقت ولا مستهلكَ إنتاجيّ للخطّ — إغلاقٌ بلا مسار"
        )


def test_the_platform_image_does_not_ship_ai_agronomist() -> None:
    """يُقرأ من كلّ مُعامِلات `COPY` — فمصدرٌ واسعٌ (`.` أو `services/`) يشحنها أيضاً."""
    offenders = [
        src
        for src in _copy_sources(PLATFORM_DOCKERFILE)
        if _ships(src, FORBIDDEN_IN_PLATFORM_IMAGE)
    ]
    assert not offenders, (
        f"صورةُ المنصّة صارت تشحن {FORBIDDEN_IN_PLATFORM_IMAGE} عبر {offenders} — "
        "حدِّث هذا الحارس والقسمَ AI-RUNTIME-WIRING-01 معاً"
    )


def test_no_code_inside_the_platform_image_imports_ai_agronomist() -> None:
    """المسحُ يشمل `shared/` لأنّ الصورةَ تنسخها (`Dockerfile:33`) كما تنسخ شجرةَ المنصّة."""
    offenders = []
    for base in (PLATFORM, SHARED):
        for path in base.rglob("*.py"):
            if _is_test_path(path):
                continue
            if any(
                name == "ai_agronomist"
                or name.startswith("ai_agronomist.")
                or name.startswith("services.ai_agronomist")
                for name in _imports_of(path)
            ):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"شيفرةٌ داخل صورة المنصّة تستورد ai_agronomist عبر حدّ الحاوية: {sorted(offenders)} — "
        "تعمل في الاختبار وتنكسر في الصورة (AI-RUNTIME-WIRING-01: انقل إلى shared/ أوّلاً)"
    )


def test_the_measured_zero_is_still_zero_while_the_gap_is_open() -> None:
    """يوثّق الرقمَ الذي بُني عليه القسم — ومشروطٌ بالحالة كي لا يحجب شريحةَ التوصيل نفسَها."""
    if _gap_status("AI-RUNTIME-WIRING-01") != "open":
        pytest.skip("الفجوة لم تعد `open` — الاتّجاهان أعلاه يحرسان العدد بعد قلبِ الحالة")
    assert _production_consumers() == [], _production_consumers()


# ── شواهدُ القارئَين أنفسِهما (ملاحظاتُ مراجعة #1018) ────────────────────────────


def test_the_import_reader_sees_a_module_less_relative_import(tmp_path: Path) -> None:
    module = tmp_path / "consumer.py"
    module.write_text(f"from . import {PIPELINE_MODULE}\n", encoding="utf-8")
    assert PIPELINE_MODULE in _imports_of(module)


def test_the_import_reader_sees_a_literal_dynamic_import(tmp_path: Path) -> None:
    module = tmp_path / "consumer.py"
    module.write_text(
        "import importlib\n"
        f'mod = importlib.import_module("services.ai_agronomist.{PIPELINE_MODULE}")\n',
        encoding="utf-8",
    )
    assert f"services.ai_agronomist.{PIPELINE_MODULE}" in _imports_of(module)


def test_the_copy_reader_sees_a_flagged_and_a_multi_source_line(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "COPY --chown=app:app services/ai_agronomist /app/svc\n"
        "COPY shared/ services/sahool-platform/ /app/\n"
        "COPY --from=builder /app /app\n",
        encoding="utf-8",
    )
    sources = _copy_sources(dockerfile)
    assert "services/ai_agronomist" in sources, sources
    assert "shared/" in sources and "services/sahool-platform/" in sources, sources
    assert "/app" not in sources, "مصدرُ `--from` مرحلةُ بناءٍ لا شجرةُ المستودع"


@pytest.mark.parametrize("source", [".", "./", "services", "services/", "services/ai_agronomist"])
def test_a_broad_copy_source_counts_as_shipping_the_service(source: str) -> None:
    assert _ships(source, FORBIDDEN_IN_PLATFORM_IMAGE), source


@pytest.mark.parametrize("source", ["shared", "shared/", "services/sahool-platform/"])
def test_an_unrelated_copy_source_does_not_count_as_shipping_the_service(source: str) -> None:
    assert not _ships(source, FORBIDDEN_IN_PLATFORM_IMAGE), source
