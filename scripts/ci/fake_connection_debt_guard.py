#!/usr/bin/env python3
"""راتشِت الدَّين: اختبارٌ على اتّصال وهميّ يدّعي سلوكاً تفرضه القاعدة —
``FAKE-CONNECTION-ENFORCES-NOTHING-01``.

**الحادثة التي أوجبته، لا فرضيّة.** بعد تطبيق ٢٢٦ هجرة على PG16 نظيفة وتشغيل
الرحلة القانونيّة، تعطّلت **أربع مرّات متتالية بأربعة أسباب مختلفة**، كلّ إصلاح يكشف
الذي بعده. وكلّها كانت خضراء سنةً كاملة على وهميّ. أخطرها ``jsonb``: asyncpg يُعيده
**نصّاً** ما لم يُسجَّل codec، والوهميّ يُعيد ``dict`` — فما مرّ في الاختبار انهار حيّاً.

والسجلّ سمّى ما لم يُقَس صراحةً: «**كم اختباراً في هذا المستودع يعتمد على وهميّ لا
يفرض ما تفرضه القاعدة… السطح غير ممسوح**». هذا الملفّ يمسحه.

**ما يقيسه بالضبط:** ملفّات الاختبار التي تُعرّف/تستعمل اتّصالاً أو مسبحاً وهميّاً،
ومنها المجموعة الأخطر: ما يذكر أيضاً دلالةً **تفرضها القاعدة ولا يفرضها الوهميّ**
(``CHECK`` · ``TRIGGER`` · ``UNIQUE``/``ON CONFLICT`` · ``jsonb`` · ``FK``). خضرة هذه
لا تقول شيئاً عن سلوك القاعدة.

**وهو راتشِت لا بوّابة نظافة:** الأساس المُعلَن **يمنع النموّ ولا يدّعي أنّ ما فيه
سليم**. المُدرَجون لم يُثبَت انهيارهم؛ ثبت فقط أنّ خضرتهم لا تُثبِت العكس. وإخراج
ملفّ من الدَّين يكون **بإثباته على قاعدة حيّة**، لا بحذف الكلمة من نصّه.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "architecture" / "fake_connection_debt.json"

# اتّصال/مسبح وهميّ: صنف يُعرَّف أو تجهيزة تُمرَّر. الأسماء مشتقّة من الاصطلاح
# القائم في هذا المستودع (`_FakeConn` · `_FakeTenantConn` · `fake_pool`).
_FAKE = re.compile(r"\b(class\s+_?Fake\w*(Conn|Pool)\w*|fake_conn\w*|fake_pool\w*)\b")

# الحارس واختباره يحويان الرموز **بوصفها موضوعهما** — زرعاتٌ في مستودعات مؤقّتة
# وشرحٌ للحادثة. حارسٌ يُطلِق على توثيق ما يمنعه يُعطَّل في أوّل يوم، وهو عطل تكرّر
# في هذا المستودع (`probe_leak_guard` وقع فيه بعد `#802`) — **ووقعتُ فيه هنا عند أوّل
# تشغيل للمكنسة**: أدرج الأساسُ اختبارَ الحارس ديناً بـCHECK/UNIQUE/jsonb.
# الاستثناء بالمسار لا بالتخمين، ومقصورٌ على الاثنين.
_SELF = {
    "scripts/ci/fake_connection_debt_guard.py",
    "tests_v9/test_fake_connection_debt_guard.py",
}

# دلالات تفرضها القاعدة ولا يفرضها أيّ وهميّ.
_DB_ENFORCED = {
    "CHECK": re.compile(r"\bCHECK\s*\(|\bcheck constraint\b|\bchk_\w+", re.I),
    "TRIGGER": re.compile(r"\bTRIGGER\b|\btrg_\w+", re.I),
    "UNIQUE": re.compile(r"\bUNIQUE\s*\(|\bON CONFLICT\b|\bduplicate key\b", re.I),
    "jsonb": re.compile(r"\bjsonb\b", re.I),
    "FK": re.compile(r"\bREFERENCES\s+\w+|\bforeign key\b", re.I),
}


def _tracked_tests() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "tests_v9", "tests", "services"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln.endswith(".py") and "test" in ln]


def survey(root: Path | None = None) -> dict:
    """يُرجِع المسح: كلّ من يستعمل وهميّاً، ومن يدّعي منهم دلالة قاعدة (مع سببها)."""
    base = root or ROOT
    fake: list[str] = []
    claiming: dict[str, list[str]] = {}
    for rel in _tracked_tests() if base == ROOT else _tracked_in(base):
        if rel in _SELF:
            continue
        path = base / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not _FAKE.search(text):
            continue
        fake.append(rel)
        why = sorted(k for k, rx in _DB_ENFORCED.items() if rx.search(text))
        if why:
            claiming[rel] = why
    return {"fake": sorted(fake), "claiming": dict(sorted(claiming.items()))}


def _tracked_in(base: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"],
        cwd=base,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln.endswith(".py") and "test" in ln]


def _load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _proof_covers(rel: str, entry: dict, claims: list[str]) -> list[str]:
    """هل يُخرِج هذا السداد الملفَّ من الدَّين فعلاً؟ المطلوب ثلاثة، وكلّها مقيسة.

    **لِمَ تُفحَص أصلاً:** المخرج الوحيد المُعلَن من الدَّين هو الإثبات الحيّ، ومدخلٌ
    يُكتَب باليد يستطيع أن يدّعيه بلا أن يفعله. فالمدخل الذي لا يُسمّي ملفَّ إثباتٍ
    قائماً **يذكر مصدره** ليس سداداً بل حذفٌ للكلمة من نصّه — وهو بالضبط ما يمنعه
    سطر العقد في `$comment`.
    """
    bad: list[str] = []
    proof = entry.get("proof", "")
    proof_path = (ROOT / proof).resolve() if proof else None
    if not (proof_path and proof_path.is_relative_to(ROOT) and proof_path.is_file()):
        bad.append(f"✗ {rel} — `proof` لا يُسمّي ملفّاً قائماً: {proof or '—'}")
    elif rel not in proof_path.read_text(encoding="utf-8", errors="ignore"):  # type: ignore[union-attr]
        bad.append(
            f"✗ {rel} — ملفّ الإثبات `{proof}` لا يذكره. الربط يُقاس ولا يُدَّعى: "
            "مدخلٌ يشير إلى إثباتٍ لا يعرف مصدره يُسدّد ديناً لم يُقَس."
        )
    declared_claims = sorted(entry.get("claims", []))
    if declared_claims != sorted(claims):
        bad.append(
            f"✗ {rel} — السداد يغطّي {declared_claims or '—'} والمقيس الآن "
            f"{sorted(claims)}. ادّعاءٌ جديد في ملفّ مُسدَّد يُعيد فتح الدَّين؛ "
            "غطِّه حيّاً ثمّ حدّث `claims`."
        )
    if len((entry.get("evidence") or "").strip()) < 30:
        bad.append(f"✗ {rel} — سدادٌ بلا دليل مكتوب أقصر من تفسير")
    return bad


def check() -> list[str]:
    """يُرجِع المخالفات. النموّ يُدان؛ والانكماش يُطالَب بتحديث الأساس."""
    found = survey()
    declared = _load_baseline()

    if not found["fake"]:
        return [
            "صفر ملفّ مفحوص — الماسح فقد عينه (تغيّر اصطلاح التسمية؟). "
            "أخضرٌ بصفر ليس نظافةً؛ صحّح `_FAKE` أو نطاق `git ls-files`."
        ]

    problems: list[str] = []
    new_fake = sorted(set(found["fake"]) - set(declared["fake_connection_tests"]))
    new_claim = sorted(set(found["claiming"]) - set(declared["claiming_db_enforced"]))
    gone_fake = sorted(set(declared["fake_connection_tests"]) - set(found["fake"]))
    gone_claim = sorted(set(declared["claiming_db_enforced"]) - set(found["claiming"]))

    # السداد الحيّ: ملفّ أُثبِتت **كلّ** ادّعاءاته التي تفرضها القاعدة يخرج من الدَّين
    # وهو ما يزال في `fake_connection_tests` — الوهميّ باقٍ لمنطق التطبيق، والمُسدَّد
    # هو الادّعاء عن القاعدة لا استعمال الوهميّ. وهذا القسم **لا يُشتقّ** بالماسح:
    # النصّ لا يتغيّر بالإثبات، فلا سبيل لاستنتاجه من الشجرة.
    proven = declared.get("proven_live", {})
    for rel, entry in sorted(proven.items()):
        if rel not in found["claiming"]:
            problems.append(
                f"✗ {rel} — سدادٌ لادّعاءٍ لم يعد الماسح يراه. مدخلٌ بائت يُوهِم بتغطية "
                "قائمة؛ احذفه أو أعِد الادّعاء."
            )
            continue
        problems.extend(_proof_covers(rel, entry, found["claiming"][rel]))

    for rel in new_claim:
        if rel in proven:
            continue
        problems.append(
            f"✗ {rel} — اختبارٌ على وهميّ يدّعي سلوكاً تفرضه القاعدة "
            f"({' · '.join(found['claiming'][rel])}). خضرتُه لا تقول شيئاً عن القاعدة. "
            "أثبِته على قاعدة حيّة، أو أعلِنه ديناً صراحةً في الأساس."
        )
    for rel in new_fake:
        if rel in new_claim:
            continue
        problems.append(
            f"✗ {rel} — اتّصال وهميّ جديد خارج الأساس. الدَّين راتشِت لا ينمو؛ أعلِنه إن كان مقصوداً."
        )
    if gone_fake or gone_claim:
        problems.append(
            "✗ الأساس صار أوسع من الواقع — حدّثه بما قِيس: "
            f"غادر الوهميّ {gone_fake or '—'} · غادر الادّعاء {gone_claim or '—'}. "
            "الأساس الذي يُبالغ يُدرَّب قارئه على تجاهله."
        )
    return problems


def _measured_on() -> str:
    """‏SHA الشجرة التي قِيس عليها الأساس — لأنّه **قياس** يَبيت بحركتها لا قرار."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return out.stdout.strip() or "unknown"


def outstanding(found: dict | None = None, declared: dict | None = None) -> dict[str, list[str]]:
    """الدَّين **القائم**: ما مسحه الماسح ناقص ما سُدِّد حيّاً.

    الرقم الذي يُراقَب هو هذا لا `claiming_db_enforced` الخام: الأخير مُشتقّ من النصّ،
    والنصّ لا يتغيّر بالإثبات — فلو رُبِط به الراتشِت لَما نزل أبداً مهما أُثبِت.
    """
    found = found or survey()
    declared = declared or _load_baseline()
    proven = declared.get("proven_live", {})
    return {
        rel: claims
        for rel, claims in found["claiming"].items()
        if sorted(proven.get(rel, {}).get("claims", [])) != sorted(claims)
    }


def _generate() -> None:
    found = survey()
    # `proven_live` قرارٌ مقيس لا مُشتقّ — يُحمَل عبر إعادة التوليد وإلّا محته أوّل
    # `--generate` ورجع الدَّين المُسدَّد صامتاً. (صنف «المصنوع يدهس المكتوب».)
    carried = _load_baseline().get("proven_live", {}) if BASELINE.exists() else {}
    BASELINE.write_text(
        json.dumps(
            {
                "$comment": (
                    "FAKE-CONNECTION-ENFORCES-NOTHING-01 — أساس مُعلَن يمنع النموّ ولا "
                    "يدّعي أنّ ما فيه سليم. `claiming_db_enforced` مسحٌ خام مُشتقّ من "
                    "النصّ، والخروج منه يكون بإثبات الملفّ على قاعدة حيّة لا بحذف الكلمة "
                    "من نصّه — ويُعلَن السداد في `proven_live` (لا يُشتقّ: الإثبات الحيّ "
                    "لا يغيّر النصّ). الدَّين القائم = الأوّل ناقص الثاني، وهو المُراقَب."
                ),
                # مُشتقّ بماسحٍ من الشجرة ⇒ `measured` لا `decided`، فيلزمه أساسٌ
                # يَبيت بحركتها. البيات يُبلَّغ ولا يحجب (سياسة `claim_base_guard`).
                "measured_on": _measured_on(),
                "fake_connection_tests": found["fake"],
                "claiming_db_enforced": found["claiming"],
                "proven_live": carried,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--generate", action="store_true")
    args = ap.parse_args(argv)

    if args.generate:
        _generate()
        print(f"fake_connection_debt: كُتِب الأساس في {BASELINE.relative_to(ROOT)}")
        return 0

    problems = check()
    if problems:
        print("fake_connection_debt_guard FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    declared = _load_baseline()
    # الرقم المطبوع جزءٌ من الحارس: طباعة الخام وحده تقول «٨ ديون» بعد سدادها كلّها،
    # فتُدرِّب القارئ على تجاهُل العدّاد. الثلاثة تُطبَع كي يُقرأ السداد لا يُستنتَج.
    raw = len(declared["claiming_db_enforced"])
    paid = len(declared.get("proven_live", {}))
    print(
        "fake_connection_debt_guard_ok "
        f"(وهميّ: {len(declared['fake_connection_tests'])} · "
        f"يدّعي سلوك قاعدة: {raw} خاماً − {paid} مُسدَّداً حيّاً "
        f"⇒ {len(outstanding(declared=declared))} ديناً قائماً)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
