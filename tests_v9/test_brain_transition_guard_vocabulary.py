"""مفردات حارس انتقال الحالة — BRAIN-TRANSITION-GUARD-MATCHES-FAIL-CLOSED-01.

كان النمط `\\b(CLOSED|…)\\b` خاطئاً في الاتّجاهين معاً، وكلّ خطأ يُخفي الآخر:

* **إيجابيّة كاذبة:** `fail-closed` و`open-closed` **وصفُ تصميم** لا انتقالُ حالة،
  والشرطة حدُّ كلمة. والمصطلح يظهر **٢٧٣ مرّة في الدماغ وحده** و٤٧٧ ملفّاً في
  المستودع — فأيّ مذكّرة دماغيّة تشرح قاعدة fail-closed كانت تُرفَض برسالة عن
  «انتقال إغلاق/تحقّق». حجبٌ صحيح **بسبب كاذب**، وهو أسوأ من عدم الحجب: الرسالة
  تُرسِل القارئ يبحث عن ادّعاء لم يُكتَب قطّ.
* **سلبيّة كاذبة:** `CLOSED_IN_CODE` و`CLOSED_IN_CODE_AND_PG_PROVEN` هما **مفردة
  الإغلاق الفعليّة في هذا المستودع**، و`\\b` يسقط على `_` اللاحقة — فالادّعاءات
  الحقيقيّة التي وُجِد الحارس لأجلها كانت تمرّ من أمامه.

اكتُشف حين حجب هذا الحارسُ شريحةَ بروتوكول دماغ لا تدّعي إغلاقاً، لأنّ سطراً فيها
يشرح **لماذا** قاعدة تصنيف المفاتيح fail-closed.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "brain_state_transition_guard", ROOT / "scripts/ci/brain_state_transition_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(guard)

# ادّعاءات إغلاق حقيقيّة — يجب أن تُلتقَط.
_REAL_CLAIMS = [
    "+- **الحالة:** CLOSED",
    "+- **CLOSED_IN_CODE + PG16_PROVEN**",
    "+- CLOSED_IN_CODE_AND_PG_PROVEN",
    "+| GAP-X | عنوان | VERIFIED |",
    "+- RUNTIME_VERIFIED",
    "+- PRODUCTION_CERTIFIED",
    "+- الحالة verified حيّاً بعد النشر",
]

# وصف تصميم أو نصّ عابر — يجب ألّا يُلتقَط.
_NOT_CLAIMS = [
    "+- **لماذا الاتّجاه fail-closed:** العجز عن الإثبات ليس إثباتاً",
    "+- the rule is fail-closed by design",
    "+- open-closed principle applies here",
    "+- الحارس مُغلَق عند الفشل",
    "+- closedness of the import graph",
]


@pytest.mark.parametrize("line", _REAL_CLAIMS)
def test_real_closure_claims_are_still_caught(line: str):
    """الأهمّ: الإصلاح لا يُضعِف الحارس. مفردة الإغلاق الحقيقيّة تبقى محجوبة."""
    assert guard.CLOSED_RE.search(line), f"ادّعاء إغلاق حقيقيّ أفلت: {line}"


@pytest.mark.parametrize("line", _NOT_CLAIMS)
def test_design_descriptions_are_not_closure_claims(line: str):
    """`fail-closed` وصفُ تصميم — حجبُه يُرسِل القارئ خلف ادّعاء لم يُكتَب."""
    assert not guard.CLOSED_RE.search(line), f"إيجابيّة كاذبة: {line}"


def test_the_underscore_vocabulary_was_the_false_negative():
    """تثبيت الاتّجاه الثاني: `CLOSED_IN_CODE` كان يمرّ من أمام الحارس.

    النمط القديم `\\b(CLOSED)\\b` يسقط على `_` اللاحقة. هذا الاختبار يفشل لو عاد
    أحدٌ إلى حدود الكلمة المجرّدة — وهو الاتّجاه الذي لا تكشفه إيجابيّةٌ كاذبة.
    """
    assert guard.CLOSED_RE.search("+- الحالة: CLOSED_IN_CODE")
    assert guard.CLOSED_RE.search("+- الحالة: CLOSED_IN_CODE_AND_PG_PROVEN")


def test_brain_only_diff_without_any_claim_passes(capsys):
    """شريحة دماغ لا تدّعي إغلاقاً تمرّ — وهي الحالة التي كشفت العطل."""
    guard.check(
        ["sahool-brain/decisions/ledger.md"],
        "+- **لماذا الاتّجاه fail-closed:** شرح القاعدة\n",
    )
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out


def test_brain_only_diff_with_a_real_claim_is_still_rejected():
    """والحجب يبقى قائماً حيث يجب: إغلاق مُدَّعى بلا كود تنفيذيّ خارج الدماغ."""
    with pytest.raises(SystemExit):
        guard.check(["sahool-brain/gaps/registry.md"], "+- **الحالة:** CLOSED\n")


def test_a_real_claim_with_executable_evidence_passes(capsys):
    """الادّعاء مصحوباً بكود/اختبار خارج الدماغ يمرّ — وهذا عقد الحارس نفسه."""
    guard.check(
        ["sahool-brain/gaps/registry.md", "services/x/main.py"],
        "+- **الحالة:** CLOSED\n",
    )
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out


# ── BRAIN-TRANSITION-GUARD-MATCHES-A-QUOTED-STATUS-TOKEN-01 ────────────────────
#
# الحدّ أعلاه يقتل `fail-closed`، لكنّ الحدّ ليس مرساة: الرمز كان يُطابَق في أيّ موضع
# من السطر، فاقتباسُ حقلٍ يُقرأ ادّعاءً له. أطلق الحارس فعلاً على سطر يقول حرفيّاً إنّ
# `production_certified=0/81` **ليس** عيباً — نفيٌ صريح قُرِئ ادّعاءً.

# اقتباسٌ يقول إنّ القيمة صفر — لا يمكن أن يكون ادّعاء إغلاق.
_CITED_AS_ZERO = [
    "+- `production_certified=0/81` **ليس عيباً**: ثابت صدق يفرضه CI حرفيّاً",
    '+- CI يفرض `grep -F "production_certified: 0"` في capability-governance.yml',
    "+- `runtime_verified=0` كما هو، ولا يُرفَع على برهان ساكن",
    "+- الجرد يقول runtime_verified: 0 لكلّ القدرات الـ81",
    "+- production_certified=false في كلّ مصنوعة",
]

# ادّعاءات حقيقيّة بقيمة موجبة — يجب أن تبقى محجوبة بعد التضييق.
_POSITIVE_VALUE_CLAIMS = [
    "+- `production_certified: 1`",
    "+- runtime_verified: 1 بعد البرهان الحيّ على staging",
    "+- runtime_verified=1",
]


@pytest.mark.parametrize("line", _CITED_AS_ZERO)
def test_a_zero_valued_citation_is_not_a_closure_claim(line: str):
    """**الإيجابيّة الكاذبة المقيسة.**

    نثرُ هذا المستودع الذي يشرح ثوابت الصدق **يجب** أن يسمّي هذه الحقول — فذاك ما
    الثوابتُ هي. فحارسٌ يحجبه يمنع الكتابة التي يريدها، ويُرسِل قارئه خلف ادّعاء لم
    يُكتَب: حجبٌ صحيح لسبب خاطئ، وهو أسوأ من غياب الحجب.
    """
    assert not guard._is_claim(line), f"إيجابيّة كاذبة على اقتباس صفريّ: {line}"


@pytest.mark.parametrize("line", _POSITIVE_VALUE_CLAIMS)
def test_a_positive_valued_claim_is_still_rejected(line: str):
    """**الحدّ الذي يمنع التضييق من فتح ثغرة.**

    الاستثناء مشروط بالقيمة **صفراً** لا بوجود `=`/`:` — وإلّا صار `runtime_verified: 1`،
    وهو شكل الادّعاء الحقيقيّ بعينه، معفىً. أي أنّ إصلاح إيجابيّة كاذبة كان سيصنع
    سلبيّة كاذبة أخطر منها.
    """
    assert guard._is_claim(line), f"ادّعاء بقيمة موجبة أفلت: {line}"


def test_one_unquoted_mention_still_makes_the_line_a_claim():
    """الفشل في الجهة الآمنة: يكفي ذِكرٌ واحد غير مقتبَس ليعود السطر ادّعاءً."""
    line = "+- `production_certified=0` لكنّ GAP-Y — CLOSED"
    assert guard._is_claim(line)


@pytest.mark.parametrize("line", _REAL_CLAIMS)
def test_the_narrowing_did_not_weaken_the_original_vocabulary(line: str):
    """كلّ ادّعاء كان محجوباً قبل التضييق يبقى محجوباً بعده."""
    assert guard._is_claim(line), f"ادّعاء إغلاق حقيقيّ أفلت بعد التضييق: {line}"


# ── BRAIN-TRANSITION-GUARD-MATCHES-A-DISCUSSED-POLICY-STATE-01 ──────────────────
# **صنفُ إيجابيّةٍ كاذبةٍ ثالث، مقيسٌ على #1035 لا مُفترَض — وهذه الشواهدُ مقلوبة.**
#
# الرمزُ يَرِد **مفعولاً به في جملةٍ عن سياسةٍ حالتُها كذلك** — «قراءةُ الحالة المغلقة
# إذناً عامّاً» في وصف طفرةٍ مُسجَّلة، أو نثرٌ يشرح بوّابةً حالتُها كذلك. وهو ليس
# ادّعاءَ بلوغِ حالة، ولا يُعفيه `_CITED_AS_ZERO` لأنّه ليس إسناداً بقيمةٍ صفريّة.
#
# كانت هذه الكتلةُ **تُثبِّت العطل** بشواهدَ تقول «ما يزال يُقرأ ادّعاءً»، وتنصّ على أن
# **تُقلَب لا تُحذَف** متى أُغلِقت الفجوة. وهذا ما جرى: المُرساةُ صارت الخطَّ الطباعيّ —
# رمزٌ داخل ` ` أو «» اسمٌ يُذكَر لا حالةٌ تُدَّعى — فانقلب شاهدان.
#
# **والثالثُ لم ينقلب، ويبقى هنا بحرفه:** `**البوّابة CLOSED عالميّاً**` نثرٌ عارٍ بلا
# اقتباس، ولا يفصله عن ادّعاءٍ حقيقيّ شيءٌ يُقاس. إبقاؤه محجوباً هو الفشلُ في الجهة
# الآمنة، والعلاجُ الكتابيّ حاضر: ضع الرمزَ بين ` ` إن كنتَ تسمّيه.
_QUOTED_POLICY_STATE = (
    "+- الطفرةُ تُكذِّب «قراءةَ CLOSED إذناً عامّاً» — أي أنّ الرمز اسمُ حالةٍ يُتحدَّث عنها.",
    "+`state_semantics_ar.CLOSED` يصف الحظر، و`OPEN` يصف قبولَ أدلّة المرحلة صفر نهائيّاً.",
    "+- المقتبَسُ “CLOSED” في تقريرٍ إنجليزيّ اسمٌ كذلك، لا ادّعاءَ بلوغ.",
)


@pytest.mark.parametrize("line", _QUOTED_POLICY_STATE)
def test_a_quoted_policy_state_is_not_a_closure_claim(line: str):
    """**الشاهدُ المقلوب.** رمزٌ بخطّ الشيفرة أو بين علامتَي اقتباس اسمٌ يُذكَر.

    الاقتباسُ فعلُ تسميةٍ لا فعلُ إسناد. ونثرُ هذا المستودع الذي يشرح بوّابةً أو
    يقتبس نصَّ طفرةٍ **يجب** أن يسمّي هذه الرموز — فذاك ما الشرحُ هو.
    """
    assert not guard._is_claim(line), f"إيجابيّة كاذبة على رمزٍ مقتبَس: {line}"


def test_bare_prose_is_still_read_because_a_claim_does_land_there():
    """**الحدُّ الذي يمنع هذا التضييق من فتح ثقب — وهو مقيسٌ لا احتياطيّ.**

    الاتّجاهُ المُسجَّل لهذه الفجوة كان «الإرساءُ على العنوان»، بحجّة أنّ الادّعاء في
    هذا المستودع لا يقع في المتن. والقياسُ يُكذِّب الحجّة: `sahool-brain/strategy.md`
    يحمل `**SAM2** closed (gated, env-unverified)` — ادّعاءُ إغلاقٍ في نثرٍ جارٍ،
    كان إرساءُ العنوان سيُطلِقه. فالمتنُ يبقى مقروءاً، ويُعفى **اقتباسُه** وحده.
    """
    assert guard._is_claim("+**SAM2** closed (gated, env-unverified)")
    assert guard._is_claim("+**البوّابة CLOSED عالميّاً**، ولا يُرفَع الحجر إلّا بتفويض.")


@pytest.mark.parametrize(
    "line",
    [
        "+## GAP-X — `CLOSED` @ `abc1234` (2026-09-20)",
        "+- **الحالة:** `verified` بعد النشر الحيّ",
        "+- **Status:** `CLOSED` locally",
    ],
)
def test_a_claim_in_its_canonical_position_is_read_whatever_its_typography(line: str):
    """**المُرساةُ لا تمسّ موضعَ الادّعاء القانونيّ.**

    العنوانُ وسطرُ `- **الحالة:**` هما حيث يُعلَن الادّعاء في هذا الدماغ، فيُقرآن
    بخطّ الشيفرة وبدونه. ولولا هذا الاستثناءُ لكان وضعُ الرمز بين ` ` في عنوانٍ
    كافياً لتمرير إغلاقٍ دماغيٍّ صرف — أي سلبيّةٌ كاذبةٌ في أخطر موضع.
    """
    assert guard._is_claim(line), f"ادّعاء في موضعه القانونيّ أفلت بالخطّ: {line}"


@pytest.mark.parametrize(
    "line",
    [
        "+- `production_certified: 1`",
        "+- النتيجة `runtime_verified=1` بعد البرهان الحيّ",
    ],
)
def test_a_quotation_that_assigns_a_positive_value_is_still_a_claim(line: str):
    """اقتباسٌ يُسنِد قيمةً موجبة ادّعاءٌ مهما كان خطُّه — وهذا شقيقُ حدِّ الصفر.

    `_CITED_AS_ZERO` أعفى `TOKEN=0` وحده لأنّ إعفاء `TOKEN=` مطلقاً كان يُعفي
    `runtime_verified: 1`. والخطُّ الطباعيّ لا يُغيّر ذلك: `` `production_certified: 1` ``
    ادّعاءٌ بعينه.
    """
    assert guard._is_claim(line), f"إسنادٌ موجبٌ أفلت داخل اقتباس: {line}"


def test_a_bare_token_between_two_quotations_is_still_a_claim():
    """الإفراغُ يقع على كلّ اقتباسٍ وحدَه، لا على ما بينها.

    نمطٌ جشِعٌ (`` `.*` ``) يبتلع ما بين اقتباسَين فيُعفي رمزاً عارياً بينهما — وهو
    ثقبٌ صامت: السطرُ يبدو مقتبَساً وهو ليس كذلك.
    """
    assert guard._is_claim("+- `أ` CLOSED `ب`")


# ── BRAIN-TRANSITION-GUARD-BLIND-TO-FRONTEND-CODE-01 ────────────────────────────────────
# كانت إصلاحاتُ الواجهة تُرفض «دماغيّةً صرفة» مع أنّ شيفرتها واختبارها في الدفعة. يُحتسَب
# مصدرُ الواجهة القابلُ للتنفيذ واختبارُه وحدهما؛ والتوثيقُ والإعدادُ والمُولَّدُ لا يكفي.
_CLAIM = "+- **الحالة:** CLOSED\n"


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/lib/referenceContracts.ts",
        "frontend/src/components/climate/ClimateAnalogsPanel.tsx",
        "frontend/src/lib/referenceContracts.test.ts",
        "frontend/e2e/field-workspace.spec.ts",
    ],
)
def test_a_frontend_source_or_test_change_counts_as_executable_evidence(path, capsys):
    guard.check(["sahool-brain/gaps/registry.md", path], _CLAIM)
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    "path",
    [
        "frontend/README.md",
        "frontend/package.json",
        "frontend/vite.config.ts",
        "frontend/src/index.css",
        "frontend/src/lib/indicatorsRegistry.generated.ts",
        "frontend/src/lib/platformCatalog.generated.ts",
    ],
)
def test_frontend_docs_config_or_generated_files_do_not_justify_a_closure(path):
    with pytest.raises(SystemExit, match="sahool-brain-only"):
        guard.check(["sahool-brain/gaps/registry.md", path], _CLAIM)


def test_brain_only_closure_is_still_rejected_after_the_frontend_widening():
    with pytest.raises(SystemExit, match="sahool-brain-only"):
        guard.check(["sahool-brain/gaps/registry.md", "sahool-brain/log.md"], _CLAIM)


# --- BRAIN-TRANSITION-GUARD-BLIND-TO-FIXED-01 -----------------------------------------------
# الحارسُ يقرأ **انتقالَ** صفٍّ إلى ``fixed`` لا الكلمة: قاعدةُ «fixed في PR إصلاحها» (decisions/ledger.md،
# #1136) كانت مطلبَ مراجعة لأنّ ``CLOSED_RE`` لا يطابق fixed. الانتقالُ بلا شيفرةٍ يُرفض باسم الفجوة،
# وتحريرُ صفٍّ fixed أصلاً أو ذكرُ الكلمة في السرد أو مدخلٌ تاريخيّ لا يُحمِّره.

BRAIN_ONLY = ["sahool-brain/gaps/registry.md", "sahool-brain/log.md"]
WITH_TEST = [*BRAIN_ONLY, "tests_v9/test_some_fix.py"]

TABLE = """# سجلّ

| id | العنوان | المجال/الخدمة | المصدر | الحالة |
|---|---|---|---|---|
| GAP-ALPHA-01 | عيبٌ أوّل | svc | `a.py` | {alpha} |
| GAP-BETA-01 | عيبٌ ثانٍ | svc | `b.py` | **fixed** (`abc1234`) — شاهدٌ قائم |
"""

SECTION = """
## GAP-GAMMA-01 — عيبٌ في قسم
<!-- gap-registry: current -->
- **الحالة:** {gamma}
- **المصدر:** `c.py`

## GAP-GAMMA-01 — المدخل السابق
<!-- gap-registry: historical -->
- **الحالة:** {old}
"""


def registry(alpha="open", gamma="**open** (2026-10-05)", old="open", extra=""):
    return TABLE.format(alpha=alpha) + SECTION.format(gamma=gamma, old=old) + extra


def test_brain_only_table_row_moved_to_fixed_is_rejected_by_name():
    base, head = registry(), registry(alpha="**fixed** (`def5678`)")
    assert guard.fixed_transitions(base, head) == ["GAP-ALPHA-01"]
    with pytest.raises(SystemExit) as exc:
        guard.check_fixed(BRAIN_ONLY, base, head)
    assert "GAP-ALPHA-01" in str(exc.value)


def test_brain_only_section_state_moved_to_fixed_is_rejected():
    base, head = registry(), registry(gamma="**fixed** (2026-10-05، عند `def5678`)")
    assert guard.fixed_transitions(base, head) == ["GAP-GAMMA-01"]
    with pytest.raises(SystemExit):
        guard.check_fixed(BRAIN_ONLY, base, head)


def test_new_gap_registered_already_fixed_counts_as_a_transition():
    row = "| GAP-DELTA-01 | جديد | svc | `d.py` | **fixed** (`def5678`) |\n"
    base = registry()
    head = base.replace("| GAP-BETA-01", row.rstrip("\n") + "\n| GAP-BETA-01", 1)
    assert guard.fixed_transitions(base, head) == ["GAP-DELTA-01"]
    with pytest.raises(SystemExit):
        guard.check_fixed(BRAIN_ONLY, base, head)


def test_transition_with_executable_evidence_in_the_pr_passes():
    guard.check_fixed(WITH_TEST, registry(), registry(alpha="**fixed** (`def5678`)"))


@pytest.mark.parametrize(
    ("base_kwargs", "head_kwargs"),
    [
        ({}, {"extra": "\nنثرٌ يذكر fixed و**fixed** في سطرٍ حرّ.\n"}),
        ({}, {"old": "**fixed** (مدخلٌ تاريخيّ)"}),
        ({"alpha": "**fixed** (`1111111`)"}, {"alpha": "**fixed** (`1111111`) — صياغةٌ أوضح"}),
        ({"alpha": "**fixed** (`1111111`)"}, {"alpha": "**verified** — قياسٌ حيّ"}),
        ({}, {"alpha": "**open** — بقيّةٌ مكتوبة"}),
    ],
    ids=[
        "prose-mention",
        "historical-entry",
        "reword-fixed-row",
        "fixed-to-verified",
        "open-stays-open",
    ],
)
def test_no_transition_to_fixed_is_not_blocked(base_kwargs, head_kwargs):
    base, head = registry(**base_kwargs), registry(**head_kwargs)
    assert guard.fixed_transitions(base, head) == []
    guard.check_fixed(BRAIN_ONLY, base, head)


def test_annotated_policy_row_is_not_a_fixed_state():
    head = registry(alpha="<!-- gap-registry: policy --> fixed by design")
    assert guard.fixed_transitions(registry(), head) == []


def test_fenced_example_is_not_read_as_a_state():
    fence = "\n```\n| id | الحالة |\n|---|---|\n| GAP-EPS-01 | **fixed** |\n```\n"
    assert guard.fixed_transitions(registry(), registry(extra=fence)) == []


def test_the_real_registry_moving_one_open_row_to_fixed_is_caught():
    g = guard._measure_module()
    text = (ROOT / "sahool-brain/gaps/registry.md").read_text(encoding="utf-8")
    before = guard.fixed_gap_ids(text)
    for line in text.splitlines():
        cells = g.table_cells(line) if line.startswith("| ") else []
        if len(cells) == 5 and g.classify(cells[-1])[0] == "open" and g.LABEL.fullmatch(cells[0]):
            break
    else:
        pytest.fail("no open table row in the real registry")
    gap_id = g.LABEL.fullmatch(cells[0]).group("id")
    moved = "| " + " | ".join([*cells[:-1], "**fixed** (`def5678`)"]) + " |"
    head = text.replace(line, moved, 1)
    assert gap_id not in before
    assert guard.fixed_transitions(text, head) == [gap_id]
    with pytest.raises(SystemExit):
        guard.check_fixed(BRAIN_ONLY, text, head)


# وسمُ ``historical`` لا يُسقط الحالة إلّا في سلسلةٍ مُراجَعة (حاليٌّ واحد والباقي تاريخيّ) — قاعدةُ
# gap_registry_measure.measure() نفسها. مدخلٌ منفردٌ موسومٌ تاريخيّاً كان طريقاً لتسجيل fixed في الدماغ وحده.
_LONE_HISTORICAL = """
## GAP-ZETA-01 — مدخلٌ وحيدٌ موسومٌ تاريخيّاً
<!-- gap-registry: historical -->
- **الحالة:** **fixed** (`def5678`)
"""

_NO_CURRENT = """
## GAP-ETA-01 — الأوّل
<!-- gap-registry: historical -->
- **الحالة:** **fixed** (`def5678`)

## GAP-ETA-01 — الثاني
<!-- gap-registry: historical -->
- **الحالة:** open
"""


@pytest.mark.parametrize(
    ("extra", "gap_id"),
    [(_LONE_HISTORICAL, "GAP-ZETA-01"), (_NO_CURRENT, "GAP-ETA-01")],
    ids=["lone-historical-entry", "sequence-without-current"],
)
def test_a_historical_tag_outside_a_reviewed_sequence_does_not_hide_a_fixed_state(extra, gap_id):
    base, head = registry(), registry(extra=extra)
    assert guard.fixed_transitions(base, head) == [gap_id]
    with pytest.raises(SystemExit) as exc:
        guard.check_fixed(BRAIN_ONLY, base, head)
    assert gap_id in str(exc.value)


def _git(cwd, *args):
    import subprocess

    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()


# BRAIN-TRANSITION-GUARD-DIES-ON-ARABIC-DIFF-UNDER-C-LOCALE-01: ``git diff`` لـ``sahool-brain/`` كان يُفكّ
# بترميز اللغة، فتحت ``LC_ALL=C`` يموت الحارسُ بـUnicodeDecodeError على أوّل حرفٍ عربيّ قبل أن يحكم. عدّاءُ CI
# افتراضيّه UTF-8 فلا يراه الجناحُ إلّا إن فُرِضت لغةُ C على الحارس نفسه — وهذا ما تفعله حالةُ ``c_locale``.
@pytest.mark.parametrize(
    ("change", "rejected", "c_locale"),
    [("delete", True, False), ("add", False, False), ("delete", True, True), ("add", False, True)],
    ids=["delete", "add", "delete-c_locale", "add-c_locale"],
)
def test_a_deleted_test_file_is_not_executable_evidence(tmp_path, change, rejected, c_locale):
    """حذفُ ملفٍّ تحت ``tests_v9/`` لا يبرّر انتقالاً إلى fixed؛ وإضافةُ اختبارٍ تبرّره (الضابط)."""
    import os
    import subprocess
    import sys

    env = None
    if c_locale:
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "LANG")}
        env.update(LC_ALL="C", PYTHONUTF8="0")

    (tmp_path / "sahool-brain/gaps").mkdir(parents=True)
    (tmp_path / "tests_v9").mkdir()
    reg = tmp_path / guard.REGISTRY
    reg.write_text(registry(), encoding="utf-8")
    (tmp_path / "tests_v9/test_old.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    reg.write_text(registry(alpha="**fixed** (`def5678`)"), encoding="utf-8")
    if change == "delete":
        (tmp_path / "tests_v9/test_old.py").unlink()
    else:
        (tmp_path / "tests_v9/test_new.py").write_text(
            "def test_y():\n    pass\n", encoding="utf-8"
        )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "head")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/brain_state_transition_guard.py"),
            "--base",
            "HEAD~1",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert (result.returncode != 0) is rejected, result.stdout + result.stderr
    assert ("GAP-ALPHA-01" in result.stderr) is rejected


# BRAIN-TRANSITION-GUARD-BLIND-TO-FIXED-01 (تصحيحٌ ثانٍ): الدليلُ محتوى لا اسم. ``--name-only`` كان يُدرج الاسمَ
# الجديد لإعادة تسميةٍ صرفة، فـ``git mv`` لاختبارٍ قائم يُمرِّر انتقالاً إلى fixed في الدماغ وحده.
@pytest.mark.parametrize(
    ("change", "rejected"),
    [
        ("pure_rename", True),  # R100
        ("pure_copy", True),  # C100 — ``-M`` لا يكتشفه فيصل ``A`` ببصمةٍ موجودة في الأساس
        ("chmod_only", True),  # تغييرُ صلاحيّاتٍ بلا محتوى
        ("rename_with_edit", False),  # الضابط: R<100 يحمل محتوىً جديداً
    ],
)
def test_a_pure_rename_or_copy_of_a_test_is_not_executable_evidence(tmp_path, change, rejected):
    """pure rename + brain-only open→fixed ⇒ reject (ومثلُه النسخُ وتغييرُ الصلاحيّات)."""
    import subprocess
    import sys

    (tmp_path / "sahool-brain/gaps").mkdir(parents=True)
    (tmp_path / "tests_v9").mkdir()
    reg = tmp_path / guard.REGISTRY
    reg.write_text(registry(), encoding="utf-8")
    body = "".join(f"def test_{i}():\n    assert {i} == {i}\n\n" for i in range(12))
    old = tmp_path / "tests_v9/test_old.py"
    old.write_text(body, encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    reg.write_text(registry(alpha="**fixed** (`def5678`)"), encoding="utf-8")
    if change == "pure_rename":
        _git(tmp_path, "mv", "tests_v9/test_old.py", "tests_v9/test_renamed.py")
    elif change == "pure_copy":
        (tmp_path / "tests_v9/test_copy.py").write_text(body, encoding="utf-8")
    elif change == "chmod_only":
        old.chmod(0o755)
    else:
        _git(tmp_path, "mv", "tests_v9/test_old.py", "tests_v9/test_renamed.py")
        (tmp_path / "tests_v9/test_renamed.py").write_text(
            body + "def test_fix():\n    assert True\n", encoding="utf-8"
        )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "head")
    status = _git(tmp_path, "diff", "--name-status", "-M", "HEAD~1", "HEAD")
    if change == "pure_rename":
        assert "R100" in status, status  # الشاهدُ يصنع ما يدّعيه
    if change == "chmod_only":
        assert "M\ttests_v9/test_old.py" in status, status
    if change == "rename_with_edit":
        assert re.search(r"^R0?[0-9]{2}\t", status, re.M), status
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/brain_state_transition_guard.py"),
            "--base",
            "HEAD~1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert (result.returncode != 0) is rejected, result.stdout + result.stderr
    assert ("GAP-ALPHA-01" in result.stderr) is rejected


def test_raw_parsing_keeps_the_new_name_and_the_similarity_score():
    z = "0" * 40
    raw = (
        f":100644 100644 {'a' * 40} {'a' * 40} R100\0tests_v9/old.py\0tests_v9/new.py\0"
        f":000000 100644 {z} {'b' * 40} A\0tests_v9/added.py\0"
        f":100644 100644 {'c' * 40} {'d' * 40} R087\0x.py\0y.py\0"
    )
    entries = guard.parse_raw(raw)
    assert entries == [
        ("R100", "a" * 40, "tests_v9/new.py"),
        ("A", "b" * 40, "tests_v9/added.py"),
        ("R087", "d" * 40, "y.py"),
    ]
    # R100 يحمل بصمةَ مصدره، فهي في شجرة الأساس بالضرورة؛ و``A`` ببصمةٍ قائمة نسخٌ (C100).
    base_blobs = {"a" * 40, "b" * 40, "c" * 40}
    assert guard.content_evidence(entries, base_blobs) == ["y.py"]


# BRAIN-TABLE-VERIFIED-TRANSITION-BYPASSES-GUARD-01 (DG-02): the typography of the state cell no longer decides.
@pytest.mark.parametrize("cell", ["`verified`", "**verified**", "verified (`def5678`)"])
def test_brain_only_table_row_moved_to_verified_is_rejected_whatever_its_typography(cell):
    base, head = registry(), registry(alpha=cell)
    assert guard.verified_transitions(base, head) == ["GAP-ALPHA-01"]
    with pytest.raises(SystemExit) as exc:
        guard.check_verified(BRAIN_ONLY, base, head)
    assert "verified transition rejected for GAP-ALPHA-01" in str(exc.value)


def test_brain_only_section_state_moved_to_verified_is_rejected():
    base, head = registry(), registry(gamma="**verified** (2026-10-12)")
    assert guard.verified_transitions(base, head) == ["GAP-GAMMA-01"]
    with pytest.raises(SystemExit):
        guard.check_verified(BRAIN_ONLY, base, head)


def test_a_verified_transition_with_executable_evidence_passes_the_guard():
    guard.check_verified(WITH_TEST, registry(), registry(alpha="`verified`"))


def test_a_row_that_stays_verified_is_not_a_transition():
    head = registry(alpha="**verified** (`def5678`)")
    assert guard.verified_transitions(head, head) == []
    guard.check_verified(BRAIN_ONLY, head, head)


# مراجعةُ Copilot على #1166: الوسمُ يُخرج الخليّةَ من الحالات بقرار القياس وحده — وسمٌ واحد من
# ``alias``/``policy``/``adjudicated`` — لا أيُّ وسم.
@pytest.mark.parametrize("state", ["verified", "fixed"])
def test_a_cell_with_a_non_exempting_annotation_is_still_read_as_its_state(state):
    cell = f"<!-- gap-registry: current --> `{state}`"
    base, head = registry(), registry(alpha=cell)
    assert guard.gap_ids_in_state(head, state) >= {"GAP-ALPHA-01"}
    moved = guard.verified_transitions if state == "verified" else guard.fixed_transitions
    assert moved(base, head) == ["GAP-ALPHA-01"]


@pytest.mark.parametrize("kind", ["alias", "policy", "adjudicated"])
def test_a_single_non_state_annotation_still_exempts_the_cell(kind):
    head = registry(alpha=f"<!-- gap-registry: {kind} --> `verified`")
    assert guard.verified_transitions(registry(), head) == []


# مراجعةُ Copilot على #1166: الاختباراتُ أعلاه تستدعي ``check_verified`` مباشرةً، فنزعُ ربطه في ``main()`` كان يُبقيها
# خضراء. هذا يشغّل الحارسَ نفسَه على مستودعٍ مؤقّت كما يشغّله CI.
@pytest.mark.parametrize(
    ("with_test", "rejected"), [(False, True), (True, False)], ids=["brain-only", "with-test"]
)
def test_the_cli_rejects_a_brain_only_backticked_verified_row(tmp_path, with_test, rejected):
    import subprocess
    import sys

    (tmp_path / "sahool-brain/gaps").mkdir(parents=True)
    (tmp_path / "tests_v9").mkdir()
    reg = tmp_path / guard.REGISTRY
    reg.write_text(registry(), encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    reg.write_text(registry(alpha="`verified`"), encoding="utf-8")
    if with_test:
        (tmp_path / "tests_v9/test_new.py").write_text(
            "def test_y():\n    pass\n", encoding="utf-8"
        )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "head")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/brain_state_transition_guard.py"),
            "--base",
            "HEAD~1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert (result.returncode != 0) is rejected, result.stdout + result.stderr
    assert ("verified transition rejected for GAP-ALPHA-01" in result.stderr) is rejected


# BRAIN-TRANSITION-GUARD-BLIND-TO-ARABIC-STATUS-01: exercise the real CLI, not
# merely an Arabic regexp. The full registry context carries scope and history.
@pytest.mark.parametrize(
    "template",
    [
        "## GAP-ARABIC-01 — {state}\n",
        "## `GAP-ARABIC-01` — وصف العطل ({state} 2026-10-14)\n",
        "## GAP-ARABIC-01 — وصف العطل\n- **الحالة:** {state}\n",
        "| id | الحالة |\n|---|---|\n| GAP-ARABIC-01 | {state} |\n",
    ],
    ids=["heading", "backticked-heading-parenthesis", "section", "table"],
)
@pytest.mark.parametrize("with_test", [False, True], ids=["brain-only", "with-evidence"])
def test_cli_arabic_closure_requires_executable_evidence(tmp_path, template, with_test):
    import subprocess
    import sys

    reg = tmp_path / guard.REGISTRY
    reg.parent.mkdir(parents=True)
    reg.write_text(template.format(state="مفتوحة"), encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    reg.write_text(template.format(state="**مُغلَقة**"), encoding="utf-8")
    if with_test:
        proof = tmp_path / "tests_v9/test_proof.py"
        proof.parent.mkdir()
        proof.write_text("def test_proof():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "head")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/brain_state_transition_guard.py"),
            "--base",
            "HEAD~1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == (0 if with_test else 1), result.stdout + result.stderr
    assert ("GAP-ARABIC-01" in result.stderr) is not with_test


@pytest.mark.parametrize("state", ["مُغلَقة", "مغلقة", "مُغلَق", "مُصلَحة", "مصلح", "مـُغْلَقة"])
@pytest.mark.parametrize("wrap", ["{}", "**{}**", "`{}`"])
def test_arabic_fixed_status_typography_and_diacritics(state, wrap):
    head = registry(alpha=wrap.format(state) + " — دليل الإصلاح")
    assert guard.fixed_transitions(registry(), head) == ["GAP-ALPHA-01"]
    with pytest.raises(SystemExit, match="GAP-ALPHA-01"):
        guard.check_fixed(BRAIN_ONLY, registry(), head)


def test_arabic_verification_is_a_separate_stronger_transition():
    base, head = registry(alpha="مُصلَحة"), registry(alpha="`مُتحقَّقة` حيّاً")
    assert guard.fixed_transitions(base, head) == []
    assert guard.verified_transitions(base, head) == ["GAP-ALPHA-01"]
    with pytest.raises(SystemExit, match="verified transition rejected for GAP-ALPHA-01"):
        guard.check_verified(BRAIN_ONLY, base, head)


@pytest.mark.parametrize(
    "value",
    [
        "open — كانت مُغلَقة سابقاً",
        "مفتوحة — مُصلَحة جزئيّاً فقط",
        "غير مُغلقة",
        "ليست مُصلَحة",
        "مُسجَّل لا مُصلَح",
        "مغلقاً عند الفشل",
        "مغلقة_افتراضياً",
        "مغلق-بالتصميم",
        "يفشل مُغلَقاً",
        "بلا إصدارٍ مُصلِح",
    ],
)
def test_arabic_state_does_not_search_prose_or_match_token_prefixes(value):
    assert guard.fixed_transitions(registry(), registry(alpha=value, gamma=value)) == []


@pytest.mark.parametrize("kind", ["alias", "policy", "adjudicated"])
def test_arabic_non_state_annotation_is_preserved(kind):
    assert (
        guard.fixed_transitions(registry(), registry(alpha=f"<!-- gap-registry: {kind} --> مُغلَقة"))
        == []
    )


def test_arabic_history_is_excluded_only_for_a_reviewed_chain():
    base = SECTION.format(gamma="open", old="open")
    head = SECTION.format(gamma="open", old="مُغلَقة")
    assert guard.fixed_transitions(base, head) == []
    assert guard.fixed_transitions("", head.replace("<!-- gap-registry: current -->", "")) == [
        "GAP-GAMMA-01"
    ]
    assert guard.fixed_transitions(
        "", head.replace("<!-- gap-registry: historical -->", "\n<!-- gap-registry: historical -->")
    ) == ["GAP-GAMMA-01"]


def test_arabic_historical_heading_cannot_hide_a_canonical_table_row():
    base = "## GAP-HISTORY-01 — مفتوحة\n<!-- gap-registry: current -->\n"
    history = "## GAP-HISTORY-01 — مُغلَقة\n<!-- gap-registry: historical -->\n"
    table = "| id | الحالة |\n|---|---|\n| GAP-OLD-01 | مُصلَحة |\n"
    assert guard.fixed_transitions(base, base + history + table) == ["GAP-OLD-01"]
    assert guard.fixed_transitions("", history + table) == ["GAP-HISTORY-01", "GAP-OLD-01"]


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_arabic_fenced_examples_are_not_registry_claims(fence):
    example = "## GAP-EXAMPLE-01 — مُغلَقة\n- **الحالة:** مُصلَحة\n"
    assert guard.fixed_transitions("", fence + "markdown\n" + example + fence + "\n") == []


def test_arabic_unchanged_status_rewording_is_not_a_transition():
    base = "## GAP-ARABIC-01 — مُغلَقة (2026-10-14)\n"
    assert guard.fixed_transitions(base, base + "نثرٌ يشرح لماذا يفشل مُغلَقاً.\n") == []
    assert guard.fixed_transitions(base, base.replace("مُغلَقة", "**مغلقة**")) == []


@pytest.mark.parametrize(
    "tail",
    ["الحارس مُغلَق عند الفشل", "مفتوحة — كانت مُغلقة سابقاً", "وصف (غير مُصلَحة)", "وصف (مُسجَّل لا مُصلَح)"],
)
def test_arabic_narrative_heading_is_not_a_status(tail):
    assert guard.fixed_transitions("", f"## GAP-ARABIC-01 — {tail}\n") == []


def test_arabic_table_reads_the_declared_column_and_requires_a_header():
    table = "| id | الحالة | الوصف |\n|---|---|---|\n| GAP-ARABIC-01 | open | مُغلَقة |\n"
    assert guard.fixed_transitions("", table) == []
    assert guard.fixed_transitions("", "| GAP-ARABIC-01 | مُغلَقة |\n") == []
    assert guard.fixed_transitions("", table.replace("| open | مُغلَقة |", "| مُغلَقة | وصف |")) == [
        "GAP-ARABIC-01"
    ]


def test_cli_arabic_table_does_not_inherit_an_unrelated_headings_history(tmp_path):
    template = (
        "## PARENT-01 — وصف\n<!-- gap-registry: historical -->\n"
        "| id | الحالة |\n|---|---|\n| GAP-ARABIC-01 | {state} |\n"
        "## PARENT-01 — وصف حالي\n<!-- gap-registry: current -->\n- **الحالة:** open\n"
    )
    assert guard.fixed_transitions(
        template.format(state="open"), template.format(state="مُغلَقة")
    ) == ["GAP-ARABIC-01"]
    test_cli_arabic_closure_requires_executable_evidence(tmp_path, template, False)


@pytest.mark.parametrize("state", ["مفتوح", "**مفتوحة**", "`open`", "OPEN"])
def test_arabic_heading_leading_open_state_wins_over_old_parenthesis(state):
    assert guard.fixed_transitions("", f"## GAP-ARABIC-01 — {state} (مُغلَقة سابقاً)\n") == []


def test_arabic_heading_leading_fixed_state_wins_over_old_verified_parenthesis():
    text = "## GAP-ARABIC-01 — مُصلَحة (مُتحقَّقة سابقاً)\n"
    assert guard.fixed_transitions("", text) == ["GAP-ARABIC-01"]
    assert guard.verified_transitions("", text) == []


@pytest.mark.parametrize("state", ["fixed", "`verified`", "**CLOSED_IN_CODE**", "runtime_verified"])
def test_leading_english_state_does_not_inherit_an_arabic_historical_parenthesis(state):
    assert guard._arabic_heading_state(f" — {state} (مُتحقَّقة سابقاً)") is None


# ── `BRAIN-HOT-MD-UNBOUNDED-NO-ARCHIVE-PATH-01`: a verbatim move is not a new claim ──
#
# `hot.md` now shrinks only by moving older entries byte for byte into
# `sahool-brain/archive/` (`brain_append_only_guard`). Those entries quote closure
# vocabulary by the hundred, so read naively every move re-asserts every old claim: on
# the first compaction a brain-only archival PR is rejected for lines it did not write.
# A line counts as moved only if the SAME text left `hot.md` in the same diff; anything
# else added to an archive is read as before.

_ARCHIVE_FILE = "sahool-brain/archive/hot_2026-07-01_2026-07-03.md"
_MOVED = "- **الحالة:** CLOSED"


def _diff(*files: tuple[str, list[str]]) -> str:
    """A real ``git diff --unified=0`` shape: headers, hunks, ``+``/``-`` lines."""
    out: list[str] = []
    for path, lines in files:
        out += [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@"]
        out += lines
    return "\n".join(out) + "\n"


def test_a_line_moved_verbatim_from_hot_md_to_its_archive_is_not_a_new_claim(capsys):
    diff = _diff(
        ("sahool-brain/hot.md", ["-" + _MOVED, "+> **2026-10-19 — pointer to the archive**"]),
        (_ARCHIVE_FILE, ["+" + _MOVED]),
    )
    guard.check(["sahool-brain/hot.md", _ARCHIVE_FILE], diff)
    assert "brain_state_transition_guard_ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    "files",
    [
        pytest.param(
            [("sahool-brain/hot.md", ["-" + _MOVED]), (_ARCHIVE_FILE, ["+" + _MOVED + " "])],
            id="archive-text-differs",
        ),
        pytest.param(
            [("sahool-brain/log.md", ["-" + _MOVED]), (_ARCHIVE_FILE, ["+" + _MOVED])],
            id="removed-from-another-journal",
        ),
        pytest.param(
            [
                ("sahool-brain/hot.md", ["-" + _MOVED]),
                (_ARCHIVE_FILE, ["+" + _MOVED, "+" + _MOVED]),
            ],
            id="one-removal-funds-one-line-only",
        ),
        pytest.param(
            [("sahool-brain/hot.md", ["-" + _MOVED, "+" + _MOVED + " again"])],
            id="new-claim-in-hot-md-itself",
        ),
        pytest.param(
            [
                ("sahool-brain/hot.md", ["-" + _MOVED]),
                ("sahool-brain/gaps/registry.md", ["+" + _MOVED]),
            ],
            id="moved-into-the-registry-not-the-archive",
        ),
    ],
)
def test_anything_but_a_verbatim_move_is_still_a_claim_and_is_named(files):
    with pytest.raises(SystemExit, match="sahool-brain-only") as raised:
        guard.check([path for path, _ in files], _diff(*files))
    assert _MOVED in str(raised.value), "the rejection must name the line it read as a claim"
