#!/usr/bin/env python3
"""عددٌ يُكتب بيدٍ في الدماغ عن الحاضر يجب أن يساوي المقيس — `A-HAND-WRITTEN-COUNT-IN-THE-JOURNAL-DRIFTS-FROM-ITS-OWN-MEASUREMENT-01`.

**العطلُ مقيسٌ على `98a61c5f` (دمج #1038)، وكشفه المالك:** السجلُّ المدموج يقول
``heading_count=272`` و``section_state_count=51``، ومتنُ الـPR يقول ``273`` و``51``،
والمقيسُ الفعليُّ على تلك الشجرة **273/52**. ثلاثُ إجاباتٍ عن سؤالٍ واحد، والحسابُ
من الدليل المدموج نفسِه يُعطي الثالثة: الأساسُ ``a0bba343`` كان 270/49، وتصحيحُ
``V25-AI-RUNTIME-LOCAL-ACCEPTANCE-01`` يضيف +1/+1، والفجوتان الجديدتان +2/+2.

**وكيف مرّ:** وظيفةُ «Gap registry measurement» تقيس السجلَّ فعلاً وتحفظ الخرجَ
مصنوعاً — **لكنّها لا تقارن ما كُتِب بما قِيس**. فخضرتُها تُثبِت أنّ القياس جرى، لا
أنّ النصَّ العدديَّ صادق. وهذا صنفُ «أخضرُ عن سؤالٍ لم يُطرَح» في أخصّ مواضعه:
سجلُّ الحوكمة نفسُه.

**والسببُ الجذريُّ ليس سهواً:** رقمٌ مقيسٌ يُكتب بيدٍ في سجلٍّ يستمرّ التحريرُ فيه
**يبيت داخل شريحته**. كتبتُ ``272/51`` صادقاً، ثمّ أضفتُ مدخلةً أخرى في الشريحة
نفسِها فصار ``273/52``، ولم يعد شيءٌ يُذكّر بالسطر الأوّل.

── لماذا لا تُحجَب **كلُّ** الأعداد ─────────────────────────────────────────────

السجلُّ سردٌ تاريخيّ: فيه أعدادٌ صحيحةٌ **عن أشجارٍ ماضية** (``heading_count=263``
عند ``4b8641af``). حارسٌ يطلب منها أن تساوي قياسَ اليوم يُحمِّر على عملٍ سليم،
ويُطفَأ في أوّل أسبوع — فتصير الحمايةُ صفراً.

**فالمُرساةُ إعلانُ الزمن، وهي مقيسةٌ على الشجرة لا مختارةٌ ذوقاً:** ادّعاءٌ يذكر
بصمةَ الشجرة التي قِيس عندها ادّعاءٌ **عن الماضي** — يُذكَر ولا يُحجَب، لأنّ التحقّق
منه يقتضي إعادةَ بناء تلك الشجرة. وادّعاءٌ لا يذكر بصمةً هو ادّعاءٌ **عن الحاضر**،
والحاضرُ مقيسٌ الآن، فيجب أن يطابقه.

والقاعدةُ تُقال في سطر: **رقمٌ عن الحاضر يجب أن يصدق الآن؛ ورقمٌ عن شجرةٍ ماضية
يجب أن يقول أيَّ شجرة.** وعلى الشجرة المُقاسة يومَ كتابة هذا الحارس: تسعةُ ادّعاءاتٍ
تاريخيّةٍ كلُّها تذكر بصمتَها، وستّةٌ عن الحاضر كلُّها في السطر المعطوب وحدَه.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "sahool-brain" / "gaps" / "registry.md"

#: أسماءُ الحقول كما يكتبها البشر، مربوطةً بما يقيسه `gap_registry_measure`.
#: المختصراتُ مقيسةٌ من السجلّ نفسِه لا مُخترَعة: `orphan=` و`duplicates=` و
#: `unclassified=` كلُّها مكتوبةٌ في الشجرة، فحارسٌ يقرأ الاسمَ الطويل وحدَه
#: يكون **أضيقَ من دعواه** — يزعم أنّه يربط الادّعاءات وهو يرى بعضَها.
CLAIM_KEYS: dict[str, str] = {
    "heading_count": "heading_count",
    "section_state_count": "section_state_count",
    "gap_row_count": "gap_row_count",
    "row_count": "row_count",
    "duplicate_heading_id_count": "duplicate_heading_id_count",
    "duplicates": "duplicate_heading_id_count",
    "orphan_gap_heading_count": "orphan_gap_heading_count",
    "orphan": "orphan_gap_heading_count",
    "orphans": "orphan_gap_heading_count",
    "noncanonical_heading_level_count": "noncanonical_heading_level_count",
    "noncanonical": "noncanonical_heading_level_count",
    "contradictory_section_id_count": "contradictory_section_id_count",
    "unclassified": "_unclassified_total",
    "surfaces_not_measured": "_inventory_surfaces_not_measured",
    "surfaces_declared": "_inventory_surfaces_declared",
}

CLAIM_RE = re.compile(
    r"(?<![\w.])(?P<key>" + "|".join(sorted(CLAIM_KEYS, key=len, reverse=True)) + r")"
    r"`?\s*[=:]\s*`?(?P<value>\d+)"
)
#: بصمةُ شجرةٍ بين علامتَي شيفرة — إعلانُ «هذا عن الماضي».
TREE_REF_RE = re.compile(r"`[0-9a-f]{7,40}`")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def _measure_module() -> Any:
    path = ROOT / "scripts" / "ci" / "gap_registry_measure.py"
    spec = importlib.util.spec_from_file_location("gap_registry_measure", path)
    if not spec or not spec.loader:  # pragma: no cover - يفشل مُغلَقاً
        raise SystemExit(f"✗ لا يمكن تحميل مقياس السجلّ من {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def measured_values(report: dict[str, Any]) -> dict[str, int]:
    """القيمُ المقيسة، بما فيها المشتقُّ الوحيد — ومشتقٌّ يُعلَن لا يُخفى."""
    values = {
        field: report[field]
        for field in set(CLAIM_KEYS.values())
        if field in report and isinstance(report[field], int)
    }
    # `unclassified` في نثر هذا السجلّ تعني «لا صفَّ ولا قسمَ بلا تصنيف» — وهما
    # حقلان. جمعُهما يُعلَن هنا كي لا يُقرأ رقمٌ واحدٌ على أنّه يصف أحدَهما.
    values["_unclassified_total"] = len(report.get("unclassified_rows", [])) + len(
        report.get("unclassified_section_states", [])
    )
    return values


def claims(text: str) -> list[dict[str, Any]]:
    """كلُّ ادّعاءٍ عدديٍّ خارجَ الكتل المُسيَّجة، مع إعلانِ زمنِه."""
    found: list[dict[str, Any]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = FENCE_RE.match(line)
        if marker:
            token = marker.group(1)
            # مثالٌ داخل سياجٍ ليس ادّعاءً عن الشجرة — وإلّا صار توثيقُ الحارس
            # يُحمِّر الحارسَ نفسَه.
            fence = None if fence and token.startswith(fence[0]) else (fence or token)
            continue
        if fence:
            continue
        historical = bool(TREE_REF_RE.search(line))
        for match in CLAIM_RE.finditer(line):
            found.append(
                {
                    "line": number,
                    "key": match.group("key"),
                    "field": CLAIM_KEYS[match.group("key")],
                    "value": int(match.group("value")),
                    "historical": historical,
                }
            )
    return found


def evaluate(found: list[dict[str, Any]], values: dict[str, int]) -> list[str]:
    """أسبابُ الحجب. الادّعاءُ التاريخيُّ لا يُحجَب — يُذكَر."""
    errors: list[str] = []
    for claim in found:
        if claim["historical"]:
            continue
        measured = values.get(claim["field"])
        if measured is None:
            errors.append(
                f"سطر {claim['line']}: `{claim['key']}` لا يقابله حقلٌ في مقياس السجلّ — "
                "اسمٌ لا يقيسه شيء يُقرأ دليلاً وهو ليس كذلك."
            )
        elif claim["value"] != measured:
            errors.append(
                f"سطر {claim['line']}: `{claim['key']}={claim['value']}` والمقيسُ الآن "
                f"**{measured}**. ادّعاءٌ عن الحاضر يجب أن يصدق الآن؛ وإن كان عن شجرةٍ "
                "ماضية فاذكر بصمتَها بين علامتَي شيفرة (`a0bba343`) ليُقرأ تاريخاً."
            )
    return errors


def inventory_values(manifest_path: Path, expected_sha: str) -> dict[str, int]:
    """Read current inventory evidence and cross-check its counts against surface files."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "sahool.diagnostic-inventory.v1"
        or manifest.get("source_sha") != expected_sha
    ):
        raise ValueError("inventory_identity_mismatch")
    states = []
    for path in sorted(manifest_path.parent.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != (
            "sahool.diagnostic-inventory.surface.v1"
        ):
            continue
        state = payload.get("measurement_state")
        if payload.get("surface") != path.name or state not in {"measured", "not_measured"}:
            raise ValueError("inventory_surface_invalid")
        states.append(state)
    if not states:
        raise ValueError("inventory_surfaces_missing")
    measured = {
        "surfaces_declared": len(states),
        "surfaces_not_measured": states.count("not_measured"),
    }
    for key, value in measured.items():
        reported = manifest.get("counts", {}).get(key)
        if type(reported) is not int or reported != value:
            raise ValueError(f"inventory_count_mismatch:{key}")
    return {CLAIM_KEYS[key]: value for key, value in measured.items()}


def measure_inventory(manifest_path: Path | None) -> dict[str, int]:
    """Reuse the canonical generator; never maintain a second surface registry."""
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()
    if manifest_path is not None:
        return inventory_values(manifest_path, sha)
    with tempfile.TemporaryDirectory(prefix="gap-inventory-") as directory:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/diagnostics/build_main_inventory.py"),
                "--out",
                directory,
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return inventory_values(Path(directory) / "inventory_manifest.json", sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ربطُ الادّعاءات العدديّة في سجلّ الفجوات بقياسه")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--inventory-manifest", type=Path)
    args = parser.parse_args(argv)

    path = Path(args.registry)
    text = path.read_text(encoding="utf-8")
    report = _measure_module().measure(text)
    values = measured_values(report)
    found = claims(text)
    if any(c["field"].startswith("_inventory_") and not c["historical"] for c in found):
        try:
            values.update(measure_inventory(args.inventory_manifest))
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            print(f"gap_registry_claim_guard_failed: inventory_evidence_unavailable: {exc}")
            return 1
    errors = evaluate(found, values)

    if errors:
        print("gap_registry_claim_guard_failed")
        for line in errors:
            print(f"- {line}")
        return 1
    present = sum(1 for c in found if not c["historical"])
    # الخضرةُ تُصرّح بما قِيس: «مرّ» بلا عددٍ لا يفرّق بين «قِيس فصدق» و«لم يُقَس».
    print(
        f"gap_registry_claim_guard_ok ({present} ادّعاءً عن الحاضر مربوطاً بالقياس · "
        f"{len(found) - present} ادّعاءً تاريخيّاً يذكر بصمتَه فلا يُحجَب)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
