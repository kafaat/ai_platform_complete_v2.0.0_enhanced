#!/usr/bin/env python3
"""`RAG-ANSWERS-AN-OPERATIONAL-FACT-01` — الاسترجاع لا يجيب عن حقيقةٍ تشغيليّة.

**القاعدة التي يفرضها** بندٌ من جدول المصادر: «ما ET0 الحاليّ؟ · كم السعة
المتبقّية؟ · ما الحدّ الآمن لهذه الرية؟ · هل هذا القرار مُصرَّح؟» **لا يجوز أن
يجيب عنها RAG**. والاسترجاع يبقى للمستندات غير المُهيكَلة — «ما توصية FAO
بشأن…» — لا لحالة الحقل الآن.

**ولماذا هذا البند أخطر من غيره:** مُخرَجُ الاسترجاع **نصٌّ معقول دائماً**. فإن
أجاب عن حدٍّ آمنٍ للرية أنتج رقماً يبدو صحيحاً ولا يمرّ بالميل ولا التسرّب ولا
شهادة الحزمة — وهو صنف «رقمٌ معقول من مصدرٍ غير قانونيّ» نفسه الذي يحرسه
`canonical_consumer_bypass_guard`، لكن من بابٍ لا يراه: لا حقلَ يُقرأ هنا ولا
اشتقاقَ من خام، بل **نصٌّ يُولَّد**.

**والتعريف مقيسٌ لا انطباعيّ:** «الحقيقة التشغيليّة» هي ما يحمل مفتاحاً في
`knowledge_source_registry.json`. فالحدّ يتّسع بالسجلّ ولا يحتاج قائمةً ثانية
تَبيت وحدها.

**بندان:**

١) وحدةٌ تبلغ الاسترجاع لا تذكر أيّ مفتاحٍ مُسجَّل ولا حقلَ مُنتِجٍ مُسجَّل.
٢) مُنتِجٌ قانونيّ مُسجَّل لا يستورد الاسترجاع ولا يقرأ عنوانه.

**وحدُّ صدقٍ يُقال:** لا خرقَ قائماً اليوم — قِيس قبل كتابة الحارس. فهذا يمنع
انحداراً ولا يُصلِح عطلاً حاضراً.

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
SCAN_DIRS = ("services", "shared", "agents", "bots")

# علاماتُ بلوغِ الاسترجاع. تُقاس بالنصّ لأنّ الوصول يقع عبر عنوانٍ في البيئة لا
# عبر استيرادٍ وحده، فلا يكفي `ast` هنا.
RAG_MARKERS = ("RAG_BASE_URL", "rag-retrieval", "sahool-rag")


def load_registry(registry_path: Path) -> tuple[set[str], set[str], set[str]]:
    """يُرجِع (المفاتيح، حقول المُنتِجين، مِلَفّات المُنتِجين)."""
    if not registry_path.is_file():
        raise SystemExit(f"✗ سجلّ مصادر الحقيقة غير موجود: {registry_path}")
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ سجلٌّ غير قابل للتحليل: {registry_path} — {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"✗ مخطَّطٌ غير متوقَّع في {registry_path}")
    entries = raw.get("keys")
    if not isinstance(entries, list) or not entries:
        raise SystemExit(f"✗ سجلٌّ بلا مفاتيح: {registry_path}")
    keys, fields, modules = set(), set(), set()
    for entry in entries:
        if isinstance(entry.get("key"), str):
            keys.add(entry["key"])
        if isinstance(entry.get("producer_field"), str):
            fields.add(entry["producer_field"])
        if isinstance(entry.get("producer_module"), str):
            modules.add(entry["producer_module"])
    return keys, fields, modules


def touches_rag(source: str) -> bool:
    return any(marker in source for marker in RAG_MARKERS)


def string_constants(tree: ast.AST) -> set[str]:
    """سلاسلُ الشيفرة الحرفيّة — لا التعليقات ولا نصوص التوثيق.

    الشرحُ الذي يقول «هذا لا يُسأل عنه RAG» يجب ألّا يُحمِر الحارس؛ وهو الصنف
    المُسجَّل `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`.
    """
    found: set[str] = set()
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                found.add(node.value)
    return found


def scan_files(root: Path, scan_dirs: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for name in scan_dirs:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in {"tests", "__pycache__"} for part in path.parts):
                continue
            if path.name.startswith("test_"):
                continue
            files.append(path)
    return files


def violations(
    keys: set[str], fields: set[str], modules: set[str], files: list[Path], root: Path
) -> tuple[list[str], int]:
    problems: list[str] = []
    rag_files = 0
    operational = keys | fields

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root).as_posix()
        is_rag = touches_rag(source)

        if is_rag:
            rag_files += 1
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                problems.append(f"✗ تعذّر تحليل {rel} — {exc}")
                continue
            # مطابقةُ **احتواء** لا تساوٍ تامّ: الحالة الواقعيّة الخطيرة قالبُ
            # سؤالٍ يذكر الحقيقة داخل جملة — «ما maximum_safe_depth_mm_event
            # للحقل؟» — لا سلسلةٌ تساوي الاسم وحده. والتساوي التامّ كان يجعل
            # استثناءَ نصوص التوثيق كوداً ميّتاً، وهو ما كشفته الطفرة.
            literals = string_constants(tree)
            named = {fact for fact in operational if any(fact in text for text in literals)}
            if named:
                problems.append(
                    f"✗ {rel}: وحدةٌ تبلغ الاسترجاع تذكر حقيقةً تشغيليّة {sorted(named)} — "
                    "مُخرَجُ الاسترجاع نصٌّ معقولٌ دائماً، فإجابتُه عن هذه تُنتِج رقماً "
                    "لا يمرّ بأيّ قيدٍ قانونيّ"
                )

        if rel in modules and is_rag:
            problems.append(
                f"✗ {rel}: مُنتِجٌ قانونيّ يبلغ الاسترجاع — مصدرُ الحقيقة لا يستمدّ حقيقتَه من نصٍّ مُولَّد"
            )

    return problems, rag_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="rag operational boundary guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    root = Path(args.root)
    keys, fields, modules = load_registry(Path(args.registry))
    files = scan_files(root, SCAN_DIRS)
    problems, rag_files = violations(keys, fields, modules, files, root)

    if rag_files == 0:
        # صفرُ وحدةٍ تبلغ الاسترجاع يعني أنّ الحدّ لم يُقَس أصلاً — أو أنّ
        # علاماتِ البلوغ بائتة. والخضرة عنه تُقرأ «لا خرق» وهي «لم يُنظَر».
        problems.append(
            "✗ لم تُوجَد أيّ وحدةٍ تبلغ الاسترجاع — الحارس أخضرُ لأنّه لم ينظر، "
            f"أو العلامات {list(RAG_MARKERS)} بائتة"
        )

    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)

    print(
        f"rag_operational_boundary_guard: PASS "
        f"({rag_files} وحدةً تبلغ الاسترجاع · {len(keys | fields)} حقيقةً تشغيليّة محروسة)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
