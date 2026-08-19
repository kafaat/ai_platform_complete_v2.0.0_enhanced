#!/usr/bin/env python3
"""`KNOWLEDGE-RELATION-01` — العلاقة المُسجَّلة هي العلاقة المُنفَّذة.

**الفرق بين هذا وبين Ontology تقليديّة** هو كلّ ما في الأمر. ثلاثيّةٌ من نوع
`Pump --feeds--> Valve` تُكتَب مرّةً ثمّ تَبيت بصمت: لا شيء يقول متى خالفت
الشيفرة. وهذا الحارس يجعل السجلّ **مربوطاً بالتنفيذ**: السلسلة المُعلَنة هنا
يجب أن تساوي — ترتيباً وعدداً — الثابتَ الذي يقرؤه المُنتِج فعلاً.

**ولماذا هذا البند بالذات هو الحامل:** `REQUIRED_LINKS` ليست وصفاً. كلُّ حلقةٍ
غير متاحةٍ تُضيف سببَ حجبٍ باسمها، وأضعفُ حلقةٍ تُشتقّ منها ويُبنى عليها
`operational_eligible`. فحلقةٌ سابعة تُضاف في الشيفرة ولا تُسجَّل — أو حلقةٌ
تُحذَف — تُغيّر قرارَ تشغيلٍ حقيقيّاً بينما تبقى الوثيقة تصف شجرةً زالت.

**والقراءة بـ`ast` لا بالنصّ:** `REQUIRED_LINKS` تُقرأ من إسنادها في المصدر،
فتعليقٌ يذكر اسم حلقةٍ لا يُحتسَب — وهو الصنف المُسجَّل
`TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`.

لا pytest ولا تبعيّات: يعمل مستقلّاً داخل وظيفة الحرّاس.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# GUARD-DIES-PRINTING-ITS-OWN-SUCCESS-UNDER-C-LOCALE-01: مخرَجُ هذا الحارس عربيّ،
# و`print` يُرمّز بلغة الآلة. فتحت `LC_ALL=C` كان يحسب **صحيحاً** ثمّ يموت وهو يطبع
# نجاحه (UnicodeEncodeError) ⇒ خروجٌ بـ1 يُقرَأ «الحارس يحجب» وهو قد مرّ. وحارسٌ
# يُبلِغ فشلاً لأنّه عجز عن طباعة نجاحه أسوأ من حارسٍ صامت: الصامت يُرى غيابُه،
# وهذا يُرى **ضدّ** ما قاس. القراءة محكومة بأساسٍ قائم؛ والمنسيّ كان الكتابة.
# **عند التحميل لا داخل `main()`** — فبعض الحرّاس بلا `main` أصلاً، تطبع من جسدها.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "architecture" / "knowledge_relation_registry.json"
REGISTRY_SCHEMA = "sahool.knowledge_relation_registry"


def load_relations(registry_path: Path) -> list[dict]:
    if not registry_path.is_file():
        raise SystemExit(f"✗ سجلّ العلاقات غير موجود: {registry_path}")
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"✗ سجلٌّ غير قابل للتحليل: {registry_path} — {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != REGISTRY_SCHEMA:
        raise SystemExit(f"✗ مخطَّطٌ غير متوقَّع في {registry_path}")
    relations = raw.get("relations")
    if not isinstance(relations, list) or not relations:
        raise SystemExit(f"✗ سجلٌّ بلا علاقات: {registry_path}")
    return relations


def literal_sequence(tree: ast.AST, symbol: str) -> list[str] | None:
    """قيمةُ ثابتٍ نصّيٍّ متسلسل من إسناده في المصدر — لا من نصّه."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if symbol not in names:
            continue
        value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            return None
        items: list[str] = []
        for element in value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            items.append(element.value)
        return items
    return None


def violations(relations: list[dict], root: Path) -> tuple[list[str], int]:
    problems: list[str] = []
    checked = 0
    seen: set[str] = set()

    for relation in relations:
        name = relation.get("name")
        if not isinstance(name, str) or not name:
            problems.append("✗ علاقةٌ بلا اسم")
            continue
        if name in seen:
            problems.append(f"✗ «{name}»: علاقةٌ مكرَّرة — اسمٌ واحد بدلالتين")
            continue
        seen.add(name)

        semantics = relation.get("semantics")
        if not isinstance(semantics, dict) or "directional" not in semantics:
            problems.append(f"✗ «{name}»: بلا دلالةٍ مُعلَنة — علاقةٌ لا تقول اتّجاهها لا تُنفَّذ")
            continue

        graph_role = relation.get("graph_role")
        if graph_role not in {"reference", "evidence", "operational"}:
            problems.append(f"✗ «{name}»: graph_role غير قانوني — {graph_role!r}")
            continue
        authority = relation.get("authority_semantics")
        evidence = relation.get("evidence_semantics")
        if (
            not isinstance(authority, str)
            or not authority
            or not isinstance(evidence, str)
            or not evidence
        ):
            problems.append(f"✗ «{name}»: دلالة authority/evidence غير مكتملة")
            continue
        if relation.get("direct_execution_permitted") is not False:
            problems.append(f"✗ «{name}»: السجلّ لا يجوز أن يمنح تنفيذًا مباشرًا")
            continue
        if graph_role in {"reference", "evidence"} and authority != "none":
            problems.append(f"✗ «{name}»: علاقة {graph_role} لا يجوز أن تمنح سلطة قرار")
            continue
        if (
            graph_role in {"reference", "evidence"}
            and relation.get("causal_claim_permitted") is not False
        ):
            problems.append(f"✗ «{name}»: علاقة {graph_role} لا يجوز أن تتحول إلى ادعاء سببي")
            continue
        if semantics.get("directional") and relation.get("from") == relation.get("to"):
            problems.append(f"✗ «{name}»: علاقةٌ موجَّهة طرفاها واحد")
            continue

        chain = relation.get("chain")
        module = relation.get("chain_source_module")
        symbol = relation.get("chain_symbol")
        vocab_module = relation.get("vocabulary_source_module")
        vocab_symbol = relation.get("vocabulary_symbol")

        if isinstance(chain, list):
            if len(chain) < 2:
                problems.append(f"✗ «{name}»: سلسلةٌ أقصر من حلقتين ليست علاقة")
                continue
            if any(not isinstance(x, str) or not x for x in chain):
                problems.append(f"✗ «{name}»: السلسلة تحمل عنصراً ليس نصّاً")
                continue
            if semantics.get("acyclic") and len(set(chain)) != len(chain):
                problems.append(f"✗ «{name}»: علاقةٌ مُعلَنةٌ لا دوريّة وسلسلتها تكرّر حلقة")
                continue
            if (
                not isinstance(module, str)
                or not isinstance(symbol, str)
                or not module
                or not symbol
            ):
                problems.append(f"✗ «{name}»: بلا مصدرٍ منفَّذ للسلسلة")
                continue
            path = root / module
            binding_mode = "chain"
            binding_symbol = symbol
        elif (
            isinstance(vocab_module, str)
            and isinstance(vocab_symbol, str)
            and vocab_module
            and vocab_symbol
        ):
            path = root / vocab_module
            binding_mode = "vocabulary"
            binding_symbol = vocab_symbol
        else:
            problems.append(f"✗ «{name}»: بلا binding منفَّذ — لا chain ولا vocabulary")
            continue

        if not path.is_file():
            problems.append(f"✗ «{name}»: مصدر العلاقة غير موجود — {path.relative_to(root)}")
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"✗ «{name}»: تعذّر تحليل {path.relative_to(root)} — {exc}")
            continue
        executed = literal_sequence(tree, binding_symbol)
        if executed is None:
            problems.append(
                f"✗ «{name}»: لم يُقرأ «{binding_symbol}» متسلسلاً نصّيّاً في {path.relative_to(root)}"
            )
            continue
        checked += 1
        if binding_mode == "chain" and executed != list(chain):
            problems.append(
                f"✗ «{name}»: السلسلة المُسجَّلة تخالف المُنفَّذة — السجلّ {list(chain)} · الشيفرة {executed}"
            )
        if binding_mode == "vocabulary" and name not in executed:
            problems.append(
                f"✗ «{name}»: غير موجودة في المفردات المنفَّذة «{binding_symbol}» — {executed}"
            )

        for consumer in relation.get("consumers") or []:
            if not (root / consumer).is_file():
                problems.append(f"✗ «{name}»: مُستهلِكٌ مُعلَنٌ غير موجود — {consumer}")

    return problems, checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="knowledge relation registry guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    relations = load_relations(Path(args.registry))
    problems, checked = violations(relations, Path(args.root))

    if checked == 0:
        problems.append("✗ لم تُقابَل أيّ علاقةٍ بشيفرةٍ منفَّذة — الحارس أخضرُ لأنّه لم ينظر")

    if problems:
        for line in problems:
            print(line)
        raise SystemExit(1)

    print(f"knowledge_relation_registry_guard: PASS ({checked} علاقةً مُقابَلةً بالتنفيذ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
