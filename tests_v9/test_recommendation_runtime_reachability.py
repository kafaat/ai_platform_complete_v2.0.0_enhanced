"""`AI-RUNTIME-WIRING-01` — خطُّ التوصية المحروس بلا مستهلك، والحدُّ الذي يمنع توصيلَه خطأً.

**المقيس، لا المفترَض:** `RecommendationRuntimePipeline` (`services/ai_agronomist/`) له
صفرُ مراجع غير اختباريّة، ومستهلكُه الوحيد اختبارٌ بمحرّكٍ وهميّ. والمدخلُ الإنتاجيّ
الوحيد الذي يُنتج توصيةً ويُثبِتها يعيش في المنصّة، وصورةُ المنصّة **لا تنسخ**
`services/ai_agronomist` (`Dockerfile:33-34`) — فاستيرادُه من شيفرة المنصّة يعمل في
الاختبارات (الجذرُ على المسار) وينكسر في الحاوية. هذا الملفّ يحرس حقيقتين:

١) صفرُ المستهلكين مقيَّدٌ بحالة القسم في السجلّ: مستهلكٌ يظهر بلا قلبِ الحالة ⇒ أحمر،
   وقلبُ الحالة بلا مستهلك ⇒ أحمر. لا يُقاس «الإغلاق» من وجود الملفّ.
٢) لا شيفرةَ منصّةٍ تستورد `ai_agronomist` عبر حدّ الحاوية — الحدُّ يُقرأ من `COPY`
   في الصورة لا من افتراض.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_MODULE = "recommendation_runtime_pipeline"
REGISTRY = ROOT / "sahool-brain/gaps/registry.md"
PLATFORM = ROOT / "services/sahool-platform"
PLATFORM_DOCKERFILE = PLATFORM / "Dockerfile"


def _is_test_path(path: Path) -> bool:
    parts = path.parts
    return any(p in {"tests", "tests_v9"} for p in parts) or path.name.startswith("test_")


def _imports_of(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _production_consumers() -> list[Path]:
    consumers: list[Path] = []
    for base in (ROOT / "services", ROOT / "shared", ROOT / "bots", ROOT / "agents"):
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


def test_platform_code_does_not_import_ai_agronomist_across_the_image_boundary() -> None:
    """صورةُ المنصّة تنسخ `shared/` وشجرتَها فقط — فاستيرادُ `ai_agronomist` منها ينكسر في الحاوية."""
    copies = [
        line.split()[1]
        for line in PLATFORM_DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip().upper().startswith("COPY ") and len(line.split()) >= 3
    ]
    assert not any(src.startswith("services/ai_agronomist") for src in copies), (
        "الصورةُ صارت تنسخ ai_agronomist — حدِّث هذا الحارس والقسمَ AI-RUNTIME-WIRING-01 معاً"
    )
    offenders = []
    for path in PLATFORM.rglob("*.py"):
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
        f"شيفرةُ منصّةٍ تستورد ai_agronomist عبر حدّ الحاوية: {offenders} — "
        "تعمل في الاختبار وتنكسر في الصورة (AI-RUNTIME-WIRING-01: انقل إلى shared/ أوّلاً)"
    )


def test_the_measured_zero_is_still_zero_today() -> None:
    """يوثّق الرقمَ الذي بُني عليه القسم؛ حين يتغيّر يتغيّر القسمُ معه لا هذا الاختبار وحده."""
    assert _production_consumers() == [], _production_consumers()
