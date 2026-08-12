"""دليلُ فتح `v208` يوجّه إلى **مالك المِهجرات**، لا إلى دورٍ آخر.

**العطل الذي يحرسه وقع فعلاً وأُصلِح:** أوّل صياغةٍ للدليل أوصت بدور
`sahool_jobs` نقلاً عن تعليقٍ في `scripts_v9/migrate.py`، بينما المرجع القانونيّ
لنموذج الأدوار (`migrations/POSTGRES_SETUP.md`) يقول إنّ **`sahool_user`** هو
مالك الهجرات. و`ALTER TABLE` يشترط **ملكيّة الجدول** لا صلاحيّةَ كتابةٍ فيه —
فمن اتّبع الدليل حرفيّاً كان يصطدم بـ`must be owner of table seasons`.

**ولماذا اختبارٌ لا تصحيحٌ وحده:** تصويبٌ في وثيقةٍ يعود صامتاً عند أوّل تحريرٍ
لاحق، ولا شيء يقول إنّه عاد. وهذا الاختبار يربط **الدليل بمصدره القانونيّ**:
فإن تغيّر نموذج الأدوار، أو انزلق الدليل إلى دورٍ غير المالك، يُحمِرّ.

**والمرساة على سطر التصدير لا على ذِكر الاسم:** الدليل **يذكر** `sahool_jobs`
عمداً ليشرح لماذا هو الخطأ. فتأكيدُ غيابِ الاسم كان سيُحمِرّ على الشرح نفسه —
وهو الصنف المُسجَّل `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`.

**ومتابعةُ ما بعد `#834` تُغلِق بابين بقيا مفتوحين بعد دمجه:**

**(F1)** الدليل صُوِّب، و**المصدرُ الذي أنتج الخطأ لم يُصوَّب**: `migrate.py` ظلّ
يطبع عند غياب `DATABASE_URL` مثالاً بدور `sahool_jobs`. وتصحيحُ الأثر مع بقاء
السبب يعيد إنتاج الخطأ على أوّل قارئٍ لا يمرّ بالدليل — وهو الأكثر، لأنّ رسالة
الأداة تصل إليه بلا أن يطلبها.

**(F2)** المسار المُستهدَف (§٤ب) كان يسمح بتطبيق `v208` وحدها بلا شرط، وهي
المُدخَل ٢١٣ من ٢٢٦ — فيصير `schema_migrations` **غير مرتَّبٍ بادئةً**: ثقبٌ في
السجلّ يجعل «إلى أين وصل المخطَّط؟» سؤالاً بجوابٍ كاذب. فأُضيف فحصٌ حاجب،
و**يستورد الأداة نفسها** فلا يستطيع أن ينحرف عن منطقها. وتأكيداتُه هنا تُحمِرّ
إن سقط الفحص أو نادى اسماً لم تعد الأداة تُصدِّره.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_RUNBOOK = _ROOT / "docs" / "runbooks" / "V208_SEASONS_SIM_RUN_LINEAGE_OPENING_RUNBOOK.md"
_ROLE_MODEL = _ROOT / "migrations" / "POSTGRES_SETUP.md"
_MIGRATION = _ROOT / "migrations" / "v208_seasons_sim_run_lineage.sql"
_TOOL = _ROOT / "scripts_v9" / "migrate.py"

_OWNER = "sahool_user"
_TARGET = "v208_seasons_sim_run_lineage.sql"

_ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _read(path: Path) -> str:
    assert path.is_file(), f"مفقود: {path}"
    return path.read_text(encoding="utf-8")


def _load_tool():
    """تُستورَد الأداة فعلاً — لا يُبحَث عن أسمائها نصّاً.

    فوجودُ `MIGRATION_ORDER` في ملفٍّ لا يعني أنّ الاستيراد يُصدِّره؛ والفحص
    الحاجب في الدليل ينادي هذه الأسماء على **وحدةٍ مستورَدة**، فيجب أن يُقاس
    كما يُنفَّذ.
    """
    spec = importlib.util.spec_from_file_location("migrate_tool_under_test", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_role_model_still_names_sahool_user_as_the_migrations_owner():
    """المصدر القانونيّ أوّلاً — فالدليل يتبعه ولا يُعرِّف بديلاً عنه."""
    text = _read(_ROLE_MODEL)
    assert re.search(rf"مالك الهجرات.*{_OWNER}", text), (
        f"{_ROLE_MODEL.name} لم يعد يُسمّي «{_OWNER}» مالكَ الهجرات — "
        "راجِع الدليل قبل أيّ شيء، فقد تغيّر نموذج الأدوار"
    )


def test_the_runbook_exports_the_owner_role_not_another():
    """المرساة على **سطر التصدير**: هو ما يُنسَخ ويُنفَّذ، لا ما يُقرأ شرحاً."""
    text = _read(_RUNBOOK)
    exports = re.findall(r"export DATABASE_URL='postgresql://([a-z_]+):", text)
    assert exports, "لا سطر تصديرٍ في الدليل — تغيّرت بنيته، راجِعه"
    assert set(exports) == {_OWNER}, (
        f"الدليل يُصدِّر أدواراً غير المالك: {sorted(set(exports))}. "
        "و`ALTER TABLE` يشترط ملكيّة الجدول لا صلاحيّة الكتابة"
    )


def test_the_runbook_cites_the_authoritative_role_model():
    """توجيهٌ بلا مرجعٍ يُنقَل بين الأجيال بلا سبيلٍ إلى مراجعته."""
    text = _read(_RUNBOOK)
    assert "POSTGRES_SETUP.md" in text, "الدليل لا يُحيل إلى المرجع القانونيّ لنموذج الأدوار"


def test_the_runbook_distinguishes_ownership_from_permission():
    """`must be owner` و`permission denied` تشخيصان مختلفان وعلاجُهما مختلف.

    وخلطُهما في جدول الأعطال يرسل المُصلِح إلى المكان الخطأ.
    """
    text = _read(_RUNBOOK)
    assert "must be owner of table seasons" in text
    assert "permission denied for table seasons" in text


def test_the_runbook_still_describes_the_migration_it_opens():
    """مرساةٌ على الخاصّيّة: الدليل يصف DDL هذه المِهجرة بعينها.

    فلو أُعيدت تسمية العمود أو غُيِّر نوعه، صار الدليل يصف شيئاً آخر.
    """
    migration = _read(_MIGRATION)
    assert "ADD COLUMN IF NOT EXISTS sim_run_id UUID" in migration
    assert "ADD COLUMN IF NOT EXISTS sim_run_id UUID" in _read(_RUNBOOK)


@pytest.mark.parametrize(
    "quoted",
    [
        "لا يوجد تراجع وهمي.",
        "(مُطبَّق)",
        "⚠ انجراف checksum!",
    ],
)
def test_every_quoted_tool_string_matches_the_tool_byte_for_byte(quoted):
    """اقتباسٌ ينحرف عن مخرَج الأداة يجعل البحث في السجلّات يُخفِق صامتاً.

    وأوّل صياغةٍ عندي حملت ثلاثة انحرافات: «وهميّ» بشدّة والأداة تطبع «وهمي» ·
    و«✓ مُطبَّق» والأداة تطبع `✓ <اسم الملفّ> (مُطبَّق)` · وانجرافٌ بلا علامة
    تعجّب. أمسكتها المراجعة، وهذا يمنع عودتها.
    """
    tool = _read(_TOOL)
    runbook = _read(_RUNBOOK)
    assert quoted in tool, f"الأداة لم تعد تطبع {quoted!r} — راجِع الدليل"
    assert quoted in runbook, f"الدليل يقتبس صيغةً لا تطبعها الأداة بدل {quoted!r}"


# ───────────────────────── F1 — تصويبُ المصدر لا الأثر ─────────────────────────


def test_the_tool_itself_teaches_the_owner_role():
    """المرساة نفسها، على **الأداة** هذه المرّة.

    رسالةُ `migrate.py` عند غياب `DATABASE_URL` هي أوسع سطرِ توجيهٍ في هذا
    المسار: تصل إلى كلّ من شغّل الأداة بلا إعداد، ومنهم من لم يقرأ الدليل قطّ.
    فبقاؤها على الدور الخطأ كان يعني أنّ التصويب في الوثيقة يغطّي الأقلّيّة.
    """
    exports = re.findall(r"export DATABASE_URL='postgresql://([a-z_]+):", _read(_TOOL))
    assert exports, "لا سطر مثالٍ في رسالة الأداة — تغيّرت بنيتها، راجِعها"
    assert set(exports) == {_OWNER}, (
        f"الأداة تطبع مثالاً بدورٍ غير المالك: {sorted(set(exports))}. "
        "و`ALTER TABLE` يشترط ملكيّة الجدول لا صلاحيّة الكتابة"
    )


def test_the_tool_cites_the_authoritative_role_model():
    """توجيهٌ بلا مرجع يُعاد اختراعُه خطأً — وهكذا وقع العطل أوّل مرّة."""
    assert "POSTGRES_SETUP.md" in _read(_TOOL), (
        "تعليق الأداة لا يُحيل إلى المرجع القانونيّ لنموذج الأدوار"
    )


def test_the_correction_did_not_break_the_deployment_path():
    """حدُّ التصويب: الاسم يبقى مقبولاً.

    `JOBS_DATABASE_URL` اسمُ **متغيّرٍ** يمرّره helm بهذا الاسم
    (`helm/sahool/templates/migration-job.yaml`)، لا اسمُ دور. وحذفُه انتقاماً من التعليق
    الخاطئ كان سيكسر مسار النشر — تصويبٌ يُنتِج عطلاً أكبر ممّا أصلح.
    """
    assert "JOBS_DATABASE_URL" in _read(_TOOL), (
        "الأداة لم تعد تقبل JOBS_DATABASE_URL — مسار helm ينكسر"
    )


# ──────────────────── F2 — الفحص الحاجب قبل المسار المُستهدَف ────────────────────

_GATE_SYMBOLS = ("MIGRATION_ORDER", "MIGRATIONS_DIR", "_applied", "_db_url", "_checksum")


@pytest.mark.parametrize("symbol", _GATE_SYMBOLS)
def test_every_symbol_the_gate_calls_still_exists_in_the_tool(symbol):
    """مقتطفٌ في دليلٍ ينهار عند التنفيذ أسوأ من لا مقتطف.

    فهو يُقرَأ ضماناً ويُنفَّذ فيرمي `AttributeError` في اللحظة التي بُني ليؤمّنها.
    وربطُ الفحص بالأداة (بدل إعادة كتابة منطقها) اشترى امتناعاً عن الانحراف
    وأورث تبعيّةً على أسمائها — وهذه التأكيدات هي ثمنُها المدفوع.
    """
    assert f"mig.{symbol}" in _read(_RUNBOOK), (
        f"الفحص الحاجب لم يعد ينادي {symbol} — راجِع §٤ب قبل أن تُسقِط التأكيد"
    )
    assert hasattr(_load_tool(), symbol), (
        f"الدليل ينادي `mig.{symbol}` والأداة لا تُصدِّره — المقتطف ينهار عند التنفيذ"
    )


def test_the_gate_precedes_the_targeted_apply_command():
    """شرطٌ مسبق يظهر **بعد** الأمر ليس شرطاً مسبقاً.

    والقارئ المستعجل ينسخ أوّل كتلةٍ يجدها؛ فالترتيب هنا خاصّيّةٌ لا تنسيق.
    """
    text = _read(_RUNBOOK)
    gate = text.find("شرطٌ حاجب")
    apply_cmd = text.find(f"-f migrations/{_TARGET}")
    assert gate != -1, "سقط الفحص الحاجب من §٤ب"
    assert apply_cmd != -1, "تغيّر أمر التطبيق المُستهدَف — راجِع المرساة"
    assert gate < apply_cmd, "الفحص الحاجب يظهر بعد أمر التطبيق فلا يحجب شيئاً"


def test_the_gate_cannot_crash_on_a_target_outside_the_manifest():
    """الفحص يستدعي `order.index(TARGET)` — وهي ترمي إن غاب الهدف.

    وانهيارُه بـ`ValueError` يُقرَأ «الأداة معطوبة» لا «الهدف غير مُسجَّل»،
    فيُرسِل المُشغِّل إلى التشخيص الخطأ. وهذا يُثبِت الفرضيّة التي يقوم عليها.
    """
    order = _load_tool().MIGRATION_ORDER
    assert _TARGET in order, f"{_TARGET} ليست في MANIFEST — الفحص الحاجب ينهار"
    assert order.index(_TARGET) > 0, "لا سابقاتٍ لها — الفحص يقيس مجموعةً فارغة"


# ───────────────── الإحالة إلى مسار helm — إحالةٌ لا تُتَّبع ليست إحالة ─────────────────

_HELM_JOB = _ROOT / "helm" / "sahool" / "templates" / "migration-job.yaml"

# **ولا يُفحَص هذا الملفّ بغياب الصيغة الخاطئة** — فهو مضطرٌّ إلى عرضها ليشرحها،
# تماماً كما يذكر الدليلُ `sahool_jobs` عمداً. وأوّل صياغةٍ لهذا الحارس فحصته
# فأحمرّ على **شرحه هو**: الصنف `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`
# المُسجَّل في صدر هذا الملفّ، وقعتُ فيه وأنا أعالجه. ويحرسه هنا التأكيد الموجَب
# التالي: المطلوب أن تكون الإحالة **صحيحة**، لا أن تغيب الصيغة الخاطئة.
_CITING_FILES = (_TOOL, _RUNBOOK)


@pytest.mark.parametrize("path", _CITING_FILES, ids=lambda p: p.name)
def test_the_helm_citation_is_repo_relative_not_a_dangling_suffix(path):
    """`templates/migration-job.yaml` مجرّداً لا يقع على شيء من جذر المستودع.

    وكتبتُها هكذا في **ثلاثة** مواضع، فأمسكتها المراجعة في ثلاثتها. وهي بالضبط
    الصنف الذي يعالجه هذا الالتزام: إحالةٌ تبدو دقيقة ولا تُتَّبع، فيصير الادّعاء
    المستند إليها غير قابلٍ للفحص — وهو أسوأ من غياب الإحالة، لأنّه يشتري ثقةً
    بلا ما يقابلها.
    """
    stale = re.findall(r"(?<!helm/sahool/)templates/migration-job\.yaml", _read(path))
    assert not stale, (
        f"{path.name} يُحيل إلى `templates/migration-job.yaml` مجرّداً — "
        "المسار من جذر المستودع هو `helm/sahool/templates/migration-job.yaml`"
    )


def test_the_cited_helm_line_still_defines_the_variable():
    """رقمُ السطر يُشتقّ ويُقارَن، فلا يُثبَّت في تأكيدٍ يبيت صامتاً.

    وإن انزاح التعريف، تُحمِرّ الرسالةُ **بالرقم الصحيح** — فيصير الحارس دليلاً
    إلى التصويب لا مجرّد إعلانِ خطأ.
    """
    lines = _read(_HELM_JOB).splitlines()
    actual = [i for i, line in enumerate(lines, 1) if "- name: JOBS_DATABASE_URL" in line]
    assert len(actual) == 1, f"تعريفات JOBS_DATABASE_URL في {_HELM_JOB.name}: {actual}"
    cited = f"helm/sahool/templates/migration-job.yaml:{actual[0]}"
    for path in (_TOOL, _RUNBOOK):
        assert cited in _read(path), (
            f"{path.name} يُحيل إلى سطرٍ غير الذي يعرّف المتغيّر — الصحيح `{cited}`"
        )


def test_the_position_claim_in_the_runbook_is_still_measured():
    """«٢١٣ من ٢٢٦» رقمٌ مقيس، والأرقام المقيسة تنجرف صامتةً.

    وهو ليس زينة: عليه يقوم تبرير الفحص الحاجب (كم سابقةً يمكن تخطّيها).
    """
    order = _load_tool().MIGRATION_ORDER
    position = str(order.index(_TARGET) + 1).translate(_ARABIC_DIGITS)
    total = str(len(order)).translate(_ARABIC_DIGITS)
    text = _read(_RUNBOOK)
    assert f"**{position}** من {total}" in text or f"{position} من {total}" in text, (
        f"الدليل لا يقول «{position} من {total}» — انجرف الترتيب في MANIFEST"
    )
