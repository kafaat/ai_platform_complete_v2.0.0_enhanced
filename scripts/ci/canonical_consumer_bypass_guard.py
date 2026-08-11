#!/usr/bin/env python3
"""`KNOWLEDGE-CANONICAL-CONSUMPTION-01` — مُستهلِكٌ لا يُعيد اشتقاق ما له مُنتِجٌ قانونيّ.

**العطل الذي يوجد هذا الحارس لأجله** وقع في هذه الشجرة مقيساً: سلسلة M2.2⇒M2.6
كانت مقطوعة، فقرأت قدرةُ الرشّ حقلاً غير موجود وأنتجت `blocked` دائماً. أُصلِحت
بإضافة `root_zone_refill_cap_mm` مُنتَجاً قانونيّاً. لكنّ الإصلاح ترك بابين
مفتوحين: لا شيء يمنع مُستهلِكاً قادماً من كتابة `safe_depth = raw_mm * 0.8` حين
يجد الحقل غائباً، ولا شيء يجعل تلك التبعيّة **مُعلَنةً** أصلاً.

والارتداد إلى الخام أخبثُ من الانقطاع: الانقطاع يُنتِج `blocked` فيُرى، والارتداد
يُنتِج **رقماً معقولاً** فيمرّ. `raw_mm` كمّيّةُ ماءٍ متاحة، و`maximum_safe_depth_mm_event`
عمقٌ مرّ بالميل والتسرّب والرياح وشهادة الحزمة. تساويهما عدديّاً اليوم عند المُنتِج
هو ما يجعل الاشتقاق مغرياً — ومتى تغيّرت السياسة انفصلا وبقي المُشتَقّ صامتاً.

**القاعدة المفروضة، وهي دقيقةٌ عمداً:** اسمٌ يُربَط في مِلَفِّ مُستهلِكٍ بالحقل
القانونيّ **لا يجوز أن يُربَط في المِلَفّ نفسه بتعبيرٍ يذكر مدخلاً خاماً محظوراً.**
هذا يلتقط شكلَي الارتداد الحقيقيّين — `x = cap.get(F) or raw_mm` و
`x = cap.get(F)` ثمّ `if x is None: x = raw_mm * p` — ولا يُجرّم استعمال `raw_mm`
لغرضه المشروع. و`hourly_energy_aware_irrigation_mpc` يفعل ذلك فعلاً: يقرأ
`raw_mm` لحساب الاستنزاف ويقرأ العمق الآمن من القدرة، والاسمان منفصلان.

**ولا يُجرَّم مفتاحُ قاموسٍ:** `{"raw_mm": x}` كتابةٌ لا قراءة. وتجريمُه كان
سيُطلِق الحارسَ على كلّ مُنتِجٍ يعرض حقلَه — إيجابيّةٌ كاذبة تُدرِّب قارئها
على تجاهل الأحمر.

**وحدُّ صدقٍ يُقال:** لا التفافَ قائماً في الشجرة اليوم. هذا الحارس يمنع
**انحداراً** ولا يُصلِح عطلاً حاضراً — والفرق مقيسٌ لا مُدَّعى: المستهلكون
الأربعة المُسجَّلون يقرؤون الحقول القانونيّة، وقد فُحِصوا قبل التسجيل.

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


def load_keys(registry_path: Path) -> list[dict]:
    """يقرأ السجلّ **ويرفع** عند أيّ خلل — «لم يُقرأ» ليس «لا قيد»."""
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


def referenced_identifiers(node: ast.AST) -> set[str]:
    """معرّفاتٌ **مقروءة** داخل تعبير، مع استثناء مفاتيح القواميس.

    تُحتسَب: الأسماء (`raw_mm`) · أسماء السمات (`.maximum_safe_depth_mm_event`) ·
    وكلُّ سلسلةٍ حرفيّة. ولا تُحتسَب السلسلة حين تكون **مفتاحاً في قاموسٍ حرفيّ**،
    لأنّها هناك كتابةٌ لا قراءة.

    **ولماذا كلُّ سلسلةٍ لا سلاسلُ `.get()` وحدها:** القراءة تأتي بأشكالٍ كثيرة —
    `d.get(F)` و`d[F]` و`read_field(d, F)` — وحصرُها في شكلٍ واحد يجعل الحارس
    يرى الشكل الذي صادفه كاتبُه ويعمى عن البقيّة. وقد كان هذا فعلاً: الفرعُ
    أدناه كان كوداً ميّتاً لأنّ السلاسل المجرّدة لم تكن تُحتسَب أصلاً، فكان
    اختبارُ «المفتاح كتابةٌ لا قراءة» يمرّ **لسببٍ غير سببه**. كشفَته الطفرة.
    """
    found: set[str] = set()

    def walk(current: ast.AST) -> None:
        if isinstance(current, ast.Dict):
            for value in current.values:
                walk(value)
            return
        if isinstance(current, ast.Name):
            found.add(current.id)
        elif isinstance(current, ast.Attribute):
            found.add(current.attr)
        elif isinstance(current, ast.Constant) and isinstance(current.value, str):
            found.add(current.value)
        for child in ast.iter_child_nodes(current):
            walk(child)

    walk(node)
    return found


def _targets(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, ast.Assign):
        for target in node.targets:
            names |= {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.add(node.target.id)
    elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        names.add(node.target.id)
    return names


def bindings(tree: ast.AST, field: str, forbidden: set[str]) -> tuple[set[str], set[str]]:
    """يُرجِع (الأسماء المربوطة بالحقل القانونيّ، الأسماء الملوَّثة بالخام)."""
    canonical: set[str] = set()
    tainted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        value = getattr(node, "value", None)
        if value is None:
            continue
        refs = referenced_identifiers(value)
        targets = _targets(node)
        if field in refs:
            canonical |= targets
        if refs & forbidden:
            tainted |= targets
    return canonical, tainted


def violations(keys: list[dict], root: Path) -> tuple[list[str], int]:
    """يُرجِع (المخالفات، عدد المستهلكين المفحوصين فعلاً)."""
    problems: list[str] = []
    examined = 0

    for entry in keys:
        key = entry.get("key")
        field = entry.get("producer_field")
        producer = entry.get("producer_module")
        consumers = entry.get("consumers") or []
        forbidden = set(entry.get("forbidden_raw_inputs") or [])
        if not all(isinstance(x, str) and x for x in (key, field, producer)):
            problems.append(f"✗ مدخلٌ ناقص في السجلّ: {key!r}")
            continue
        if not forbidden:
            problems.append(f"✗ «{key}»: لا مدخلات خام محظورة — قيدٌ بلا محتوى")
            continue

        producer_path = root / producer
        if not producer_path.is_file():
            problems.append(f"✗ «{key}»: المُنتِج المُعلَن غير موجود — {producer}")
        elif field not in producer_path.read_text(encoding="utf-8"):
            # مدخلٌ بائت: المُنتِج لم يعد يعرف الحقل، فالسجلّ يصف شجرةً زالت.
            problems.append(f"✗ «{key}»: المُنتِج {producer} لا يذكر الحقل «{field}»")

        for consumer in consumers:
            consumer_path = root / consumer
            if not consumer_path.is_file():
                problems.append(f"✗ «{key}»: مُستهلِكٌ مُعلَنٌ غير موجود — {consumer}")
                continue
            try:
                tree = ast.parse(consumer_path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                problems.append(f"✗ «{key}»: تعذّر تحليل {consumer} — {exc}")
                continue
            examined += 1

            canonical, tainted = bindings(tree, field, forbidden)
            if not canonical:
                # بندٌ إيجابيّ: مُستهلِكٌ لا يقرأ الحقل أصلاً إمّا مُدرَجٌ خطأً
                # أو كفّ عن استهلاكه — وفي الحالين السجلّ يَعِد بحراسةٍ لا يملكها.
                problems.append(
                    f"✗ «{key}»: {consumer} لا يقرأ «{field}» من المُنتِج القانونيّ — "
                    "مدخلٌ يَعِد بحراسةٍ لا تقع"
                )
                continue
            overlap = sorted(canonical & tainted)
            if overlap:
                problems.append(
                    f"✗ «{key}»: {consumer} يربط {overlap} بالحقل القانونيّ **و**"
                    f" بمدخلٍ خام من {sorted(forbidden)} — ارتدادٌ يُنتِج رقماً معقولاً"
                    " من مصدرٍ غير قانونيّ"
                )

    return problems, examined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="canonical consumer bypass guard")
    parser.add_argument("--registry", default=str(REGISTRY))
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)

    keys = load_keys(Path(args.registry))
    problems, examined = violations(keys, Path(args.root))

    if examined == 0:
        # «صفر مفحوص» ليس نجاحاً: خضرةٌ عن سؤالٍ لم يُطرَح.
        problems.append("✗ لم يُفحَص أيّ مُستهلِك — الحارس أخضرُ لأنّه لم ينظر")

    if problems:
        for line in problems:
            for index, part in enumerate(line.splitlines()):
                print(part if index == 0 else f"    {part}")
        raise SystemExit(1)

    print(f"canonical_consumer_bypass_guard: PASS ({len(keys)} مفتاحاً · {examined} مُستهلِكاً مفحوصاً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
