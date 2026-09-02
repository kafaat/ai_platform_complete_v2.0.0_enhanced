#!/usr/bin/env python3
"""Print the current status of the production certification blockers.

This script is intentionally read-only. It does not promote certification and
it does not convert local/sandbox checks into deployment evidence.

**والحكمُ هنا لا يُكتَب — يُفوَّض.** كان هذا الملفُّ يحمل قائمةَ حواجزَ ثانيةً
وحكماً ثانياً، وكلاهما أضعفُ من الحارس الصارم القائم:

* قائمتُه أربعةُ حواجز، وقائمةُ `production_evidence_pack_guard` **خمسة** —
  الخامسُ `GUARDS` مُدرَجٌ هناك في `non_waivable_blockers` وغائبٌ هنا. أي أنّ
  حاجباً كاملاً لم يكن يُقيَّم أصلاً، لا لأنّه غيرُ معرَّفٍ بل لأنّ القائمتين
  اختلفتا.
* وحكمُه كان `row["status"] == "verified"` — مقارنةَ سلسلةٍ لا غير: لا بصمةَ
  تُفحَص، ولا مستودعَ ولا workflow يُطابَق، ولا سببَ إعفاءٍ يُقرأ.

**ومُكذَّبٌ بالتنفيذ لا موصوف:** في رملٍ معزول (`EVIDENCE_DIR` مُوجَّهٌ إلى دليلٍ
مؤقّت) أنتجت **أربعةُ ملفّات JSON مكتوبةٍ باليد** `production_certified=true`
وخروجاً `0` — ببصمةٍ من أربعين صفراً، و`repository: attacker/x`، وقوائمَ فارغة،
وإعفاءٍ **بلا حقل سببٍ أصلاً**؛ والكلمةُ «سبب» كانت في **اسم الحالة**
(`waived_with_reason`) لا في البيانات.

فصار المصدرُ واحداً: القائمةُ تُستورَد، والتحقّقُ يُفوَّض إلى `check_files()`،
ولا يُعلَن اعتمادٌ إلّا بعد مروره. **وحكمان لحقيقةٍ واحدة ينحرفان — وهذان لم
يكونا متّفقَين أصلاً.**

**حدُّ صدقٍ مُعلَن:** هذا يمنع التزييفَ **الأسهل** (ملفّاتٌ مكتوبةٌ باليد بقيمٍ
شكليّة). ولا يُثبت أنّ الدليلَ صادرٌ عن تشغيلٍ حقيقيّ — ذاك يحتاج attestation
موقَّعة، وهي مُسجَّلةٌ ديناً مفتوحاً في
`PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"
_GUARD = Path(__file__).resolve().parent / "production_evidence_pack_guard.py"


def _evidence_guard():
    """المصدرُ الواحد للحواجز وللتحقّق — يُستورَد ولا يُنسَخ.

    نسخُ القائمة هنا هو بعينه العطلُ الذي أُغلِق: قائمتان تختلفان بلا أن يذكر
    أحدُهما الآخر.
    """
    spec = importlib.util.spec_from_file_location("_production_evidence_pack_guard", _GUARD)
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit("cannot load production_evidence_pack_guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "timestamp_utc": None}
    return json.loads(path.read_text(encoding="utf-8"))


def main(*, require_certified: bool = False) -> int:
    guard = _evidence_guard()

    rows = []
    for item in guard.BLOCKERS:
        payload = _load(EVIDENCE_DIR / item["required_file"])
        rows.append(
            {
                "blocker_id": item["id"],
                "name": item["name"],
                "status": payload.get("status", "unknown"),
                "waivable": item["waivable"],
                "file": f"certification/evidence/{item['required_file']}",
                "timestamp_utc": payload.get("timestamp_utc"),
            }
        )

    # **البوّابةُ الصارمة تسبق الحكم.** حالةٌ تقول `verified` بلا بصمةٍ صالحة أو
    # بمستودعٍ لا يطابق البيئة، أو إعفاءٌ بلا شروطه الخمسة ⇒ لا اعتماد.
    # وسببُ المنع يُطبَع، فلا يُقرأ الرفضُ عطلاً في الأداة.
    # **ويُكتَم مخرَجُ الحارس عمداً:** ينجح بطباعة `production_evidence_pack_check_ok`
    # إلى `stdout`، ومخرَجُ هذا الملفّ **JSON آليّ**. تركُها يُفسِد كلَّ مُحلِّلٍ يقرؤه —
    # مقيسٌ: أوّلُ مِسبارٍ لي سقط بـ`JSONDecodeError` على هذا بالذات.
    evidence_error: str | None = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            guard.check_files()
    except SystemExit as exc:
        evidence_error = str(exc) or "evidence pack check failed"

    states_ok = all(
        row["status"] == "verified" or (row["waivable"] and row["status"] == "waived_with_reason")
        for row in rows
    )
    certified = states_ok and evidence_error is None

    print(
        json.dumps(
            {
                "production_certified": certified,
                "evidence_pack_ok": evidence_error is None,
                "evidence_pack_error": evidence_error,
                "blockers": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if certified or not require_certified:
        return 0
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-certified",
        action="store_true",
        help="exit non-zero while any non-waived production blocker is pending",
    )
    args = parser.parse_args()
    raise SystemExit(main(require_certified=args.require_certified))
