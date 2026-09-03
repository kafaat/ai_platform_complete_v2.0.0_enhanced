"""ذكر معرّف فجوة في رسالة التزام ادّعاءٌ — والحارس يفرض صدقه.

`BRAIN-CLAIM-UNVERIFIED-01`: رسالة #683 أعلنت تسجيل أربع فجوات ووصلت اثنتان. لا شيء في
المستودع كان يتحقّق من ذلك، فالادّعاء مرّ. هذه الاختبارات تُثبت أنّ الحارس يلتقطه.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/ci/brain_commit_claim_guard.py"

pytestmark = pytest.mark.unit


def _run(base: str, head: str = "HEAD") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), "--base", base, "--head", head],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_guard_passes_on_the_current_branch():
    result = _run("origin/main")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "brain commit claim guard: PASS" in result.stdout


def test_it_catches_the_real_historical_miss():
    """#683 أعلن أربع فجوات؛ اثنتان لم تصلا كعناوين أقسام.

    ليس مثالاً مصطنعاً — هذا الالتزام مدموج في main، وهو سبب وجود الحارس.
    """
    result = _run("4eded7a", "121ab09")
    assert result.returncode == 1, "الحارس لم يلتقط الفشل الذي وُجد لأجله"
    assert "UNIT-DORMANCY-WAKE-02" in result.stdout


def test_a_registered_id_is_accepted(tmp_path: Path):
    """وإلّا منع التوثيق بدل أن يفرضه: معرّف مسجَّل يجب أن يمرّ."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    known = mod.registry_ids()
    assert "IMAGERY-BLANK-THUMBNAIL-01" in known
    assert "BRAIN-CLAIM-UNVERIFIED-01" in known
    assert "CI-RLS-SUPERUSER-ROLE-01" not in known, "المعرّف المكرّر عاد"


def test_table_row_ids_count_as_registered():
    """الإيجابيّة الكاذبة التي شُحنت ثمّ صُحّحت.

    السجلّ يسجّل بشكلين: قسم `## ` وصفّ جدول. قصر الفحص على العناوين جعل ٢٢ فجوة
    مسجَّلة تُعامَل كغير مسجَّلة، فتسقط أيّ PR تذكرها برسالة تطالبها بتسجيل ما هو
    مسجَّل. أسوأ من ثغرة: حارس يعاقب على الامتثال.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    known = mod.registry_ids()
    assert "CAP-INT-004-INTEGRATION" in known, "معرّف صفّ جدول يُعامَل كغير مسجَّل"
    assert "DEPS-DEPENDABOT-4" in known


def test_the_false_positive_is_gone_on_merged_history():
    """37c3b56 مدموج ويذكر معرّف صفّ جدول — كان يسقط، ويجب أن يمرّ."""
    result = _run("37c3b56~1", "37c3b56")
    assert result.returncode == 0, result.stdout + result.stderr


def test_prose_mentions_still_do_not_register_a_gap():
    """التصحيح لم يوسّع القبول إلى النثر — وإلّا فقد الحارس معناه."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    registry = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    for gid in mod.registry_ids():
        declared = any(
            (line.startswith("## ") and gid in line)
            or (line.startswith("|") and gid in line.split("|")[1])
            for line in registry.splitlines()
        )
        assert declared, f"{gid} لم يأتِ من عنوان ولا من عمود معرّف"


def test_security_advisory_ids_are_not_treated_as_gap_claims():
    """`PYSEC-2026-1325` يُطابِق شكل المعرّف ولا يُسجَّل قطّ في السجلّ.

    التقطه الحارس على رسالة `UNIT-TEST-DORMANCY-01` التي تذكره توثيقاً لنتيجة
    `pip-audit` قبل/بعد. لو بقي، لدفع الحارسُ كلَّ رسالةٍ إلى **كتمان** رقم
    الاستشارة — عكس ما بُني له. الاستبعاد بالبادئة لا بالحالة الواحدة، لأنّ
    العلّة صنفيّة: هذه معرّفات تُصدرها جهة خارجيّة.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for advisory in ("PYSEC-2026-1325", "CVE-2024-24762", "GHSA-XXXX-YYYY-ZZZZ", "OSV-2023-1"):
        assert mod.is_advisory(advisory), advisory


def test_the_advisory_exemption_did_not_swallow_real_gap_ids():
    """التكذيب: الاستثناء ضيّق بالبادئة — معرّف فجوة حقيقيّ ما زال يُطالَب بالتسجيل."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for gid in (
        "UNIT-TEST-DORMANCY-01",
        "APP-ROUTES-EMPTY-01",
        "CVE-LIKE-BUT-NOT",
        "PYSECURITY-A-B",
    ):
        assert not mod.is_advisory(gid), f"{gid} استُثني خطأً كاستشارة"
    # والفشل التاريخيّ ما زال يُلتقَط بعد التعديل.
    assert _run("4eded7a", "121ab09").returncode == 1


def test_an_id_glued_to_arabic_text_is_read_whole_not_from_its_middle():
    """`\b` كان يقتطع المعرّف الملتصق بالعربيّة — فيخترع وهميّاً ويُفوّت الحقيقيّ معاً.

    الحرف العربيّ حرف كلمة، فلا حدّ كلمة بين `لـ` و`AUTH`؛ فيبدأ التطابق بعد أوّل
    شرطة. النتيجة عطبان في اتّجاهين متعاكسين: يُطالِب بتسجيل `E2E-UNDER-…` وهو لا
    وجود له، ويفوته `AUTH-E2E-…` وهو الادّعاء الحقيقيّ الذي بُني الحارس ليفحصه.
    التقطه الحارس على رسالة التزام فعليّة في هذه الشريحة.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._GAP_ID.findall("لـAUTH-E2E-UNDER-RESTRICTED-ROLE،") == [
        "AUTH-E2E-UNDER-RESTRICTED-ROLE"
    ]
    assert mod._GAP_ID.findall("بـUNIT-TEST-DORMANCY-01 و") == ["UNIT-TEST-DORMANCY-01"]
    # ولا يلتقط ذيل معرّف: لا مطابقة تبدأ بعد شرطة.
    assert "UNDER-RESTRICTED-ROLE" not in mod._GAP_ID.findall("AUTH-E2E-UNDER-RESTRICTED-ROLE")


def test_the_boundary_fix_did_not_break_ordinary_extraction():
    """التكذيب: الحدّ الجديد ما زال يلتقط المعرّف المحاط بمسافات/علامات، ويرفض الملتصق بحرف."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._GAP_ID.findall("ذكر APP-ROUTES-EMPTY-01 هنا") == ["APP-ROUTES-EMPTY-01"]
    assert mod._GAP_ID.findall("(APP-ROUTES-EMPTY-01)") == ["APP-ROUTES-EMPTY-01"]
    # الضمانة المقصودة **قراءة كاملة لا رفض**: رمز ملتصق بحرف ASCII — سابق أو لاحق —
    # يُقرأ كلّه ولا يُقتطَع من منتصفه. (توقّعتُ `[]` في الحالتين مرّتين متتاليتين وكنتُ
    # مخطئاً: كلاهما رمز صالح الشكل بذاته، والعطب الذي أُصلِح هو الاقتطاع لا القبول.)
    assert mod._GAP_ID.findall("XAPP-ROUTES-EMPTY-01") == ["XAPP-ROUTES-EMPTY-01"]
    assert mod._GAP_ID.findall("APP-ROUTES-EMPTY-01X") == ["APP-ROUTES-EMPTY-01X"]
    # وما لا يجوز بحال: تطابق يبدأ بعد شرطة فيُنتِج معرّفاً وهميّاً.
    for text in ("لـAUTH-E2E-UNDER-RESTRICTED-ROLE", "XAPP-ROUTES-EMPTY-01"):
        assert all(not m.startswith(("E2E-", "ROUTES-")) for m in mod._GAP_ID.findall(text))
    # والفشل التاريخيّ ما زال يُلتقَط بعد تغيير الحدّ.
    assert _run("4eded7a", "121ab09").returncode == 1


# ── صنف ثالث: معرّفات تفويض البوّابات ────────────────────────────────────────
def _module():
    """تحميل الحارس وحدةً — الاختبارات السابقة تُكرّره سطراً سطراً، وهذا يجمعه."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_gate_adjudication_id_is_not_demanded_as_a_gap_section(capsys):
    """تسجيلُ تفويضٍ في سجلّ الفجوات **كذب**: إذنُ مالكٍ لا عطلٌ مرصود.

    أسقط الحارسُ التزامَ ختمِ `GATE01-ADJ-2026-08-13-001` بـ`CONSUMED` مطالباً
    بقسمٍ في `gaps/registry.md`. وحالة التفويض `ISSUED`/`CONSUMED` لا `open`/`fixed`،
    فالمطلوب كان إدخالاً كاذباً — أو حذفَ المعرّف، وهو كتمانُ **أيّ تفويضٍ خُتِم**.
    """
    mod = _module()
    body = "خُتِم GATE01-ADJ-2026-08-13-001 بـCONSUMED بعد الدمج."
    mod.commit_messages = lambda base, head: [("abc1234", body)]
    assert mod.check("x", "y") == 0, capsys.readouterr().out


def test_a_fabricated_adjudication_id_is_still_rejected(capsys):
    """ولا يُستثنى الصنف كالاستشارة بل **يُتحقَّق منه**: مِلفُّه في هذه الشجرة.

    مبدأ الحارس أنّ الذكر ادّعاء. الاستشارة تُستثنى اضطراراً — مصدرها خارج الشجرة؛
    أمّا التفويض فيُقاس وجوده، وهو أقوى من الاستثناء لا أضعف منه.
    """
    mod = _module()
    mod.commit_messages = lambda base, head: [("abc1234", "بموجب GATE01-ADJ-2099-01-01-999")]
    assert mod.check("x", "y") == 1
    out = capsys.readouterr().out
    assert "GATE01-ADJ-2099-01-01-999" in out
    assert "adjudications" in out, "الرسالة لا تدلّ على السجلّ الصحيح"


def test_the_adjudication_class_did_not_swallow_real_gap_ids():
    """التكذيب: الشكل كامل لا بادئة — ومعرّفُ فجوةٍ يبدأ بـ`GATE` ما زال يُطالَب بالتسجيل."""
    mod = _module()
    for gid in (
        "GATE01-ONE-SHOT-LIFECYCLE-INCOMPLETE-01",
        "GATE01-STATE-MODEL-POORER-THAN-ITS-DECISIONS-01",
        "GATE01-ADJ-SOMETHING",
        "GATE1-ADJ-2026-08-13-001",
    ):
        assert not mod.is_adjudication(gid), f"{gid} عُومِل تفويضاً خطأً"
    assert mod.is_adjudication("GATE01-ADJ-2026-08-13-001")


def test_the_live_adjudication_is_verified_against_its_own_file(tmp_path):
    """الوجود يُقاس في المجلَّد لا يُفترَض — والمجلَّد الفارغ لا يُصدِّق شيئاً."""
    mod = _module()
    assert mod.adjudication_exists("GATE01-ADJ-2026-08-13-001")
    assert not mod.adjudication_exists("GATE01-ADJ-2026-08-13-001", tmp_path)


def test_a_truncated_adjudication_reference_is_diagnosed_as_such_not_as_a_gap():
    """صنفٌ رابع كان يُصنَّف خطأً، فيُعرَض عليه علاجٌ يستحيل اتّباعُه بصدق.

    ``GATE01-ADJ-2026-09-02`` — مرجعُ تفويضٍ ينقصه المقطع التسلسليّ — لا يطابق
    ``_ADJUDICATION``، فكان يسقط إلى فرع الفجوات ورسالتُه «سجّلها في
    ``gaps/registry.md``». وذاك بعينه ما يصفه متنُ الحارس بأنّه **كذب**: التفويض
    إذنُ مالكٍ لا عطلٌ مرصود. فالرسالةُ كانت تقود إلى ما يحذّر منه الملفّ.

    **والحكمُ لم يُخفَّف**: الذكرُ يبقى ادّعاءً ويبقى الفشلُ قائماً — يتغيّر
    التشخيصُ وحدَه. حارسٌ نصيحتُه خاطئةٌ يُصلَح بتصحيح النصيحة، لا بالتسامح.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("g", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    truncated = "GATE01-ADJ-2026-09-02"
    assert mod.is_truncated_adjudication(truncated)
    assert not mod.is_adjudication(truncated), "المبتور ليس تفويضاً صالحاً"

    # والكاملُ يبقى تفويضاً يُتحقَّق منه في مجلَّده — لا مبتوراً.
    full = "GATE01-ADJ-2026-09-02-001"
    assert mod.is_adjudication(full)
    assert not mod.is_truncated_adjudication(full), "ابتلع الصنفُ الجديدُ التفويضَ الكامل"

    # والشاهدُ السويّ: معرِّفُ فجوةٍ حقيقيٌّ لم يُبتلَع بالصنف الجديد.
    assert not mod.is_truncated_adjudication("WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01")
