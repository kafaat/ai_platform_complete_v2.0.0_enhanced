#!/usr/bin/env python3
"""`SHADOW-SOURCE-OF-TRUTH-01` — مفتاحٌ واحد، مُنتِجٌ واحد، وعقودٌ لا تُخالِف السجلّ.

**العطل الذي يوجد هذا الحارس لأجله وقع في هذه الشجرة قبل أيّام:** كان
`maximum_safe_depth_mm_event` مفتاحاً واحداً في السجلّ، بينما يُصدِره **مُنتِجان**:
قدرةُ الرشّ تُصدِر الحدَّ الناتج عن الجريان، والرسمُ البيانيّ يُصدِر
`min(machine_depth, safe_event_depth)` — حدّاً أضيق. فكان مَن يقرأ الاسم يظنّه
شيئاً واحداً وهما شيئان، ونَسَبُ أحدهما إلى الآخر **كذب**.

ولم يظهر ذلك بالقراءة: ظهر ساعةَ ربط المُنسِّق الحقيقيّ. وهذا الحارس يجعل ظهوره
لا يعتمد على أن يربط أحدٌ شيئاً.

**ثلاثة بنود:**

١) **مُنتِجٌ واحد لكلّ مفتاح** — ومُنتِجان لمفتاحٍ واحد مخالفة.
٢) **مِلَفّان مختلفان لا يدّعيان المصدر نفسه** — اسمُ المصدر هويّةٌ لا وصف.
٣) **كلُّ عقدٍ مُعلَن يوافق السجلّ** — عقدٌ يُسمّي مصدراً غير المُسجَّل يُنشئ
   مصدرَ حقيقةٍ ظلّاً بإعلانٍ واحد، وهو أرخصُ طريقٍ إليه وأخفاه.

والبند الثالث يُقرأ بـ`ast` من مِلَفّات العقود لا بالنصّ: تعليقٌ يذكر اسم مصدرٍ
كان سيُحمِر حارساً نصّيّاً، وهو الصنف المُسجَّل `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`.

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
CONTRACT_DIR = ROOT / "shared" / "knowledge"


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


def declared_requirements(tree: ast.AST) -> list[tuple[str, str]]:
    """أزواج (المفتاح، مصدر الحقيقة) من كلّ `KnowledgeRequirement(...)` مُعلَن.

    تُقرأ من الاستدعاء نفسه بوسائطه المُسمّاة، فلا يُحتسَب ذِكرٌ في تعليقٍ ولا
    اسمٌ يرد في سلسلةٍ عابرة.
    """
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != "KnowledgeRequirement":
            continue
        found: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg in {"key", "source_of_truth"} and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    found[kw.arg] = kw.value.value
        if "key" in found and "source_of_truth" in found:
            pairs.append((found["key"], found["source_of_truth"]))
    return pairs


def violations(keys: list[dict], contract_dir: Path) -> tuple[list[str], int]:
    problems: list[str] = []

    by_key: dict[str, str] = {}
    by_source: dict[str, str] = {}
    for entry in keys:
        key = entry.get("key")
        source = entry.get("source_of_truth")
        module = entry.get("producer_module")
        if not all(isinstance(x, str) and x for x in (key, source, module)):
            problems.append(f"✗ مدخلٌ ناقص: {key!r}")
            continue
        if key in by_key:
            problems.append(
                f"✗ «{key}»: مفتاحٌ بمُنتِجَين — {by_key[key]} و{source}. "
                "مفتاحٌ واحد بمعنيين يجعل نَسَب أحدهما إلى الآخر كذباً"
            )
        else:
            by_key[key] = source
        previous = by_source.get(source)
        if previous is not None and previous != module:
            problems.append(
                f"✗ «{source}»: يُدَّعى مصدراً من مِلَفّين — {previous} و{module}. اسمُ المصدر هويّةٌ لا وصف"
            )
        else:
            by_source[source] = module

    declared = 0
    if not contract_dir.is_dir():
        problems.append(f"✗ مجلّد العقود غير موجود: {contract_dir}")
        return problems, declared

    for path in sorted(contract_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"✗ تعذّر تحليل {path.name} — {exc}")
            continue
        for key, source in declared_requirements(tree):
            declared += 1
            registered = by_key.get(key)
            if registered is None:
                problems.append(f"✗ {path.name}: العقد يُعلِن مفتاحاً غير مُسجَّل — «{key}»")
            elif registered != source:
                problems.append(
                    f"✗ {path.name}: «{key}» يُعلَن من «{source}» والسجلّ يقول "
                    f"«{registered}» — مصدرُ حقيقةٍ ظلّ بإعلانٍ واحد"
                )

    return problems, declared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="shadow source-of-truth guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--contracts", default=str(CONTRACT_DIR))
    args = parser.parse_args(argv)

    keys = load_keys(Path(args.registry))
    problems, declared = violations(keys, Path(args.contracts))

    if declared == 0:
        # لا عقدَ مقروء ⇒ البند الثالث لم يُفحَص، والخضرة عنه تكذب.
        problems.append("✗ لم يُقرأ أيّ متطلَّبٍ مُعلَن — الحارس أخضرُ لأنّه لم ينظر")

    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)

    print(f"shadow_source_of_truth_guard: PASS ({len(keys)} مفتاحاً · {declared} متطلَّباً مُعلَناً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
