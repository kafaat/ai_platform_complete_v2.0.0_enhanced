#!/usr/bin/env python3
"""يكتب ملفَّ دليلِ حاجبٍ واحدٍ **من بيئة التشغيل**، لا من وسائطِ المُنادي.

`PRODUCTION-CERTIFICATION-EVIDENCE-IS-NEVER-EMITTED-01`.

**العطلُ مُكذَّبٌ بالتنفيذ لا موصوف.** `production-certification-blockers.yml` يحمل
أربعَ وظائفِ «دليل» ووظيفةَ حكمٍ تعتمد عليها كلِّها — و**لا واحدةَ منها تكتب دليلاً**.
كلُّ وظيفةٍ تستنسخ الشجرة، تُشغّل فحصَها، ثمّ تطبع حالةَ الملفّات **المودَعة** كما هي.
المقيس على الشجرة الحاليّة: خمسةُ حواجزَ كلُّها `pending`، و`--require-certified`
يُخرِج `1`. فالوظائفُ لا تُنتِج ما يقرؤه المُحكِّم، والمُحكِّم يقرأ نائباتٍ مودَعة.

أي أنّ الاعتمادَ لم يكن **صعباً**؛ كان **مستحيلاً** — وهذا صنفٌ آخر: بوّابةٌ لا تُغلَق
بعملٍ صحيح تُقرأ بمرور الوقت دعوةً إلى تزييفِ مُدخَلها بدل إصلاح مُنتِجه.

## لمَ الوراثةُ من البيئة شرطٌ لا تفصيل

`production_evidence_pack_guard._check_provenance` يطابق `repository` و`workflow`
بـ`GITHUB_REPOSITORY` و`GITHUB_WORKFLOW` **حين تتوفّران**. فلو قَبِل هذا الباعث
`--repository` وسيطاً لَصار أداةَ تلفيقٍ جاهزة: يكفي تمريرُ القيمة المطابقة. فالوسائط
تحمل **قياسَ الحاجب** وحدَه، والهويّةُ تُقرأ من البيئة ولا تُمرَّر قطّ.

## حدُّ صدقٍ مُعلَن — ما لا يُثبِته هذا الملفّ

يمنع هذا: (١) اختلاقَ الهويّة عبر الوسائط، (٢) دليلاً ينقصه حقلٌ يشترطه الحارس
(يُتحقَّق هنا فيسقط في الوظيفة التي تملك السبب لا في المُحكِّم بعد خطوتين)، (٣)
انبعاثاً بعد فشلِ القياس — لأنّ خطوةَ GitHub Actions لا تُنفَّذ إن سقطت سابقتُها،
فالخطوةُ **غيرُ قابلةٍ للبلوغ** ما لم يمرّ القياس.

ولا يمنع: كتابةَ الملفّ بيدٍ خارج هذا الباعث أصلاً. ذاك يقطعه شيئان لا هو:
مطابقةُ البيئة عند الفحص، و**التوقيعُ الشهاديّ** (`actions/attest`) الذي يربط
البايتات بهويّةِ الـworkflow عبر Sigstore — وهي هويّةٌ لا يملك مؤلّفُ الشجرة
إصدارَها. مُسجَّلٌ في
`PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01`.

يعمل بلا pytest — نفس نمط `platform_route_placement_guard`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"
_GUARD = Path(__file__).resolve().parent / "production_evidence_pack_guard.py"

#: حقولٌ تُقرأ من البيئة حصراً. تمريرُ أيٍّ منها وسيطاً يُرفَض — لا يُتجاهَل بصمت،
#: لأنّ التجاهلَ الصامت يجعل محاولةَ التلفيق تبدو ناجحة.
_PROVENANCE_FIELDS = ("repository", "workflow", "workflow_run_id", "commit")

#: ما لا يملك المُنادي ضبطَه بحال: الحالةُ يحدّدها بلوغُ الخطوة، والوقتُ ساعةُ العدّاء.
_RESERVED_FIELDS = (*_PROVENANCE_FIELDS, "status", "timestamp_utc")

#: البيئة ⇒ حقل الأصل. غيابُ أيٍّ منها ⇒ لسنا في عدّاء GitHub Actions ⇒ لا انبعاث.
_ENV_TO_FIELD = {
    "GITHUB_REPOSITORY": "repository",
    "GITHUB_WORKFLOW": "workflow",
    "GITHUB_RUN_ID": "workflow_run_id",
    "GITHUB_SHA": "commit",
}


def _blockers() -> list[dict]:
    """قائمةُ الحواجز تُستورَد من الحارس ولا تُنسَخ.

    نسخُها هنا هو بعينه العطلُ الذي أُغلِق في `production_certification_blockers_status`:
    قائمتان تختلفان بلا أن يذكر أحدُهما الآخر، فيسقط حاجبٌ كاملٌ من التقييم صامتاً.
    """
    spec = importlib.util.spec_from_file_location("_production_evidence_pack_guard", _GUARD)
    if not spec or not spec.loader:  # pragma: no cover - بيئةٌ مكسورة
        raise SystemExit("cannot load production_evidence_pack_guard")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.BLOCKERS)


def provenance(env: dict[str, str] | None = None) -> dict[str, str]:
    """يقرأ الأصلَ من البيئة، أو يسقط مُسمّياً المتغيّرَ الغائب بعينه."""
    source = os.environ if env is None else env
    values: dict[str, str] = {}
    missing: list[str] = []
    for var, field in _ENV_TO_FIELD.items():
        value = str(source.get(var) or "").strip()
        if not value:
            missing.append(var)
        else:
            values[field] = value
    if missing:
        raise SystemExit(
            "لا انبعاثَ خارج عدّاء GitHub Actions — متغيّراتُ الأصل الغائبة: "
            + ", ".join(sorted(missing))
            + "\nالأصلُ يُورَث من البيئة ولا يُمرَّر وسيطاً؛ ولو مُرِّر لَصار هذا الباعث "
            "أداةَ تلفيقٍ جاهزة."
        )
    return values


def _reject_reserved(fields: dict[str, object]) -> dict[str, object]:
    reserved = sorted(set(fields) & set(_RESERVED_FIELDS))
    if reserved:
        raise SystemExit(
            f"حقولٌ محجوزة: {', '.join(reserved)} — تُقرأ من البيئة أو من بلوغ الخطوة، "
            "ولا تُمرَّر مُدخَلاً."
        )
    return fields


def fields_from_file(path: Path) -> dict[str, object]:
    """حقولُ قياسٍ يكتبها جامعٌ سابق — لا تختصر شرطَ الحجز.

    الحاجةُ إليه ميكانيكيّة: `jobs` قائمةُ كائنات، ونقلُها عبر وسيطِ صدفةٍ مُقتبَسٍ
    يدويّاً يكسرها عند أوّل اقتباسٍ داخليّ. والحجزُ يُطبَّق هنا حرفيّاً كما على
    الوسائط: مصدرُ الحقول لا يغيّر ما يملك المُنادي ضبطَه.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"تعذّرت قراءةُ حقول القياس من {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path}: يجب أن يكون كائنَ JSON من حقولِ قياس")
    return _reject_reserved(payload)


def _parse_assignments(raw: list[str], *, as_json: bool) -> dict[str, object]:
    fields: dict[str, object] = {}
    for entry in raw:
        if "=" not in entry:
            raise SystemExit(f"صيغةُ الحقل يجب أن تكون key=value — ورد: {entry!r}")
        key, _, value = entry.partition("=")
        key = key.strip()
        if key in _RESERVED_FIELDS:
            raise SystemExit(
                f"الحقل {key!r} محجوز: يُقرأ من البيئة أو من بلوغ الخطوة، ولا يُمرَّر وسيطاً."
            )
        if not as_json:
            fields[key] = value
            continue
        try:
            fields[key] = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"قيمةُ --json-field {key!r} ليست JSON صالحاً: {exc}") from exc
    return fields


def build(blocker_id: str, fields: dict[str, object], *, env: dict[str, str] | None = None) -> dict:
    """يبني الحمولةَ ويتحقّق من اكتمالها **قبل** كتابتها.

    التحقّقُ هنا لا في المُحكِّم قصدٌ: الوظيفةُ التي تملك سببَ النقص هي التي تسقط به،
    بدل رفضٍ بعد خطوتين في وظيفةٍ لا تعرف ما الذي لم يُقَس.
    """
    item = next((b for b in _blockers() if b["id"] == blocker_id), None)
    if item is None:
        known = ", ".join(sorted(b["id"] for b in _blockers()))
        raise SystemExit(f"حاجبٌ غيرُ معروف: {blocker_id!r} — المعروفة: {known}")

    payload: dict[str, object] = {
        "blocker_id": item["id"],
        "name": item["name"],
        "status": "verified",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        **provenance(env),
        **fields,
    }

    # `_is_substantive` لا `in`: قائمةٌ فارغةٌ أو `null` تُرضي فحصَ الحضور — وهو
    # المتّجه الذي مرّ به الدليلُ المُلفَّق في تكذيب `production_evidence_pack_guard`.
    empty = [f for f in item["minimum_fields"] if not _substantive(payload.get(f))]
    if empty:
        raise SystemExit(
            f"{item['id']}: حقولٌ يشترطها الحارس ناقصةٌ أو خاوية: {', '.join(empty)}\n"
            "مرِّرها بـ--field/--json-field من قياسٍ حقيقيّ — ولا تُملأ بقيمٍ شكليّة."
        )
    return payload


def _substantive(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) > 0
    return True


def emit(blocker_id: str, fields: dict[str, object], out_dir: Path) -> Path:
    # `build` أوّلاً لا البحثُ عن الملفّ: الترتيبُ المعكوس كان يُخرِج `AssertionError`
    # عارياً على حاجبٍ مجهول بدل رسالة `build` التي تُسمّي المعروف. مقيسٌ في التكذيب —
    # ورسالةٌ مفهومةٌ في الوظيفة التي تملك السبب هي نصفُ فائدة هذا الملفّ.
    payload = build(blocker_id, fields)
    item = next(b for b in _blockers() if b["id"] == blocker_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / item["required_file"]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def purge(out_dir: Path) -> list[Path]:
    """يمسح ملفّاتِ الحواجز من الاستنساخ **قبل** جلب مصنوعات هذا العدّاء.

    **وبدونه يبقى أسهلُ تزييفٍ مفتوحاً:** المُحكِّم يستنسخ الشجرة ثمّ يقرأ
    `certification/evidence/`. فملفٌّ `verified` **مودَعٌ في الشجرة** بقيمِ أصلٍ
    مطابقةٍ للبيئة (وهي قيمٌ عامّةٌ يعرفها أيُّ مؤلّف) يمرّ بلا أن تُنتِجه وظيفةٌ
    واحدة — أي أنّ كلّ ما بُني أعلاه يُلتَفُّ عليه بـ`git add`.

    فالقاعدة: **لا يُعتَدّ إلّا بما أنتجه هذا العدّاء.** ما يبقى بعد المسح ولم تجلبه
    مصنوعةٌ يُعاد بناؤه نائبةً `pending` بـ`--write`، فيسقط الحكم — فشلٌ مغلقٌ لا
    قبولٌ صامت.

    ويمسح **قائمةَ الحارس** لا كلَّ ما في المجلَّد: فيه ملفّاتُ أدلّةٍ أخرى
    (`certify_run_*`, `unified_readiness_summary`) لا يقرؤها هذا الحكم، ومسحُها
    توسيعٌ للأثر بلا سبب.
    """
    removed: list[Path] = []
    for item in _blockers():
        path = out_dir / item["required_file"]
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--purge",
        action="store_true",
        help="امسح ملفّاتِ الحواجز من الاستنساخ (يُستعمَل في وظيفة الحكم قبل الجلب)",
    )
    parser.add_argument("--blocker", help="معرّف الحاجب (P-CERT-1 …)")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="حقلُ قياسٍ نصّيّ",
    )
    parser.add_argument(
        "--json-field",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="حقلُ قياسٍ مُهيكَل (قائمة/كائن/منطقيّ)",
    )
    parser.add_argument(
        "--fields-file",
        default=None,
        metavar="PATH",
        help="كائنُ JSON من حقول القياس (يكتبه جامعٌ سابق)",
    )
    parser.add_argument(
        "--skip-outside-ci",
        action="store_true",
        help=(
            "خارج عدّاء Actions: أعلِن التخطّي بصوتٍ عالٍ وأخرُج بـ0 بدل السقوط "
            "(لسكربتٍ عملُه الأصليّ مشروعٌ محليّاً وانبعاثُ الدليل ثانويّ فيه)"
        ),
    )
    parser.add_argument("--out", default=str(EVIDENCE_DIR), help="مجلَّد الإخراج")
    args = parser.parse_args(argv)

    # **شرطُ «أنا في CI» يبقى تعريفاً واحداً.** البديلُ أن يفحص كلُّ مُنادٍ متغيّراتِ
    # البيئة في صدفته، فيصير لدينا شرطان يتّفقان اليوم — الصنفُ الذي أسقط قائمتَي
    # الحواجز. الفحصُ هنا، والرايةُ تختار **السلوكَ عند الغياب** لا التعريف.
    if args.skip_outside_ci and not args.purge:
        try:
            provenance()
        except SystemExit as exc:
            print(f"⊘ لا انبعاثَ لدليل الاعتماد — {exc}", file=sys.stderr)
            print("⊘ هذه خطوةٌ **لم تُنتِج دليلاً**؛ الحاجبُ يبقى كما كان.", file=sys.stderr)
            return 0

    if args.purge:
        if args.blocker or args.field or args.json_field or args.fields_file:
            raise SystemExit("--purge لا يُخلَط بانبعاث: إمّا مسحٌ وإمّا كتابةُ دليل.")
        removed = purge(Path(args.out))
        print(f"certification evidence purged ({len(removed)} ملفّاً) — لا يُعتَدّ إلّا بما يُجلَب.")
        for path in removed:
            print(f"  − {path.name}")
        return 0
    if not args.blocker:
        raise SystemExit("--blocker مطلوب (أو استعمل --purge).")

    fields: dict[str, object] = {}
    if args.fields_file:
        fields.update(fields_from_file(Path(args.fields_file)))
    text_fields = _parse_assignments(args.field, as_json=False)
    json_fields = _parse_assignments(args.json_field, as_json=True)
    overlap = set(text_fields) & set(json_fields)
    if overlap:
        raise SystemExit(f"حقلٌ مُعرَّفٌ مرّتين بـ--field و--json-field: {', '.join(sorted(overlap))}")
    fields.update(text_fields)
    fields.update(json_fields)

    path = emit(args.blocker, fields, Path(args.out))
    # `relative_to` يرمي على مسارٍ خارج الشجرة — و`--out` يقبل الخارج عمداً (رملُ
    # التكذيب يكتب في مؤقّت). كان سطرُ الطباعة يُسقِط انبعاثاً **نجح** بـ`ValueError`:
    # عطلٌ في الزينة يُقرأ فشلاً في القياس. مقيسٌ في أوّل تمريرةِ تكذيب.
    try:
        shown: Path | str = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"certification evidence emitted: {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
