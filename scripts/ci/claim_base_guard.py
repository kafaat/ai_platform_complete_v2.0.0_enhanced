#!/usr/bin/env python3
"""كلّ ادّعاء يحمل أساسه — CLAIMS-WITHOUT-A-MEASURED-BASE-01.

مصنوعات `docs/architecture/` صنفان لا واحد، ولكلٍّ ختمٌ مختلف:

* **قياس** — عدد أو مجموعة اشتقّها ماسحٌ من شجرةٍ في لحظة. يَبيت حين تتحرّك الشجرة
  تحته، فيلزمه ``measured_on``: أيّ شجرةٍ قِيس عليها.
* **قرار** — حكمٌ اتّخذه إنسان. لا يَبيت بحركة الشجرة بل بتغيّر أسبابه، فيلزمه
  ``adjudicated_on``: متى حُكِم.

**والخلط بينهما هو العطل، لا غياب الختم:** رقمٌ مقيس يُقرأ عقداً فلا يُعاد قياسه
أبداً — و`platform_extraction_map.json` يقول اليوم `baseline_route_count = 633`
بينما قائمة `routes` فيه تعدّ **635**، ولا حارس ولا اختبار ولا workflow يقرأ ذلك
الحقل إطلاقاً. رقمٌ منشور بوصفه واقعاً، انحرف عن القائمة التي يعدّها، بلا أساس
يُقاس عليه وبلا قارئ يكشفه.

**والمفردتان ليستا اختراعاً هنا:** أربع مصنوعات تحمل ``measured_on`` وأربع تحمل
``adjudicated_on``، اختارها كاتبوها كلٌّ على حدة ولم تُسمَّ قاعدةً قطّ. هذا الحارس
يُسمّي القائم ويقيس تغطيته.

**ما يُحجَب وما يُبلَّغ — والفرق مقصود:** يُحجَب غياب الأساس (ملفّ غير مصنَّف · قياس
بلا ختم خارج قائمة الدَّين · نموّ الدَّين · مدخل دَين بائت). ويُبلَّغ **البيات** ولا
يُحجَب عليه: الحجب على تقادم رقمٍ يُحوّل كلّ PR إلى حملة إعادة قياس، ويُدرّب قارئه
على تجاهل الحارس — وهو أشيع أعطال الحرّاس.

    python scripts/ci/claim_base_guard.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs" / "architecture"
REGISTRY = ARCH / "claim_base_registry.json"

# ختمٌ يحمل معرّف شجرة: أوّل رمز hex بطول ٧..٤٠ داخل نصّ الختم الحرّ.
_HEX = "0123456789abcdef"


def load_registry(path: Path = REGISTRY) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def declared_artifacts(arch: Path = ARCH) -> list[str]:
    return sorted(p.name for p in arch.glob("*.json"))


def _has_base(data: dict, keys: list[str]) -> bool:
    """مطابقة **تامّة** للمفتاح. `baseline_route_count` عدٌّ لا أساس."""
    return any(k in data and str(data[k]).strip() for k in keys)


def extract_sha(stamp: str) -> str | None:
    """أوّل رمز شجرة في ختمٍ حرّ الصياغة. ما لا يُشبِه SHA لا يُخمَّن."""
    token = ""
    for ch in stamp + " ":
        if ch.lower() in _HEX:
            token += ch
            continue
        if 7 <= len(token) <= 40 and any(c.isdigit() for c in token):
            return token
        token = ""
    return None


def commits_since(sha: str, root: Path = ROOT) -> int | None:
    """بُعد الختم عن HEAD. ``None`` إن كان الرمز غير معروف لهذه الشجرة."""
    res = subprocess.run(
        ["git", "rev-list", "--count", f"{sha}..HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=root,
    )
    if res.returncode != 0:
        return None
    try:
        return int(res.stdout.strip())
    except ValueError:
        return None


def check(registry: dict, arch: Path = ARCH) -> list[str]:
    """يُرجِع أسباب الحجب. الفارغة تعني مروراً."""
    failures: list[str] = []
    measured = set(registry["measured"])
    decided = set(registry["decided"])
    m_keys = registry["measured_base_keys"]
    d_keys = registry["decided_base_keys"]
    unbased = {k for k in registry["unbased_debt"] if not k.startswith("$")}
    undated = {k for k in registry["undated_debt"] if not k.startswith("$")}

    present = set(declared_artifacts(arch))

    overlap = measured & decided
    if overlap:
        failures.append(f"مصنَّفة قياساً وقراراً معاً — والصنفان متنافيان: {sorted(overlap)}")

    unclassified = present - measured - decided
    if unclassified:
        failures.append(
            "مصنوعة في docs/architecture/ غير مصنَّفة: "
            f"{sorted(unclassified)}\n"
            "  صنّفها في claim_base_registry.json: `measured` إن كان محتواها مُشتقّاً\n"
            "  بماسحٍ من شجرة (فيلزمه `measured_on`)، أو `decided` إن كان حكماً\n"
            "  اتّخذه إنسان (فيلزمه `adjudicated_on`). والفرق ليس أسلوبيّاً: القياس\n"
            "  يَبيت بحركة الشجرة والقرار لا يَبيت بها."
        )

    ghost = (measured | decided) - present
    if ghost:
        failures.append(f"مصنَّفة في السجلّ ولا وجود لها على القرص: {sorted(ghost)}")

    for name in sorted(measured & present):
        data = json.loads((arch / name).read_text(encoding="utf-8"))
        has = _has_base(data, m_keys)
        if has and name in unbased:
            failures.append(
                f"{name}: اكتسب ختم أساس وما زال في `unbased_debt` — احذفه منها."
                "\n  (إنفاذ عكسيّ: قائمة دَين لا تتقلّص تُطيل نفسها بمداخل بائتة.)"
            )
        elif not has and name not in unbased:
            failures.append(
                f"{name}: قياس بلا أساس. أضِف {m_keys[0]!r} يذكر الشجرة التي قِيس"
                "\n  عليها — أو أعلِنه ديناً في `unbased_debt` بسببٍ مكتوب."
            )

    for name in sorted(decided & present):
        data = json.loads((arch / name).read_text(encoding="utf-8"))
        has = _has_base(data, d_keys)
        if has and name in undated:
            failures.append(f"{name}: اكتسب تاريخ حكم وما زال في `undated_debt` — احذفه منها.")
        elif not has and name not in undated:
            failures.append(
                f"{name}: قرار بلا تاريخ حكم. أضِف {d_keys[0]!r} أو أعلِنه في `undated_debt`."
            )

    for label, debt in (("unbased_debt", unbased), ("undated_debt", undated)):
        gone = debt - present
        if gone:
            failures.append(f"{label}: مدخل بائت لمصنوعة غير موجودة: {sorted(gone)}")
        ceiling = registry[f"{label}_ceiling"]
        if len(debt) > ceiling:
            failures.append(
                f"{label}: {len(debt)} مدخلاً والسقف {ceiling}. قائمة دَين بلا سقف"
                "\n  لا تمنع النموّ — يكفي أن يُضاف إليها المدخل الجديد. ومصنوعةٌ"
                "\n  أُنشئت اليوم لا عذر لها: من قاس يعرف على أيّ شجرة قاس."
            )

    return failures


def report_staleness(registry: dict, arch: Path = ARCH, root: Path = ROOT) -> None:
    """عمر كلّ قياس مؤرَّخ. **يُطبَع ولا يُحجَب** — انظر docstring الوحدة."""
    m_keys = registry["measured_base_keys"]
    for name in sorted(registry["measured"]):
        f = arch / name
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        stamp = next((str(data[k]) for k in m_keys if k in data), None)
        if not stamp:
            print(f"  ○ {name}: بلا أساس (دَين مُعلَن)")
            continue
        sha = extract_sha(stamp)
        distance = commits_since(sha, root) if sha else None
        if distance is None:
            print(f"  · {name}: أساس غير قابل للحلّ في هذه الشجرة — {stamp[:60]}")
        else:
            print(f"  · {name}: قِيس على {sha} — {distance} التزاماً قبل HEAD")


def main() -> int:
    registry = load_registry()
    failures = check(registry)
    print("claim_base_guard: عمر القياسات (تقرير، لا حجب)")
    report_staleness(registry)
    if failures:
        print("\nclaim_base_guard: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        return 1
    print("\nclaim_base_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
