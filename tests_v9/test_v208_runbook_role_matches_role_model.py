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

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_RUNBOOK = _ROOT / "docs" / "runbooks" / "V208_SEASONS_SIM_RUN_LINEAGE_OPENING_RUNBOOK.md"
_ROLE_MODEL = _ROOT / "migrations" / "POSTGRES_SETUP.md"
_MIGRATION = _ROOT / "migrations" / "v208_seasons_sim_run_lineage.sql"

_OWNER = "sahool_user"


def _read(path: Path) -> str:
    assert path.is_file(), f"مفقود: {path}"
    return path.read_text(encoding="utf-8")


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
    tool = _read(_ROOT / "scripts_v9" / "migrate.py")
    runbook = _read(_RUNBOOK)
    assert quoted in tool, f"الأداة لم تعد تطبع {quoted!r} — راجِع الدليل"
    assert quoted in runbook, f"الدليل يقتبس صيغةً لا تطبعها الأداة بدل {quoted!r}"
