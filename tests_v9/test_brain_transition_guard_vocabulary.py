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
