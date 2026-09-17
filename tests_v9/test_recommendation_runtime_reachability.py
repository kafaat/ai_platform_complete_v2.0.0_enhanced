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

import re
from pathlib import Path

import pytest

from tests_v9.static_reading import copy_sources, imports_of, is_test_path, ships

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


def _production_consumers() -> list[Path]:
    consumers: list[Path] = []
    for base in (ROOT / "services", SHARED, ROOT / "bots", ROOT / "agents"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if is_test_path(path) or path.name == f"{PIPELINE_MODULE}.py":
                continue
            if any(PIPELINE_MODULE in name for name in imports_of(path)):
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
        src for src in copy_sources(PLATFORM_DOCKERFILE) if ships(src, FORBIDDEN_IN_PLATFORM_IMAGE)
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
            if is_test_path(path):
                continue
            if any(
                name == "ai_agronomist"
                or name.startswith("ai_agronomist.")
                or name.startswith("services.ai_agronomist")
                for name in imports_of(path)
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
    assert PIPELINE_MODULE in imports_of(module)


def test_the_import_reader_sees_a_literal_dynamic_import(tmp_path: Path) -> None:
    module = tmp_path / "consumer.py"
    module.write_text(
        "import importlib\n"
        f'mod = importlib.import_module("services.ai_agronomist.{PIPELINE_MODULE}")\n',
        encoding="utf-8",
    )
    assert f"services.ai_agronomist.{PIPELINE_MODULE}" in imports_of(module)


def test_the_copy_reader_sees_a_flagged_and_a_multi_source_line(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        "COPY --chown=app:app services/ai_agronomist /app/svc\n"
        "COPY shared/ services/sahool-platform/ /app/\n"
        "COPY --from=builder /app /app\n",
        encoding="utf-8",
    )
    sources = copy_sources(dockerfile)
    assert "services/ai_agronomist" in sources, sources
    assert "shared/" in sources and "services/sahool-platform/" in sources, sources
    assert "/app" not in sources, "مصدرُ `--from` مرحلةُ بناءٍ لا شجرةُ المستودع"
    # الوثيقةُ تقول «بلا الرايات»، فتُقاس: رمزُ رايةٍ في القائمة دعوًى غيرُ مُثبَتة.
    # (لا يقلب حكماً اليوم لأنّ الرمزَ لا يطابق مساراً، لكنّ عقدَ القارئ يُثبَّت لا يُفترَض.)
    assert not [src for src in sources if src.startswith("--")], sources


@pytest.mark.parametrize("source", [".", "./", "services", "services/", "services/ai_agronomist"])
def test_a_broad_copy_source_counts_as_shipping_the_service(source: str) -> None:
    assert ships(source, FORBIDDEN_IN_PLATFORM_IMAGE), source


@pytest.mark.parametrize("source", ["shared", "shared/", "services/sahool-platform/"])
def test_an_unrelated_copy_source_does_not_count_as_shipping_the_service(source: str) -> None:
    assert not ships(source, FORBIDDEN_IN_PLATFORM_IMAGE), source
