"""`RAG-ANSWERS-AN-OPERATIONAL-FACT-01` — الاسترجاع لا يجيب عن حالة الحقل الآن.

**ولماذا هذا البند أخطر من غيره:** مُخرَجُ الاسترجاع **نصٌّ معقول دائماً**. فإن
أجاب عن حدٍّ آمنٍ للرية أنتج رقماً يبدو صحيحاً ولم يمرّ بالميل ولا التسرّب ولا
شهادة الحزمة. وهو صنف «رقمٌ معقول من مصدرٍ غير قانونيّ» نفسه — لكن من بابٍ لا
يراه حارسُ الالتفاف: لا حقلَ يُقرأ ولا اشتقاقَ من خام، بل نصٌّ يُولَّد.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "rag_operational_boundary_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("rag_operational_boundary_guard", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

_KEYS = {"irrigation.maximum_safe_depth_mm_event"}
_FIELDS = {"maximum_safe_depth_mm_event"}


def _write(tmp_path: Path, name: str, body: str) -> Path:
    pkg = tmp_path / "services"
    pkg.mkdir(exist_ok=True)
    (pkg / name).write_text(body, encoding="utf-8")
    return pkg / name


def _run(tmp_path: Path, files: list[Path], modules: set[str] | None = None):
    return guard.violations(_KEYS, _FIELDS, modules or set(), files, tmp_path)


_RAG_CLEAN = '''
import os

RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://sahool-rag-retrieval:8000")


def ask(question):
    """يسأل عن مستنداتٍ غير مُهيكَلة — توصيات FAO ونحوها."""
    return {"question": question, "topic": "fao_guidance"}
'''


def test_a_rag_module_that_stays_in_its_lane_passes(tmp_path):
    f = _write(tmp_path, "advisor.py", _RAG_CLEAN)
    problems, rag_files = _run(tmp_path, [f])
    assert problems == []
    assert rag_files == 1


def test_a_rag_module_naming_an_operational_key_is_blocked(tmp_path):
    """الصنف المقصود: «اسأل الاسترجاع عن الحدّ الآمن»."""
    body = _RAG_CLEAN + '\n\ndef bad(c):\n    return c["irrigation.maximum_safe_depth_mm_event"]\n'
    f = _write(tmp_path, "advisor.py", body)
    problems, _ = _run(tmp_path, [f])
    assert problems and "حقيقةً تشغيليّة" in problems[0]


def test_a_producer_field_name_counts_too(tmp_path):
    """المفتاح المنطقيّ ليس المدخل الوحيد: اسمُ الحقل الفعليّ بابٌ ثانٍ."""
    body = _RAG_CLEAN + '\n\ndef bad(c):\n    return c.get("maximum_safe_depth_mm_event")\n'
    f = _write(tmp_path, "advisor.py", body)
    problems, _ = _run(tmp_path, [f])
    assert problems


def test_a_canonical_producer_that_reaches_rag_is_blocked(tmp_path):
    """مصدرُ الحقيقة لا يستمدّ حقيقتَه من نصٍّ مُولَّد."""
    f = _write(tmp_path, "prod.py", _RAG_CLEAN)
    problems, _ = _run(tmp_path, [f], modules={"services/prod.py"})
    assert any("مُنتِجٌ قانونيّ يبلغ الاسترجاع" in p for p in problems)


def test_a_non_rag_module_may_name_operational_facts_freely(tmp_path):
    """الحدُّ على الاسترجاع وحده؛ وتوسيعُه يُجرّم كلّ مستهلِكٍ قانونيّ."""
    body = 'def ok(c):\n    return c["irrigation.maximum_safe_depth_mm_event"]\n'
    f = _write(tmp_path, "consumer.py", body)
    problems, rag_files = _run(tmp_path, [f])
    assert problems == [] and rag_files == 0


def test_a_mention_inside_a_docstring_is_not_a_use(tmp_path):
    """شرحٌ يقول «هذا لا يُسأل عنه الاسترجاع» يجب ألّا يُحمِر الحارس.

    وإلّا دُرِّب كاتبُه على حذف التوثيق — رقمٌ أخضر وتوثيقٌ أقلّ.
    """
    body = _RAG_CLEAN.replace(
        '"""يسأل عن مستنداتٍ غير مُهيكَلة — توصيات FAO ونحوها."""',
        '"""لا يُسأل هنا عن irrigation.maximum_safe_depth_mm_event إطلاقاً."""',
    )
    f = _write(tmp_path, "advisor.py", body)
    problems, _ = _run(tmp_path, [f])
    assert problems == [], f"نصُّ توثيقٍ عُومِل استعمالاً: {problems}"


def test_zero_rag_modules_fails_closed(tmp_path):
    """صفرُ وحدةٍ تبلغ الاسترجاع يعني أنّ الحدّ لم يُقَس — أو أنّ العلامات بائتة."""
    registry = tmp_path / "reg.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "sahool.knowledge_source_registry",
                "keys": [{"key": "k", "producer_field": "f", "producer_module": "m.py"}],
            }
        ),
        encoding="utf-8",
    )
    _write(tmp_path, "plain.py", "def f():\n    return 1\n")
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(registry), "--root", str(tmp_path)])


def test_a_missing_registry_fails_closed(tmp_path):
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(tmp_path / "nope.json"), "--root", str(tmp_path)])


def test_a_wrong_schema_fails_closed(tmp_path):
    """الشجرة هنا سليمةٌ تماماً عدا مخطَّط السجلّ — عمداً.

    أوّل صياغةٍ تركت الشجرة فارغة، فوقع الحجب بفرع «صفر وحدة استرجاع» لا بفرع
    المخطَّط، وبقيت الخاصّيّة بلا حارس. كشفَت الطفرةُ ذلك وهي خضراء — وهو ثالث
    ظهورٍ للصنف نفسه في هذه الجلسة.
    """
    _write(tmp_path, "advisor.py", _RAG_CLEAN)
    other = tmp_path / "other.json"
    other.write_text(
        json.dumps(
            {
                "schema": "else",
                "keys": [
                    {
                        # أسماءٌ واقعيّة الطول عمداً: المطابقة بالاحتواء تجعل
                        # مفتاحاً بحرفٍ واحد يُطابِق كلّ سلسلةٍ في الشجرة، فيقع
                        # الحجب لسببٍ ثالثٍ غير المقصود — وقد وقع.
                        "key": "zzz.unrelated_operational_fact",
                        "producer_field": "zzz_unrelated_producer_field",
                        "producer_module": "zzz/unrelated_producer.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        guard.main(["--registry", str(other), "--root", str(tmp_path)])


def test_the_live_tree_passes_the_guard():
    assert guard.main([]) == 0


def test_the_live_tree_actually_contains_rag_modules():
    """المسار الثاني: لولا وحدةٍ حقيقيّة واحدة لكان الحدّ بلا قياس."""
    keys, fields, modules = guard.load_registry(guard.REGISTRY)
    files = guard.scan_files(guard.ROOT, guard.SCAN_DIRS)
    problems, rag_files = guard.violations(keys, fields, modules, files, guard.ROOT)
    assert problems == []
    assert rag_files >= 1, "لا وحدةَ استرجاعٍ في الشجرة — الحدّ لا يُقاس"
