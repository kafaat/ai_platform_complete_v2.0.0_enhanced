"""سجلُّ سلطة العتبات: الربطُ اسميّ لا سطريّ.

`THRESHOLDS-CARRY-NO-SOURCE-AND-NO-CALIBRATION-STATE-01`

**العطل:** أربعُ عتباتٍ تُغيّر سلطةَ القرار أو تُصعّد التدخّل تعمل في المسار
الحرج بلا سلطةٍ مُثبَتة ولا أساسِ معايرة. اثنتان ورثهما المستودعُ مع استيراد
منصّةٍ قائمة (سلسلةُ السلطة تنتهي خارجه)، واثنتان أُقِرَّت آليّتُهما محلّيّاً
ولم يُثبَت حدُّهما العدديّ.

**وما يحرسه هذا الملفّ ليس القيمَ بل انفصالَ السجلّ عن الكود.** فسجلٌّ يوثّق
`0.7` بينما المصدرُ صار `0.75` أسوأُ من لا سجلّ: يقرأه القارئُ فيطمئنّ إلى
رقمٍ لا يعمل. والمِرساةُ **اسمٌ في وحدة** لا سطرٌ في ملفّ — ولولا ذلك لكان
أوّلُ إعادةِ ترتيبٍ يُفشِل الحارسَ فيُعلَّمُ الفريقُ تجاهُلَه.

الشرطان المتقابلان مُختبَران صراحةً أدناه:
  تغييرُ القيمة في المصدر بلا السجلّ ⇒ يحمرّ · تحريكُ السطر ⇒ يبقى أخضر.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs" / "architecture" / "threshold_authority_ledger.json"

# الجردُ المُقِرّ لـA1. مكتوبٌ هنا لا مُشتقٌّ من السجلّ: سجلٌّ يُشتقّ منه جردُه
# لا يستطيع أن يكشف إسقاطَ قيدٍ منه — وهو أوّلُ ما نهى عنه قرارُ A1.
EXPECTED_CONSTANTS = frozenset(
    {
        # A1 — السلطة والقرار
        "_SEVERITY_CRITICAL",
        "_SEVERITY_INTERVENTION",
        "_LOW_SUCCESS",
        "_HIGH_SUCCESS",
        # A2 — محرّك التنبيهات
        "_SALINITY_RISK",
        "_VIGOR_LOW",
        "_HEAT_HIGH",
        "_DEGRADED_PCT",
        "_SEVERE_PCT",
        "_DESERT_PCT",
        "_MIN_COVERAGE",
        # P5-B — المرض الفطريّ (طرفان مقيسان مختلفَين) وصقيع إزهار اللوز
        "_HUMID_THRESHOLD",
        "_MILD_TEMP_LOW",
        "_MILD_TEMP_HIGH",
        "_DISEASE_RH",
        "_DISEASE_T_MIN",
        "_DISEASE_T_MAX",
        "POLLINATION_THRESHOLDS_V1",
        "THERMAL_THRESHOLDS_V1",
        # P5-C — نافذة الرشّ
        "_WIND_MIN_MS",
        "_WIND_MAX_MS",
    }
)

# دلالاتُ الأصناف — مفروضةٌ لا موصوفة. صنفٌ يحمل حالةَ سلطةٍ لا تُطابقه
# يُحوّل السجلَّ إلى مفرداتٍ حرّة.
#
# و`cited_basis` هو ما يفصل الصنفين المحلّيّين: كلاهما `LOCAL_DESIGN_DECISION`
# على الآليّة، والفرقُ في الحدّ العدديّ وحده. فلو بقي الفصلُ وصفاً في المتن
# لأمكن نقلُ قيدٍ بين الصنفين بلا أثرٍ يُقاس — ولذلك يُفرَض في الاتّجاهين:
# المستشهِدُ يلزمه أساسٌ وخطّة، وغيرُ المستشهِد يُمنَع من ادّعائهما.
CLASS_SEMANTICS = {
    "INHERITED_NO_DECISION_RECORD": {
        "authority_status": "NONE",
        "calibration_status": "NOT_APPLICABLE_UNTIL_PROVENANCE_RECOVERED",
        "decision_record_is_null": True,
        "requires_cited_basis": False,
    },
    "LOCALLY_DECIDED_BUT_UNCALIBRATED": {
        "authority_status": "LOCAL_DESIGN_DECISION",
        "calibration_status": "BLOCKED_MISSING_RUNTIME_EVIDENCE",
        "decision_record_is_null": False,
        "requires_cited_basis": False,
    },
    "LOCALLY_DECIDED_WITH_CITED_BASIS": {
        "authority_status": "LOCAL_DESIGN_DECISION",
        "calibration_status": "DECLARED_PLAN_NOT_EXECUTED",
        "decision_record_is_null": False,
        "requires_cited_basis": True,
    },
}


@pytest.fixture(scope="module")
def ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(ledger: dict) -> list[dict]:
    return ledger["entries"]


def _import_module(entry: dict):
    """يستورد وحدةَ القيد بجذر الاستيراد المُعلَن في السجلّ نفسِه.

    وحداتُ `core/*.py` تكتب `from core.x import y`، فلا يكفي تحميلُ ملفٍّ
    بمساره: بلا جذرٍ على `sys.path` يفشل الاستيرادُ عند أوّل تبعيّة داخليّة.
    والجذرُ مُعلَنٌ بياناً لأنّ تخمينَه في الاختبار يجعله ينكسر يوم يُنقَل الملفّ.
    """
    root = str(ROOT / entry["import_root"])
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(entry["module"])
    finally:
        if added and sys.path and sys.path[0] == root:
            sys.path.pop(0)


def _resolve(entry: dict):
    """سلسلةُ المِرساة كاملةً: وحدة ← رمز ← قيمةُ زمنِ التشغيل.

    لا تقرأ `line` ولا تفتح الملفَّ نصّاً. وهذا ليس إغفالاً: هو **الخاصّيّةُ**
    التي يُثبِتها `test_moving_the_declaration_line_does_not_break_the_anchor`.
    """
    module = _import_module(entry)
    value = getattr(module, entry["constant"])
    for step in entry.get("path", []):
        value = value[step]
    return value


def test_the_ledger_is_a_governed_manifest(ledger: dict) -> None:
    """`manifest_registry_guard` يسجّل تلقائيّاً كلَّ بيانٍ يحمل `adjudicated_on`،
    ويرفض أيَّ بيانٍ جديد خارج صنف `governed`. فالحقولُ الثلاثة شرطُ دخول."""
    for field in ("schema", "version", "adjudicated_on"):
        assert field in ledger, f"بيانٌ جديد بلا {field} يُرفَض في سجلّ البيانات"
    assert ledger["schema"] == "sahool.threshold_authority_ledger"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", ledger["adjudicated_on"])


def test_no_registered_threshold_is_dropped_from_the_inventory(entries: list[dict]) -> None:
    """«ولا تُسقطها من الجرد» — قيدٌ يختفي بلا أثر يُعيد الفجوةَ إلى الصمت."""
    assert {e["constant"] for e in entries} == EXPECTED_CONSTANTS
    keys = [(e["constant"], tuple(e.get("path", ()))) for e in entries]
    assert len(set(keys)) == len(keys), "قيدان بنفس الرمز والمسار — أحدهما يحجب الآخر"


def test_every_recorded_value_matches_the_symbol_it_names(entries: list[dict]) -> None:
    """الشرطُ الأوّل: تغييرُ القيمة في المصدر بلا تحديث السجلّ **يحمرّ**.

    ويصدق في الاتّجاهين: تحريرُ السجلّ بلا مسِّ الكود يحمرّ كذلك — فالمقارنةُ
    بين طرفين حقيقيّين، لا بين السجلّ ونسخةٍ منه.
    """
    for entry in entries:
        runtime = _resolve(entry)
        assert runtime == entry["value"], (
            f"{entry['constant']}: السجلّ يقول {entry['value']} "
            f"وزمنُ التشغيل يقول {runtime} — انحرفَ أحدُهما عن الآخر"
        )


def test_a_vanished_or_unimportable_symbol_is_a_failure(entries: list[dict]) -> None:
    """قيدٌ بلا نظيرٍ في الكود سجلٌّ يصف منصّةً غيرَ التي تعمل."""
    for entry in entries:
        module = _import_module(entry)
        assert hasattr(module, entry["constant"]), (
            f"{entry['constant']} غائبٌ عن {entry['module']} — القيدُ يصف رمزاً لا وجودَ له"
        )


def test_the_symbol_is_defined_in_the_named_module_not_re_exported(entries: list[dict]) -> None:
    """مِرساةٌ ترسو على وسيطٍ لا تحرس أصلاً.

    رمزٌ مُعادُ تصديره (`from .other import _X`) يمرّ على `getattr` بينما
    القيمةُ الحقيقيّةُ تُغيَّر في وحدةٍ أخرى لا يذكرها السجلّ — فيبقى أخضر
    وهو يحرس السرابَ. الشرطُ: التصريحُ نفسُه في ملفّ الوحدة المسمّاة.

    **والصياغةُ الأولى كانت تفترض إسناداً باسمٍ واحد** (`^NAME` ثمّ `=`)، فسقطت على
    `_DISEASE_T_MIN, _DISEASE_T_MAX = 10.0, 30.0` — تفكيكُ صفٍّ مشروعٌ تماماً.
    فالفحصُ الآن على **الطرف الأيسر كاملاً**: يقبل التفكيك ويظلّ يرفض
    `from other import NAME` لأنّ الاستيرادَ بلا `=`.
    """
    for entry in entries:
        module = _import_module(entry)
        source = Path(module.__file__).read_text(encoding="utf-8")
        declared = any(
            re.search(rf"(?<![\w.]){re.escape(entry['constant'])}(?![\w])", line.split("=", 1)[0])
            for line in source.splitlines()
            if "=" in line and line[:1] not in (" ", "\t", "#")
        )
        assert declared, (
            f"{entry['constant']} غيرُ مُصرَّحٍ في {entry['module']} — إعادةُ تصديرٍ أو استيراد"
        )


def test_every_recorded_value_is_a_plain_numeric_scalar(entries: list[dict]) -> None:
    """رمزٌ صار قاموساً أو قائمةً يمرّ على مقارنةٍ ساذجة ويكسر معنى «عتبة».

    و`bool` مستثنى صراحةً: في بايثون `True == 1`، فعتبةٌ صارت علماً منطقيّاً
    تُطابق السجلَّ عدديّاً وهي لم تعد عتبةً أصلاً.
    """
    for entry in entries:
        runtime = _resolve(entry)
        assert not isinstance(runtime, bool), f"{entry['constant']}: علمٌ منطقيّ لا عتبة"
        assert isinstance(runtime, (int, float)), (
            f"{entry['constant']}: نوعُ زمنِ التشغيل {type(runtime).__name__} ليس عدداً قياسيّاً"
        )
        assert type(runtime).__name__ == entry["value_type"], (
            f"{entry['constant']}: النوعُ المُعلَن {entry['value_type']} "
            f"والمقيس {type(runtime).__name__}"
        )


def test_the_recorded_file_points_at_the_module_that_was_imported(entries: list[dict]) -> None:
    """اتّساقُ الملفّ — لا السطر.

    مسارٌ في السجلّ لا يشير إلى الوحدة المستوردة يُرسِل القارئَ إلى ملفٍّ
    خاطئ. أمّا رقمُ السطر فيُفحَص وجودُه في المدى فقط: بيانُ قارئٍ لا مِرساة.
    """
    for entry in entries:
        module = _import_module(entry)
        assert Path(module.__file__).resolve() == (ROOT / entry["file"]).resolve(), (
            f"{entry['constant']}: السجلّ يشير إلى {entry['file']} "
            f"والوحدةُ المستوردة {module.__file__}"
        )
        line_count = len(Path(module.__file__).read_text(encoding="utf-8").splitlines())
        assert 1 <= entry["line"] <= line_count, (
            f"{entry['constant']}: السطر {entry['line']} خارج مدى الملفّ ({line_count})"
        )


def test_moving_the_declaration_line_does_not_break_the_anchor(entries: list[dict]) -> None:
    """الشرطُ الثاني المقابل: تحريكُ السطر **يبقى أخضر**.

    مُختبَرٌ بالتنفيذ لا بالوصف: تُحلّ القيمةُ من قيدٍ يحمل رقمَ سطرٍ خاطئاً
    عمداً. لو كان السطرُ جزءاً من سلسلة المِرساة لفشل هذا هنا — فنجاحُه
    **هو** البرهان أنّ `file:line` بيانُ قارئٍ لا مِرساةُ سلامة.
    """
    for entry in entries:
        displaced = {**entry, "line": entry["line"] + 10_000}
        assert _resolve(displaced) == entry["value"], (
            f"{entry['constant']}: سطرٌ مُزاح كسر الحلّ — المِرساةُ صارت سطريّة"
        )


def test_no_entry_is_executable_and_the_class_semantics_hold(entries: list[dict]) -> None:
    """التسجيلُ ليس ترخيصاً.

    «لا تغيّر القيم. لا توحّدها. لا تمنحها FINAL أو CALIBRATED.» فكلُّ قيدٍ
    `executable=false`، وكلُّ صنفٍ يجرّ حالةَ سلطته ومعايرته معاً — لا
    توليفةَ حرّة بين الحقول.
    """
    for entry in entries:
        assert entry["executable"] is False, f"{entry['constant']}: سياسةٌ قابلة للتنفيذ بلا أساس"
        rules = CLASS_SEMANTICS[entry["provenance_class"]]
        assert entry["authority_status"] == rules["authority_status"]
        assert entry["calibration_status"] == rules["calibration_status"]
        assert (entry["decision_record"] is None) is rules["decision_record_is_null"], (
            f"{entry['constant']}: صنفُه {entry['provenance_class']} وسجلُّ قراره لا يطابقه"
        )
        assert entry["recovery_condition"], "قيدٌ بلا شرطِ استعادة سجلُّ يأسٍ لا سجلُّ فجوة"
        assert "FINAL" not in entry["calibration_status"]
        assert "CALIBRATED" != entry["calibration_status"]


def test_a_container_path_resolves_and_says_so_when_it_does_not(entries: list[dict]) -> None:
    """عتبةٌ داخل حاوية: المسارُ جزءٌ من المِرساة، وانكسارُه يجب أن **يُسمّي** نفسه.

    بلا هذا، مفتاحٌ يُعاد تسميته يُفجّر `KeyError` عارياً داخل مُحلِّلٍ مشترك،
    فتحمرّ اختباراتٌ عدّة برسالةٍ لا تقول أيّ قيدٍ انكسر ولا عند أيّ خطوة —
    وحارسٌ يموت بلا تشخيص يُعلَّم الفريقُ تجاهُلَه (§٣.٢٥).
    """
    for entry in entries:
        path = entry.get("path")
        if not path:
            continue
        node = getattr(_import_module(entry), entry["constant"])
        walked: list[str] = []
        for step in path:
            assert isinstance(node, dict), (
                f"{entry['constant']}{walked}: الخطوةُ {step!r} على قيمةٍ ليست قاموساً"
            )
            assert step in node, (
                f"{entry['constant']}{walked}: المفتاح {step!r} غير موجود — "
                f"المتاح: {sorted(node)[:8]}"
            )
            node = node[step]
            walked.append(step)


def test_a_cited_basis_is_required_by_its_class_and_forbidden_outside_it(
    entries: list[dict],
) -> None:
    """الفصلُ بين الصنفين المحلّيّين مقيسٌ لا موصوف.

    `LOCALLY_DECIDED_WITH_CITED_BASIS` يلزمه **أساسٌ مستشهَد وخطّةُ معايرةٍ
    مُعلَنة**، وشرطُ رفعه تنفيذُ تلك الخطّة بعينها. فإن سُمِح لقيدٍ أن يحمل
    الصنفَ بلا أساس، صار الصنفُ ترقيةً مجّانيّة.

    والاتّجاهُ المقابل ألزم: قيدٌ في `..._BUT_UNCALIBRATED` يحمل أساساً
    مستشهَداً هو **قيدٌ مُصنَّفٌ دون حقّه** — يبقى شرطُ رفعه «شواهدُ تشغيل»
    بينما الواقعُ أنّ له خطّةً مُعلَنة. فالمنعُ هنا يمنع سوءَ تصنيفٍ في
    الاتّجاه الذي لا ينتبه له أحد.
    """
    for entry in entries:
        rules = CLASS_SEMANTICS[entry["provenance_class"]]
        record = entry["decision_record"] or {}
        has_basis = bool(record.get("cited_basis_en"))
        has_plan = bool(record.get("declared_calibration_plan_en"))

        if rules["requires_cited_basis"]:
            assert has_basis, f"{entry['constant']}: صنفٌ مستشهِد بلا أساسٍ مذكور"
            assert has_plan, f"{entry['constant']}: استشهادٌ بلا خطّةِ معايرةٍ مُعلَنة"
            assert entry["recovery_condition"], "خطّةٌ مُعلَنة بلا شرطِ رفعٍ يُحيل إليها"
        else:
            assert not has_basis, (
                f"{entry['constant']}: يحمل أساساً مستشهَداً وصنفُه لا يعترف به — "
                "إمّا الصنف خطأ أو الأساس مُقحَم"
            )
            assert not has_plan, f"{entry['constant']}: خطّةٌ مُعلَنة خارج صنفها"


def test_the_closing_rule_is_recorded_verbatim(ledger: dict) -> None:
    """القاعدةُ الخاتمة نصٌّ مُقِرٌّ لا إعادةُ صياغة: هي معيارُ الخروج من السجلّ."""
    assert ledger["closing_rule_en"] == (
        "Every threshold must have both an authority provenance and a calibration "
        "basis before it can become an executable registered policy."
    )
