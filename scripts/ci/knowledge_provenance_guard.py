#!/usr/bin/env python3
"""`KNOWLEDGE-PROVENANCE-01` — مُنتِجٌ قانونيّ يحمل نَسَبَه، أو لا يُقرأ.

**العطل الذي يوجد هذا الحارس لأجله مقيسٌ في هذه الشجرة:** قدرةُ الرشّ كانت
تُبلِّغ `verified` و`root_zone_profile_digest` فيها `None` — دليلٌ يعرض ثقبَه
بوصفه حقيقةً مُتحقَّقة. وهو أسوأ من الحجب، لأنّ من يقرأ `verified` لا يعود ينظر
في الأدلّة.

**والمرساةُ الزمنيّة ليست زينة:** بلا `generated_at` لا يُقاس عمرُ القيمة، فيصير
كلّ عقدٍ يُعلِن `max_age_seconds` **حاجباً دائماً** بـ`FRESHNESS_UNMEASURABLE`.
أي أنّ بندَ الطزاجة في المُحلِّل يبقى معطَّلاً بصمتٍ ما لم يُفرَض هذا هنا. وقد
كان كذلك فعلاً: `sprinkler` و`graph` بلا مرساةٍ زمنيّة حتّى هذه الشريحة.

**ولماذا الفحص على المُخرَج لا على الـdataclass:** ما يُخزَّن ويُنقَل ويُقرأ هو
القاموس. وحقلٌ مُعلَنٌ في الصنف ولا يظهر في `base` يُنتِج `TypeError` عند البناء
أو — أسوأ — يُملأ افتراضيّاً فيبدو موجوداً وهو فارغ.

لا pytest ولا تبعيّات: يعمل مستقلّاً داخل وظيفة الحرّاس.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "knowledge_source_registry.json"
REGISTRY_SCHEMA = "sahool.knowledge_source_registry"

# الحدّ الأدنى لغلاف النَّسَب. كلٌّ منها يجيب سؤالاً يُطرَح فعلاً عند القرار:
# «بأيّ مواصفة تُقرأ؟» · «أيّ إصدارٍ أنتجها؟» · «متى؟» · «ومتى تسري؟».
REQUIRED_PROVENANCE = ("schema_version", "product_version", "generated_at", "effective_at")


def load_keys(registry_path: Path) -> list[dict]:
    if not registry_path.is_file():
        raise SystemExit(f"✗ سجلّ مصادر الحقيقة غير موجود: {registry_path}")
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ سجلٌّ غير قابل للتحليل: {registry_path} — {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"✗ مخطَّطٌ غير متوقَّع في {registry_path}")
    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys:
        raise SystemExit(f"✗ سجلٌّ بلا مفاتيح: {registry_path}")
    return keys


def emitted_dict_keys(tree: ast.AST) -> set[str]:
    """مفاتيحُ السلاسل الحرفيّة في كلّ قاموسٍ حرفيّ في المِلَفّ.

    يُقاس المُخرَج كما يُكتَب، لا كما يُعلَن في التوقيع.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                found.add(key.value)
    return found


def digest_field_for(entry: dict) -> str | None:
    """بصمةُ المُنتِج: ما يربط القيمةَ بالعمل الذي أنتجها — **مُعلَنةٌ لا مُفترَضة**.

    أوّل صياغةٍ هنا افترضت `capability_digest` افتراضيّاً، فأطلقت على
    `canonical_root_zone_profile` وبصمتُه `profile_digest`. والافتراض الصامت هو
    الصنف نفسه الذي يطارده الحارس: قيمةٌ تُقاس مقابل اسمٍ خمّنه كاتبُه. فصار
    الحقل مطلوباً في السجلّ، وغيابُه مخالفةٌ لا ارتداد.
    """
    declared = entry.get("producer_digest_field")
    return declared if isinstance(declared, str) and declared else None


def violations(keys: list[dict], root: Path) -> tuple[list[str], int]:
    problems: list[str] = []
    examined = 0
    seen: set[str] = set()

    for entry in keys:
        producer = entry.get("producer_module")
        key = entry.get("key")
        if not isinstance(producer, str) or not producer:
            problems.append(f"✗ مدخلٌ بلا مُنتِج: {key!r}")
            continue
        if producer in seen:
            continue
        seen.add(producer)

        path = root / producer
        if not path.is_file():
            problems.append(f"✗ «{key}»: المُنتِج المُعلَن غير موجود — {producer}")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"✗ «{key}»: تعذّر تحليل {producer} — {exc}")
            continue
        examined += 1

        emitted = emitted_dict_keys(tree)
        missing = [field for field in REQUIRED_PROVENANCE if field not in emitted]
        if missing:
            problems.append(
                f"✗ {producer}: مُخرَجٌ بلا نَسَبٍ كامل — ينقصه {missing}. "
                "قيمةٌ بلا مرساةٍ زمنيّة لا يُقاس عمرُها، فيبقى بند الطزاجة معطَّلاً بصمت"
            )
        digest_field = digest_field_for(entry)
        if digest_field is None:
            problems.append(
                f"✗ «{key}»: `producer_digest_field` غير مُعلَن — بصمةُ مُنتِجٍ تُخمَّن ليست بصمة"
            )
            continue
        source = path.read_text(encoding="utf-8")
        if digest_field not in emitted and f"{digest_field}=" not in source:
            problems.append(
                f"✗ {producer}: لا يُصدِر بصمة «{digest_field}» — "
                "قيمةٌ بلا بصمة مُنتِجها تُقرأ حقيقةً بلا سبيلٍ إلى مصدرها"
            )

    return problems, examined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="knowledge provenance guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    keys = load_keys(Path(args.registry))
    problems, examined = violations(keys, Path(args.root))

    if examined == 0:
        problems.append("✗ لم يُفحَص أيّ مُنتِج — الحارس أخضرُ لأنّه لم ينظر")

    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)

    print(f"knowledge_provenance_guard: PASS ({examined} مُنتِجاً مفحوصاً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
