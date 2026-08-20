"""UNIT-TEST-DORMANCY-01 بآليّةٍ ثالثة: طبقةُ التبعيّات.

الصنف عاد مرّتين قبل هذه، وبآليّتين مختلفتين، ولذلك يستحقّ قياساً لا فقرة:

  ① **العلامة** — اختبارٌ بلا `unit` يُستبعَد من البوّابة (`TESTS-UNMARKED-DESELECTED-01`).
  ② **مسار الجمع** — ملفٌّ خارج `testpaths` لا يُجمَع أصلاً (`RASTER-SERVICE-TESTS-UNWIRED-TO-CI-01`).
  ③ **وهذه:** ملفٌّ مُعلَّم ومجموعٌ، لكنّ `pytest.importorskip("X")` في رأسه يُخرِجه
     من التنفيذ لأنّ `X` غير مثبَّتة في طبقة الوظيفة التي تجمعه.

والثالثة أخبثُ من أختيها لأنّ مُخرَجها **`skipped` لا `deselected`**: سطرٌ واحد في
ذيل التقرير بين آلاف النقاط الخضراء، لا رقمٌ ناقص يلفت النظر.

المقيس الذي وَلَّد هذا الملفّ: `test_prescription_shapefile.py` مُعلَّم `unit` ويصف
نفسه «نقيّاً بلا خدمات/شبكة»، ويستدعي `importorskip("shapefile")`. و`pyshp` مُعلَنة
في `api/requirements.txt` — تُثبّتها *Platform Unit Tests* وحدها، وهي تُشغّل
`services/sahool-platform/tests` لا `tests_v9/`. فالوظيفة المالكة للحزمة لا تجمع
الملفّ، والجامعة له لا تملكها: **سبعةُ اختباراتٍ على مُصدِّر وصفة VRA لم تُنفَّذ قطّ**.

و`importorskip` ليست عطلاً بذاتها — بل عُرفٌ مقصود وموثَّق هنا: ٩٣ ملفّاً تستعمله
لـ`fastapi` وحدها، لأنّ طبقة الوحدة دنيا عمداً. فالمقيس ليس «هل يوجد تخطٍّ؟» بل
**«هل هذا التخطّي مُعلَنٌ ومُبرَّر، أم وقع صدفةً ولم يعلم به أحد؟»**

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "tests_v9"

# ── الجرد المُعلَن: خامدٌ **بقرارٍ مكتوب**، لا بصدفة ─────────────────────────
#
# كلّ مدخل هنا يعني: «هذه الوحدة غائبة عن طبقة الوحدة عن عمد، وهذه كلفتها».
# وهو **إعلانُ دَينٍ لا إعفاء**: القائمة تُقاس (المدخل البائت يُحمِرّ)، وأيّ تخطٍّ
# جديد غير مُعلَن يحجب — فلا يدخل خمولٌ رابع بصمت كما دخل الثالث.
#
# ولم تُوسَّع القائمة تخميناً: كلٌّ قِيس بأنّه غائب عن **كلّ** وظيفةٍ تجمع
# `tests_v9/` (`unit-tests` و`integration-tests` و`live-pg`، وثلاثتها تُثبّت
# `tests_v9/requirements-test.txt` وحدها).
DECLARED_DORMANT: dict[str, str] = {
    "sklearn": "scikit-learn ~٣٠ ميغابايت لحالةٍ واحدة (`zones_kmeans`) — مُعلَنة في requirements_real",
    "pyarrow": "عجلةٌ ثقيلة لحالة parquet واحدة في `test_farm_memory`",
    "aiomqtt": "عميلُ وسيطٍ يستورده مدخل actuator/video عند التحميل — مُعلَن في requirements الخدمتين",
    "edge_tts": "غير مُعلَنة في أيّ ملفّ متطلّبات في الشجرة — تبعيّةٌ اختياريّة لمزوّد TTS واحد",
    "api.irrigation_models": "وحدةٌ داخليّة لا حزمة: التخطّي يقع حين لا تكون شجرة المنصّة على المسار",
}


def _importorskip_targets() -> dict[str, list[str]]:
    """كلّ `pytest.importorskip("X")` **مُنفَّذ** في الجناح، مع ملفّاته.

    الفحص بـ`ast` لا بـ`grep`: أكثر من عشرة تعليقات في هذا الجناح تشرح العُرف بذكر
    اسم الدالّة، وإدانتُها إيجابيّةٌ كاذبة تُدرِّب كاتبها على حذف التوثيق.
    """
    targets: dict[str, list[str]] = {}
    for path in sorted(SUITE.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "importorskip"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                targets.setdefault(node.args[0].value, []).append(path.name)
    return targets


def _importable(module: str) -> bool:
    """قابليّةُ الاستيراد في **البيئة التي يعمل فيها هذا الاختبار**.

    وهذا مقصود: البوّابة تُشغّله داخل وظيفة الوحدة، فيقيس طبقتها هي لا جدولاً
    يصفها. جدولُ التبعيّات المكتوب يبيت؛ `find_spec` لا يبيت. وقياسي الأوّل كان
    نصّيّاً على `requirements-test.txt` فأدان `cryptography` خطأً — وهي تصل
    عبوريّاً مع `python-jose[cryptography]`.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def test_no_unit_test_is_silently_dormant_on_a_missing_dependency():
    """تخطٍّ غير مُعلَن = اختبارٌ لا يعمل ولا أحد يعلم."""
    undeclared = sorted(
        f"{module} ({', '.join(sorted(set(files))[:3])})"
        for module, files in _importorskip_targets().items()
        if not _importable(module) and module not in DECLARED_DORMANT
    )
    assert not undeclared, (
        "`importorskip` على وحدةٍ غائبة وغير مُعلَنة — الاختبار يُقرأ أخضر وهو لم "
        f"يُنفَّذ: {undeclared}. إمّا تُضاف التبعيّة إلى `tests_v9/requirements-test.txt` "
        "(مثبَّتةً على إصدار الإنتاج)، وإمّا تُعلَن في `DECLARED_DORMANT` بكلفةٍ مكتوبة"
    )


def test_no_inventory_entry_contradicts_a_declared_dependency():
    """المدخل يقول «غائبة بقرارِ كلفة»؛ وسطرٌ في ملفّ المتطلّبات يقول العكس.

    عطلٌ مقيس في حارسي أنا: دمجُ #876 أضاف ``rasterio`` و``shapely`` إلى
    ``requirements-test.txt`` — أي أنّ قرار الكلفة انعكس — وبقي مدخلاهما هنا يقولان
    إنّهما خارج الطبقة. و``test_the_dormancy_inventory_has_no_stale_entry`` لم
    يمسكهما لأنّه يسأل «أما زال أحدٌ يتخطّاها؟» لا «أما زالت غائبة؟».

    فبقي في وثيقةٍ حاكمة **وصفٌ كاذب عن العالم**، وهو أسوأ من غياب الوثيقة: يُقرأ
    قراراً قائماً وقد نُقِض. وهذا الفحص هو ما يجعل الجرد يتقلّص عند زوال سببه بدل أن
    يُصان بيد أحد.
    """
    import re

    text = (ROOT / "tests_v9/requirements-test.txt").read_text(encoding="utf-8")
    declared = {
        re.split(r"[<>=\[]", line.split("#")[0].strip())[0].strip().lower()
        for line in text.splitlines()
        if line.split("#")[0].strip()
    }
    distributions = {"sklearn": "scikit-learn", "shapefile": "pyshp"}
    contradictions = sorted(
        module
        for module in DECLARED_DORMANT
        if distributions.get(module, module).split(".")[0].lower() in declared
    )
    assert not contradictions, (
        f"مُعلَنةٌ خامدة ومُعلَنةٌ تبعيّةً معاً: {contradictions}. انعكس قرار الكلفة — "
        "احذف المدخل، فالجرد يتقلّص عند زوال سببه"
    )


def test_the_dormancy_inventory_has_no_stale_entry():
    """مدخلٌ لا يُقابله تخطٍّ في الشجرة إعفاءٌ دائم بلا صاحب — وهو كيف يصير المؤقّت أبديّاً.

    والفحص هنا **مستقلٌّ عن البيئة** عمداً: يسأل «أما زال أحدٌ يتخطّى هذه الوحدة؟»
    لا «أهي غائبة؟». فلو أُضيفت التبعيّة يوماً بقي المدخل صالحاً حتّى يُحذَف
    `importorskip` نفسه — ولا يحمرّ الجناح على مطوّرٍ ثبّتها محلّيّاً.
    """
    targets = _importorskip_targets()
    stale = sorted(module for module in DECLARED_DORMANT if module not in targets)
    assert not stale, f"مدخلٌ في الجرد لا يتخطّاه أيّ ملفّ — يُحذَف لا يُترَك: {stale}"


def test_the_woken_shapefile_suite_actually_runs_here():
    """العطل المؤسِّس: البرهان أنّ الإيقاظ وقع، لا أنّ سطراً أُضيف إلى ملفّ متطلّبات.

    ``pyshp`` عجلةٌ نقيّة-Python بـ٤٦ كيلوبايت بلا تبعيّات، فكلفة إيقاظها صفر —
    ولم يكن السبات قراراً بل سطراً ناقصاً. ولو عاد الملفّ إلى التخطّي (نُزِعت
    التبعيّة، أو انتقل الاختبار إلى وظيفةٍ بلا الحزمة) يحمرّ هذا فوراً بدل أن
    يُبتلَع في سطر ``skipped`` واحد.
    """
    assert _importable("shapefile"), (
        "`pyshp` غائبة عن طبقة الوحدة — عادت اختبارات مُصدِّر وصفة VRA إلى السبات"
    )
    assert "shapefile" not in DECLARED_DORMANT, (
        "لا تُعلَن خامدةً وهي مثبَّتة: الإعلان يُخفي عودةَ العطل بدل أن يكشفها"
    )
