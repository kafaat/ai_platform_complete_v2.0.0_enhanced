#!/usr/bin/env python3
"""`TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01` — اسمُ مُتغيّر المستأجِر واحدٌ أو معدود.

عزلُ المستأجِر في هذا المستودع مبنيٌّ على `current_setting('app.<اسم>')` داخل سياسات
RLS. **والاسمُ ليس واحداً**: ثلاثُ عائلاتٍ من السياسات تقرأ ثلاثةَ أسماءٍ مختلفة،
ومَن يضبط أحدَها لا يُرى له الآخر.

**وشكلُ الفشل صامتٌ لا حاجب** — وهذا ما يجعله يستحقّ حارساً:

    السياسة تقرأ  app.tenant_id
    الشيفرة تضبط  app.current_tenant
    ⇒ current_setting('app.tenant_id', true) = NULL
    ⇒ USING (tenant_id::text = NULL) = NULL ⇒ صفرُ صفوف

لا استثناءَ يُرفَع، ولا سطرَ يُسجَّل، ولا رمزَ خروجٍ يتغيّر. **جوابٌ ناقصٌ يُقرَأ
كاملاً** — وهو أخطرُ من ٥٠٣ صريحة في أيّ مسارِ قراءة.

**والانحرافُ يُدفَع ثمنُه الآن بترقيعٍ صامت:** `phase_runtime_workers.py::_set_tenant`
يضبط **اسمين معاً** في سطرين متتاليين، بلا سطرٍ يقول لماذا. فالحلُّ قائمٌ في موضعٍ
واحد ومفقودٌ في سواه — وهو تعريفُ الدَّين لا تعريفُ العلاج.

## ما يقيسه هذا الحارس، وما لا يقيسه

**يقيس ثلاثاً:**

* **تساوي المجموعات لا العدّادات.** مجموعةُ أسماء المستأجِر في `migrations/` تُقارَن
  بمجموعةٍ مُجمَّدة. عدّادٌ ثابت يمرّ حين يُضاف اسمٌ ويُحذَف آخر — وهو بالضبط شكلُ
  الانحراف الذي نحرسه.
* **كلُّ اسمٍ تقرؤه سياسةٌ يضبطه مسارٌ في الشيفرة.** اسمٌ بلا ضابطٍ يعني جدولاً
  **لا يُقرَأ منه شيءٌ أبداً** في كلّ مسارٍ حيّ — صفرُ صفوفٍ دائم بلا شكوى.
* **راتشِتٌ نازل.** السقفُ يُخفَّض عند كلّ توحيد ولا يُرفَع. رفعُه لتمرير اسمٍ رابع
  يُبطِل الحارسَ لا يُرضيه.

**ولا يقيس — بالقصد:**

* **أسماءَ غيرِ المستأجِر** (`app.current_role` · `app.current_user_id`). انحرافُها
  عطلُ تفويضٍ لا عطلُ عزلٍ بين المستأجرين، وصنفٌ آخر بأثرٍ آخر. وإدخالُها هنا كان
  يُوسِّع الادّعاءَ فوق الدليل الذي قِيس.
* **`app.managed_roles` · `app.bypassrls_allowed`** — قِيسا فوُجِدا **ليسا في سياسةٍ
  أصلاً**، بل في تأكيدٍ داخل `apply_in_compose.sh` يضبطهما السكربتُ نفسُه بـ`-v`.
  فاستبعادُهما اشتقاقٌ لا إعفاء: لا يُطابِقان `app.*tenant*`.
* **صحّةَ السياسة نفسِها.** أنّ الاسم مضبوطٌ لا يعني أنّ العزل صحيح — يقيسه
  `rls_policy_guard` وجناحُ RLS التكامليّ.

    python scripts/ci/tenant_guc_name_convergence_guard.py
    python scripts/ci/tenant_guc_name_convergence_guard.py --json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة — فتحت `LC_ALL=C` يحسب صحيحاً ثمّ يموت وهو يطبع نجاحَه.
# **عند التحميل لا داخل `main()`**: الحارسُ يُستورَد في اختباره وتُستدعى دوالُّه
# مباشرةً، فعلاجٌ في `main()` يترك المسارَ المُستورَد مكشوفاً.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"

#: مواضعُ ضبطِ المُتغيّر — شيفرةُ التطبيق والخدمات والاختبارات.
SETTER_TREES = ("services", "shared", "scripts", "tests_v9", "tests", "migrations")

_READ = re.compile(r"current_setting\(\s*['\"](app\.[a-z0-9_]+)['\"]")
_SET = re.compile(r"set_config\(\s*['\"](app\.[a-z0-9_]+)['\"]")

#: نطاقُ الحارس **مُشتقٌّ لا مكتوب**: كلُّ اسمٍ يحمل `tenant`. فاسمٌ رابعٌ يدخل
#: النطاقَ بمجرّد كتابته، ولا ينتظر أحداً ليُدرِجه في قائمة.
_TENANT_SCOPED = re.compile(r"^app\.[a-z0-9_]*tenant[a-z0-9_]*$")

#: المجموعةُ المقيسة على `99000487`. **هويّاتٌ لا عدد** — عدّادٌ ثابت يمرّ حين
#: يُضاف اسمٌ ويُزال آخر.
EXPECTED_NAMES = frozenset(
    {
        "app.current_tenant",
        "app.tenant_id",
        "app.current_tenant_id",
    }
)

#: راتشِت: يُخفَّض عند كلّ توحيد ولا يُرفَع.
NAME_CEILING = 3


def _sql_text() -> dict[str, str]:
    """نصُّ كلّ هجرة. `errors="ignore"` مرفوض: ملفٌّ لا يُقرَأ ليس ملفّاً بلا أسماء."""
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(MIGRATIONS.rglob("*.sql"))
    }


def tenant_names_read() -> dict[str, list[str]]:
    """اسمُ المستأجِر ⇒ الهجراتُ التي تقرؤه.

    والقراءةُ من نصّ الهجرة كلِّه لا من متن ``CREATE POLICY`` وحده — عمداً: ثلاثُ
    عائلاتٍ هنا تُنشئ سياساتِها **ديناميكيّاً** داخل ``format()`` في كتلة ``DO``
    (`_sahool_apply_tenant_rls` · `v161` · `v162`)، فمُستخرِجٌ يقرأ العبارةَ
    الساكنة وحدَها كان يفوته أوسعُ عائلةٍ في الشجرة.
    """
    found: dict[str, list[str]] = {}
    for rel, text in _sql_text().items():
        for name in set(_READ.findall(text)):
            if _TENANT_SCOPED.match(name):
                found.setdefault(name, []).append(rel)
    return {name: sorted(files) for name, files in sorted(found.items())}


def setter_counts() -> dict[str, int]:
    """اسمُ المستأجِر ⇒ عددُ مواضع ``set_config`` التي تضبطه في الشجرة."""
    counts: dict[str, int] = {}
    for tree in SETTER_TREES:
        base = ROOT / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".sql", ".sh"}:
                continue
            if "__pycache__" in path.as_posix():
                continue
            for name in _SET.findall(path.read_text(encoding="utf-8", errors="replace")):
                if _TENANT_SCOPED.match(name):
                    counts[name] = counts.get(name, 0) + 1
    return counts


def audit() -> dict:
    read = tenant_names_read()
    setters = setter_counts()
    names = set(read)
    return {
        "names": sorted(names),
        "read": {name: len(files) for name, files in read.items()},
        "setters": {name: setters.get(name, 0) for name in sorted(names)},
        "unset": sorted(name for name in names if setters.get(name, 0) == 0),
        "new": sorted(names - EXPECTED_NAMES),
        "retired": sorted(EXPECTED_NAMES - names),
        "ceiling": NAME_CEILING,
    }


def failures(report: dict) -> list[str]:
    """أسبابُ الحجب. الفارغةُ تعني مروراً."""
    out: list[str] = []
    if not report["names"]:
        out.append(
            "صفرُ اسمِ مستأجِرٍ مكتشَفٍ في `migrations/` — والمستودعُ يحمل مئاتِ السياسات."
            "\n  قراءةٌ صفريّة تمرّ خضراء عن سؤالٍ لم تطرحه، وهي أخطرُ من انحرافٍ مُبلَّغ."
        )
        return out
    if report["new"]:
        out.append(
            f"اسمُ مستأجِرٍ جديد في سياسات RLS: {report['new']}."
            "\n  وشكلُ فشله صامت: مَن يضبط الاسمَ الشائع يقرأ صفرَ صفوفٍ بلا خطأ."
            "\n  وحّده مع اسمٍ قائم، أو اخفض السقفَ وأدرِجه إن كان توحيدُه مرحلةً."
        )
    if report["unset"]:
        out.append(
            f"اسمٌ تقرؤه سياسةٌ ولا يضبطه أيُّ مسار: {report['unset']}."
            "\n  الجداولُ المحكومة به تُعيد صفرَ صفوفٍ في كلّ مسارٍ حيّ — دائماً وصامتاً."
        )
    if len(report["names"]) > report["ceiling"]:
        out.append(
            f"عددُ الأسماء {len(report['names'])} فوق السقف {report['ceiling']} —"
            "\n  الراتشِت ينزل ولا يصعد؛ ورفعُه لتمرير اسمٍ رابع يُبطِل الحارس لا يُرضيه."
        )
    return out


def main() -> int:
    report = audit()
    if "--json" in sys.argv[1:]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    reasons = failures(report)
    if reasons:
        print("tenant_guc_name_convergence_guard: FAIL")
        for reason in reasons:
            print(f"  ✗ {reason}")
        return 1
    detail = " · ".join(
        f"{name}: {report['read'][name]} هجرة / {report['setters'][name]} ضابط"
        for name in report["names"]
    )
    print(f"tenant_guc_name_convergence_guard_ok — {len(report['names'])} أسماء · {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
