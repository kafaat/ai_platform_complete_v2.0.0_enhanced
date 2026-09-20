"""`AI-RUNTIME-WIRING-01` ② — شاهدُ التوصيل: الخطُّ المحروس له موضعُ استدعاءٍ إنتاجيّ.

يقيس **الوصلَ** لا السلوكَ الزراعيّ: أنّ موضعَ الاستدعاء موجود، وأنّه يستورد الخطَّ من
`shared/` (الشجرةُ الوحيدةُ التي تنسخها صورةُ المنصّة)، وأنّ الرايةَ مطفأةٌ افتراضاً
فلا يتغيّر سلوكٌ منشورٌ بمجرّد وصول الشيفرة.

**ولا يُعيد تنفيذَ قواعد المراجعة** — تلك تعيش في الخطّ نفسِه ولها شواهدُها؛ إعادتُها هنا
تصنع مصدرَ حقيقةٍ ثانياً ينحرف. والشهادةُ الحيّة **ليست هنا**: مخرجُها المحفوظ في
`docs/evidence/ai_runtime_wiring_live_certification.json` يُقرأ أدناه بوصفه مصنوعةً
مؤرّخة، لأنّ جناحَ الوحدة لا يملك قاعدةً — وادّعاءُ قياسها هنا كان سيكون أخضرَ عن
سؤالٍ لم يُطرَح.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CALL_SITE = ROOT / "services/sahool-platform/api/routers/recommendations.py"
EVIDENCE = ROOT / "docs/evidence/ai_runtime_wiring_live_certification.json"
HELPER = "_run_guarded_runtime_pipeline"
PIPELINE_IMPORT = "shared.ai.recommendation_runtime.recommendation_runtime_pipeline"


def _tree() -> ast.Module:
    return ast.parse(CALL_SITE.read_text(encoding="utf-8"))


def _helper() -> ast.AsyncFunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == HELPER:
            return node
    raise AssertionError(f"{HELPER} غائبةٌ عن {CALL_SITE.name} — لا موضعَ استدعاءٍ إنتاجيّ")


def test_the_production_call_site_exists_and_is_async() -> None:
    """غيرُ متزامنةٍ بالضرورة: `execute` كذلك، والمايسترو المتزامنُ كان العائقَ (أ)."""
    assert _helper().name == HELPER


def test_the_call_site_imports_the_pipeline_from_shared_not_from_the_service() -> None:
    """حدُّ الحاوية: صورةُ المنصّة تنسخ `shared/` ولا تنسخ `services/ai_agronomist`."""
    modules = {
        node.module
        for node in ast.walk(_tree())
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert PIPELINE_IMPORT in modules, sorted(m for m in modules if "recommendation_runtime" in m)
    assert not [m for m in modules if "ai_agronomist" in m], sorted(modules)


def test_the_call_site_actually_awaits_execute() -> None:
    """استيرادٌ بلا استدعاءٍ توصيلٌ في الاسم فقط — يُقرأ الاستدعاءُ من الشجرة النحويّة."""
    awaited = {
        node.func.attr
        for node in ast.walk(_helper())
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "execute" in awaited, sorted(awaited)


def test_the_flag_is_off_by_default() -> None:
    """وصولُ الشيفرة ليس تفعيلاً: الافتراضُ مطفأٌ فلا يتغيّر سلوكٌ منشور."""
    from shared.ai.recommendation_runtime.flags import flag

    assert flag("ENABLE_RUNTIME_PIPELINE_CONSUMER", False) is False


def test_the_flag_can_be_flipped_from_the_environment(monkeypatch) -> None:
    """قابليّةُ القلب في الحاوية شرطٌ مُعلَنٌ في بند الإغلاق — تُقاس لا تُفترَض."""
    from shared.ai.recommendation_runtime.flags import flag

    monkeypatch.setenv("SAHOOL_ENABLE_RUNTIME_PIPELINE_CONSUMER", "1")
    assert flag("ENABLE_RUNTIME_PIPELINE_CONSUMER", False) is True


def test_the_live_certification_artefact_records_a_real_reach() -> None:
    """المصنوعةُ تقول إنّ `execute` بُلِغت على قاعدةٍ حيّة — لا أنّها تستطيع ذلك."""
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["flag_ENABLE_RUNTIME_PIPELINE_CONSUMER"] is True
    assert evidence["execute_reached"] >= 1, evidence
    assert evidence["execute_calls"][0]["has_canonical_field_state"] is True, evidence
    assert evidence["live_db"]["postgis"].startswith("3."), evidence["live_db"]
    assert evidence["live_db"]["public_tables"] > 300, evidence["live_db"]


def test_the_failure_path_falls_back_instead_of_breaking_the_request() -> None:
    """الخطُّ الساقطُ يهبط إلى الموروث — والهبوطُ مُعلَنٌ بتحذير، غيرُ مبتلَع."""
    source = ast.get_source_segment(CALL_SITE.read_text(encoding="utf-8"), _helper()) or ""
    assert "logger.warning" in source, "هبوطٌ صامتٌ يجعل رايةً مقلوبةً تبدو عاملةً وهي ساقطة"
    assert "return None" in source
