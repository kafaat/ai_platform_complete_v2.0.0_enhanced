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

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
FLAGS = "shared.ai.recommendation_runtime.flags"
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


def test_no_production_consumer_reads_the_root_config_or_falls_back_silently():
    for path in CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        assert "config.guardrail_feature_flags" not in imported, (
            f"{path.name}: عاد إلى `config/` الذي لا تنسخه أيُّ صورة"
        )
        # الاستيرادُ النسبيّ داخل الحزمة (`from .flags import …`) يُقرأ `flags` بلا بادئة.
        assert any(m == FLAGS or m.endswith(".flags") or m == "flags" for m in imported), (
            f"{path.name}: لا يستورد الرايات من الموضع الذي يصل إلى الحاوية"
        )
        guarded = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Try)
            and any(
                isinstance(stmt, ast.ImportFrom) and stmt.module and stmt.module.endswith("flags")
                for stmt in node.body
            )
        ]
        assert not guarded, f"{path.name}: استيرادُ الرايات داخل try/except يُعيد البديلَ الصامت"


def test_every_image_that_consumes_the_flags_copies_shared():
    for dockerfile in IMAGES:
        copies = [
            line.split()[1]
            for line in dockerfile.read_text(encoding="utf-8").splitlines()
            if line.strip().upper().startswith("COPY ") and len(line.split()) >= 3
        ]
        assert any(src.rstrip("/") == "shared" for src in copies), (
            f"{dockerfile}: الصورةُ لا تنسخ `shared/` فالرايات لا تصلها"
        )
        assert not any(src.rstrip("/") == "config" for src in copies), (
            f"{dockerfile}: عادت تنسخ `config/` — حدِّث القسمَ GUARDRAIL-FLAGS-FILE-NOT-IN-ANY-IMAGE-01"
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
