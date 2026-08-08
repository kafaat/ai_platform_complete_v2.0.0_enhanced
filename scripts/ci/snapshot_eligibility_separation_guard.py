#!/usr/bin/env python3
"""اللقطة لا تكتسب أهليّة — `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`.

**الخاصّيّة المحروسة واحدة ومحدّدة:** جسم اللقطة المعنون بمحتواه يبقى **حقائق مرصودة**،
فلا يدخله `policy_version` ولا `eligibility_assessment_id` ولا أيّ حكم أهليّة — لا في
النموذج ولا في المخطَّط.

**ولماذا حارسٌ لا اختبارٌ وحده:** الاختبارات تقيس التقييم كما هو مكتوب اليوم. وهذا
الصنف من الانحدار لا يأتي عبر التقييم أصلاً — يأتي من هجرةٍ تُضيف عموداً «للسرعة»، أو
من حقلٍ يُضاف إلى `VegetationSnapshotIn` لأنّ واجهةً احتاجته. وكلاهما يمرّ خضراء:
الاختبارات لا تنظر إلى مكانٍ لم يتغيّر فيه سلوك.

**والكلفة إن مرّ:** اللقطة معنونة بمحتواها (`UNIQUE(tenant_id, snapshot_hash)` ومُشغِّل
يمنع التحرير). فحقلٌ واحد داخلها يُغيّر **كلّ هاش قائم** عند أوّل تغيير سياسة ⇒ تنكسر
إعادة التشغيل ويُقطَع نَسَب الأدلّة. العطل لا يظهر يوم يُضاف الحقل بل يوم تتغيّر
السياسة أوّل مرّة — وحينها لا يدلّ شيء على السبب.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.

    python scripts/ci/snapshot_eligibility_separation_guard.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "decision-service"
MIGRATIONS = SERVICE / "migrations"
MODEL_FILE = SERVICE / "main.py"

SNAPSHOT_TABLE = "decision_vegetation_snapshots"
SNAPSHOT_MODEL = "VegetationSnapshotIn"

#: مفردات الحكم على الأهليّة. `decision_eligible` مقصودة: هي القيمة المنطقيّة القديمة
#: التي تعيش في سجلّ المؤشّرات، وموضعُها هناك — لا داخل اللقطة.
FORBIDDEN = (
    "policy_version",
    "eligibility_assessment_id",
    "eligibility_assessment",
    "decision_eligible",
    "eligibility_policy",
)

#: اقتباس اختياريّ. **لا يُطابَق زوجيّاً عمداً** (`"<t>` و`<t>"` مقبولتان): كاشفٌ لا
#: مُحلِّل نحويّ، والإفراط مجّانيّ.
_QUOTE = r'"?'

#: بادئة مخطَّط اختياريّة — عارية أو مقتبسة، **وبمسافات حول النقطة** (`public . t`
#: قانونيّة: مُحلِّل PostgreSQL يفصل الرموز بالمسافات كغيرها).
_SCHEMA = rf"(?:{_QUOTE}\w+{_QUOTE}\s*\.\s*)?"

#: الجدول المستهدف: `public.t` · `"t"` · `public."t"` — كلّها الجدول نفسه.
#:
#: **الثقب الرابع في النحو نفسه:** كانت الصياغة تقرأ الاسم **عارياً فقط**، فـ
#: `ALTER TABLE public."decision_vegetation_snapshots" ADD COLUMN decision_eligible`
#: — هجرةٌ مشروعة تماماً — تمرّ بصفر التقاط. الاقتباس في PostgreSQL يحفظ حالة الأحرف
#: ولا يُنشئ كياناً آخر.
_QUALIFIED = rf"{_SCHEMA}{_QUOTE}{SNAPSHOT_TABLE}{_QUOTE}"

#: اسم العمود عارياً أو مقتبساً، **مسبوقاً بنظرة أمام سالبة**.
#:
#: والنظرة ليست زينة: بلا دعم الاقتباس كان `(\w+)` يفشل عند `"` **فيتراجع المُطابِق عن
#: `(?:column\s+)?` ويلتقط `COLUMN` بوصفه اسم العمود** — اسمٌ ليس في `FORBIDDEN` فيمرّ
#: الحارس خضراء وقد نظر ورأى الشيء الخطأ. وهو الصنف نفسه الذي أفلتت به `IF NOT EXISTS`
#: أوّل مرّة. فدعمُ الاقتباس وحده لا يكفي: النظرة تمنع أن يُنتِج **أيّ** مسار تراجع
#: اسماً هو كلمة مفتاحيّة.
#:
#: **وحدّ صدق على التطبيع:** المقارنة تجري بـ`lower()`، فـ`"Decision_Eligible"` تُطابِق
#: `decision_eligible` — وهما في PostgreSQL **مُعرِّفان مختلفان**. إفراطٌ مقصود في
#: الالتقاط، لا ادّعاء دقّة.
#:
#: **وحدّ صدق ثانٍ، على النظرة نفسها:** لا طفرةَ مُسجَّلة تنزعها وحدها — لأنّ نزعها
#: وحده **لا يُسقِط أيّ اختبار**: مع دعم الاقتباس قائماً لا يوجد مدخلٌ يتراجع إلى كلمة
#: مفتاحيّة (مقيس على خمس صيغ). فهي **دفاعٌ في العمق ضدّ الانحدار المركَّب** — تبيت إن
#: زال دعم الاقتباس يوماً — **لا حارسٌ مُثبَت بالتكذيب**. ومواصفةُ طفرةٍ تمرّ خضراء
#: ليست دليلاً، فلم تُسجَّل.
_COLUMN = rf"(?!(?:column|if|not|exists)\b){_QUOTE}(\w+){_QUOTE}"

#: `ALTER TABLE [IF EXISTS] [ONLY] <snapshot> [*] ADD [COLUMN] [IF NOT EXISTS] <name>`.
#:
#: **الترتيب من قواعد PostgreSQL لا من الحدس** — `ALTER TABLE [ IF EXISTS ] [ ONLY ]
#: name [ * ]`. وصياغتي الثانية عكسَت الاثنين (`only` قبل `if exists`)، فأفلتت الصيغة
#: القانونيّة `ALTER TABLE IF EXISTS ONLY …` **تماماً**: صفر التقاط، لا اسمٌ خاطئ.
#:
#: وقبلها أفلتت `IF NOT EXISTS` بالتقاط `IF` بوصفها اسم العمود — وهي تظهر **٢١ مرّة**
#: في هجرات هذه الخدمة نفسها. **ثقبان متتاليان في نحوٍ واحد**: حارس DDL يُكتَب من
#: القواعد المنشورة، لا من الصيغة التي صادفتُها.
#:
#: **وثالثٌ بقي بعد تصحيح الترتيب:** النجمة الوراثيّة `name [ * ]` جزءٌ من القواعد
#: نفسها، وكانت خارج النمط. وتُقبَل الكلمتان **بأيّ ترتيب** لا بالقانونيّ وحده، لأنّ
#: هذا **كاشف** لا مُحلِّل نحويّ: الإفراط في الالتقاط لا يكلّف شيئاً — SQL غير
#: القانونيّة تفشل في الترحيل على أيّ حال — أمّا التقصير فهو العطل بعينه، صمتٌ
#: يُقرأ «لا عمود محظور هنا» وهو يعني «لم أنظر».
_ALTER_ADD = re.compile(
    rf"alter\s+table\s+(?:(?:if\s+exists|only)\s+){{0,2}}{_QUALIFIED}(?:\s*\*)?"
    rf"\s+add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?{_COLUMN}",
    re.IGNORECASE,
)


def _create_table_body(sql: str) -> str | None:
    """جسم `CREATE TABLE` للقطة — بالأقواس المتوازنة لا بتعبير نمطيّ كسول."""
    match = re.search(
        rf"create\s+table\s+(?:if\s+not\s+exists\s+)?{_QUALIFIED}\s*\(", sql, re.IGNORECASE
    )
    if match is None:
        return None
    depth, start = 0, match.end() - 1
    for index in range(start, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1 : index]
    return None


def _model_body(source: str) -> str | None:
    """جسم صنف النموذج — حتّى أوّل تعريف على مستوى الوحدة بعده."""
    match = re.search(rf"^class\s+{SNAPSHOT_MODEL}\b.*?:$", source, re.MULTILINE)
    if match is None:
        return None
    rest = source[match.end() :]
    end = re.search(r"^(?:class|def|@)\s", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def violations() -> list[str]:
    found: list[str] = []

    source = MODEL_FILE.read_text(encoding="utf-8")
    body = _model_body(source)
    if body is None:
        found.append(
            f"{MODEL_FILE.relative_to(ROOT)} — لم يُعثَر على `{SNAPSHOT_MODEL}`. "
            "حارسٌ لا يجد موضوعه يُبلِغ خضرةً عن سؤال لم يطرحه: صحّح المرساة أو الاسم."
        )
    else:
        for field in FORBIDDEN:
            if re.search(rf"^\s+{field}\s*[:=]", body, re.MULTILINE):
                found.append(
                    f"{MODEL_FILE.relative_to(ROOT)} — `{SNAPSHOT_MODEL}.{field}`: "
                    "حكم أهليّة داخل جسم اللقطة."
                )

    seen_table = False
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)

        table_body = _create_table_body(sql)
        if table_body is not None:
            seen_table = True
            for field in FORBIDDEN:
                # الاقتباس حول اسم العمود داخل التعريف كان تجاوزاً صامتاً: الجسم
                # يُوجَد والحقل يفلت — بخلاف الجدول المقتبس الذي كان يُسقِط الموضوع
                # فيفشل الحارس بصوتٍ عالٍ. الصامت أخطر، لأنّ لا شيء يدلّ عليه.
                if re.search(rf"(^|,|\()\s*{_QUOTE}{field}{_QUOTE}\s", table_body, re.IGNORECASE):
                    found.append(f"{rel} — عمود `{field}` في تعريف `{SNAPSHOT_TABLE}`.")

        for column in _ALTER_ADD.findall(sql):
            if column.lower() in FORBIDDEN:
                found.append(f"{rel} — `ALTER TABLE {SNAPSHOT_TABLE} ADD {column}`.")

    if not seen_table:
        found.append(
            f"لم يُعثَر على `CREATE TABLE {SNAPSHOT_TABLE}` في {MIGRATIONS.relative_to(ROOT)} — "
            "الحارس بلا موضوع، وخضرتُه لا تعني شيئاً."
        )
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="بوّابة CI (الوضع الوحيد)")
    parser.parse_args()

    problems = violations()
    if problems:
        print("اللقطة اكتسبت حكم أهليّة — وهي حقائق مرصودة معنونة بمحتواها:")
        for line in problems:
            print(f"  ✗ {line}")
        print(
            "\nالعلاج — لا تُضِف الحقل ولا تُوسّع الهاش:\n"
            "  الأهليّة كيانٌ مشتقّ في `decision_eligibility_assessments`، مفتاحه\n"
            "  (tenant_id, snapshot_hash, policy_version, as_of) وخارج الهاش تماماً.\n"
            "  انظر services/decision-service/eligibility_policy.py\n"
        )
        return 1

    print(
        f"snapshot_eligibility_separation_guard: PASS "
        f"({SNAPSHOT_MODEL} و{SNAPSHOT_TABLE} خاليان من حكم الأهليّة)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
