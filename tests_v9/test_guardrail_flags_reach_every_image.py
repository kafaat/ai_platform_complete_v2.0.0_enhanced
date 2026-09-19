"""`GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01` — رايات الحواجز تُقرأ من البيئة وتصل إلى كلّ صورة.

**المقيس:** كانت الرايات في `config/guardrail_feature_flags.py` بجذر المستودع، ولا تنسخ
أيُّ صورةٍ `config/`، ومستهلكاها يستوردانها داخل `try/except` بافتراضات — فكانت في كلّ
حاوية افتراضاتٍ لا تُقلَب، بينما تقرؤها الوثائق مرحلةَ تفعيل. الآن: تعريفٌ واحد في
`shared/ai/recommendation_runtime/flags.py` (تنسخه الصورتان) يقرأ `SAHOOL_<FLAG>`.

يحرس هذا الملفّ: (١) القراءةَ من البيئة بدلالاتٍ صريحة، (٢) ألّا يعود مستهلكٌ إنتاجيّ
إلى `config/` أو إلى بديلٍ صامت، (٣) أنّ كلَّ صورةٍ تستهلك الرايات تنسخ `shared/`.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from tests_v9.static_reading import copy_sources, guarded_import_names, imported_names, ships

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FLAGS = "shared.ai.recommendation_runtime.flags"
ROOT_CONFIG = "config.guardrail_feature_flags"
CONSUMERS = (
    ROOT / "services/sahool-platform/core/internal_orchestrator.py",
    ROOT / "shared/ai/recommendation_runtime/runtime_guardrail_adapter.py",
)
IMAGES = (
    ROOT / "services/sahool-platform/Dockerfile",
    ROOT / "services/ai_agronomist/Dockerfile",
)


def _reload_flags(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(f"SAHOOL_{key}", raising=False)
        else:
            monkeypatch.setenv(f"SAHOOL_{key}", value)
    return importlib.reload(importlib.import_module(FLAGS))


def test_defaults_are_the_documented_safe_defaults(monkeypatch):
    flags = _reload_flags(
        monkeypatch,
        ENABLE_PONYTAIL_GUARDRAILS=None,
        ENABLE_LEGACY_RECOMMENDATION_FALLBACK=None,
        REQUIRE_CANONICAL_FIELD_STATE=None,
        REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES=None,
    )
    assert flags.ENABLE_PONYTAIL_GUARDRAILS is False
    assert flags.ENABLE_LEGACY_RECOMMENDATION_FALLBACK is True
    assert flags.REQUIRE_CANONICAL_FIELD_STATE is True
    assert flags.REQUIRE_HUMAN_REVIEW_FOR_PESTICIDES is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("true", True), ("YES", True), ("0", False), ("off", False), ("maybe", False)],
)
def test_a_flag_is_read_from_the_environment_and_garbage_is_the_default(monkeypatch, raw, expected):
    """قيمةٌ غيرُ مفهومة تُعدّ الافتراضَ لا تفعيلاً — فالتفعيلُ لا يقع بخطأ إملائيّ."""
    flags = _reload_flags(monkeypatch, ENABLE_PONYTAIL_GUARDRAILS=raw)
    assert flags.ENABLE_PONYTAIL_GUARDRAILS is expected
    _reload_flags(monkeypatch, ENABLE_PONYTAIL_GUARDRAILS=None)


def _reads_the_root_config(name: str) -> bool:
    return name == ROOT_CONFIG or name.startswith(f"{ROOT_CONFIG}.")


def _reads_the_shared_flags(name: str) -> bool:
    # الاستيرادُ النسبيّ داخل الحزمة (`from .flags import …`) يُقرأ `flags` بلا بادئة.
    return name == FLAGS or name.endswith(".flags") or name == "flags"


def test_no_production_consumer_reads_the_root_config_or_falls_back_silently():
    """القراءةُ تشمل `import x` كما تشمل `from x import y` — وإلّا تُجوَّز بصيغةٍ أخرى.

    مراجعةُ #1019: الصياغةُ الأولى قرأت `ast.ImportFrom` ذاتَ الوحدة فقط، فكان
    `import config.guardrail_feature_flags` يمرّ، وكذلك `import …flags` داخل `try`.
    """
    for path in CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = imported_names(tree)
        assert not any(_reads_the_root_config(m) for m in imported), (
            f"{path.name}: عاد إلى `config/` الذي لا تنسخه أيُّ صورة"
        )
        assert any(_reads_the_shared_flags(m) for m in imported), (
            f"{path.name}: لا يستورد الرايات من الموضع الذي يصل إلى الحاوية"
        )
        guarded = [m for m in guarded_import_names(tree) if _reads_the_shared_flags(m)]
        assert not guarded, (
            f"{path.name}: استيرادُ الرايات داخل try/except يُعيد البديلَ الصامت ({guarded})"
        )


def test_every_image_that_consumes_the_flags_copies_shared():
    """يُقرأ من كلّ مُعامِلات `COPY` بالقارئ المشترك، فلا تُفلِته رايةٌ ولا مصدرٌ ثانٍ."""
    for dockerfile in IMAGES:
        sources = copy_sources(dockerfile)
        assert any(ships(src, "shared") for src in sources), (
            f"{dockerfile}: الصورةُ لا تنسخ `shared/` فالرايات لا تصلها"
        )
        offenders = [src for src in sources if ships(src, "config")]
        assert not offenders, (
            f"{dockerfile}: عادت تشحن `config/` عبر {offenders} — "
            "حدِّث القسمَ GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"
        )


def test_the_import_reader_sees_the_forms_that_would_otherwise_slip_past(tmp_path: Path):
    """شاهدُ القارئ نفسِه: الصيغتان اللتان كانتا تمرّان، ومعهما الاستيرادُ المحروس."""
    plain = tmp_path / "plain.py"
    plain.write_text(f"import {ROOT_CONFIG}\n", encoding="utf-8")
    plain_tree = ast.parse(plain.read_text(encoding="utf-8"))
    assert any(_reads_the_root_config(m) for m in imported_names(plain_tree))

    guarded = tmp_path / "guarded.py"
    guarded.write_text(f"try:\n    import {FLAGS}\nexcept Exception:\n    pass\n", encoding="utf-8")
    tree = ast.parse(guarded.read_text(encoding="utf-8"))
    assert any(_reads_the_shared_flags(m) for m in guarded_import_names(tree)), (
        "`import …flags` داخل `try` يجب أن يُقرأ محروساً — وإلّا مرّ البديلُ الصامت"
    )


def test_the_root_config_module_defines_nothing_and_only_re_exports():
    tree = ast.parse((ROOT / "config/guardrail_feature_flags.py").read_text(encoding="utf-8"))
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and not (len(node.targets) == 1 and getattr(node.targets[0], "id", "") == "__all__")
    ]
    assert not assignments, "عاد `config/` يعرّف رايةً — تعريفٌ ثانٍ ينحرف عن الذي تقرؤه الحاوية"


def test_the_pipeline_cannot_run_with_the_guardrail_adapter_missing():
    """لا بديلَ صامتاً للمُهيّئ المحروس: غيابُه عطلٌ يُرى لا مسارٌ يعمل بلا سلطة قرار.

    **المقيس (مراجعة #1019):** كان الاستيرادُ داخل `try/except Exception` ببديلٍ `None`،
    والمسارُ البديل يفحص `canonical_field_state` وحده ويُمرّر السياقَ كما هو — فلا
    `assert_no_decision_keys` على مخرجات الأدوات ولا تجريدَ لـRAG/KG من مدخلات القرار.
    أي أنّ انكسارَ استيرادٍ واحد كان يُسقِط سلطةَ القرار ويُبقي الخطَّ يعمل، وهو أخطرُ
    من إخفاء عطل الاستيراد الذي رُصِد. الحارسُ يمنع عودةَ الصيغتين معاً.
    """
    pipeline = ROOT / "shared/ai/recommendation_runtime/recommendation_runtime_pipeline.py"
    tree = ast.parse(pipeline.read_text(encoding="utf-8"))

    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any(
            isinstance(stmt, ast.ImportFrom)
            and stmt.module
            and stmt.module.endswith("runtime_guardrail_adapter")
            for stmt in node.body
        )
    ]
    assert not guarded, "عاد استيرادُ المُهيّئ داخل `try/except` — بديلٌ صامتٌ يتجاوز الحاجز"

    rebound = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "guarded_runtime_context" for t in node.targets)
    ]
    assert not rebound, "أُسنِدت قيمةٌ إلى `guarded_runtime_context` — بديلٌ يتخطّى سلطةَ القرار"

    module = importlib.import_module(
        "shared.ai.recommendation_runtime.recommendation_runtime_pipeline"
    )
    assert module.guarded_runtime_context is not None
