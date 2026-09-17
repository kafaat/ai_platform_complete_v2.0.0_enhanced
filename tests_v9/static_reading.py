"""قارئان ساكنان يتشاركهما حرّاسُ حدّ الحاوية: استيراداتُ وحدةٍ، ومصادرُ `COPY` في صورة.

**لماذا مُوحَّدان (مراجعتا #1018 و#1019):** كان لكلّ حارسٍ قارئُه الخاصّ، فأُصلح قارئُ
حارسٍ وبقي الآخرُ ضيّقاً بالعيب نفسِه — ورُصِد ذلك مرّتين على ملفَّين في مراجعتَين
متتاليتَين. والقارئُ **الأضيقُ من دعوى حارسه يُعطي أخضرَ كاذباً لا حمرة**، وهو أسوأُ
من غياب الحارس لأنّه يُشترى به اطمئنان. فالتوحيدُ هنا ليس تنظيفاً بل إغلاقُ الصنف:
إصلاحٌ واحد يسري على كلّ من يقرأ.

**حدودُ القراءة، معلَنةٌ لا مسكوتٌ عنها:**
- وسيطُ استيرادٍ **محسوب** (`import_module(name_from_config)`) لا يُقرأ بالتحليل الساكن؛
  الحرفيُّ وحده مُغطًّى.
- مصدرُ `COPY --from=<stage>` مسارٌ في مرحلةِ بناءٍ أخرى لا في شجرة المستودع، فيُتجاهَل؛
  ومراحلُ البناء نفسُها تُقرأ بأسطر `COPY` الخاصّة بها في الملفّ ذاته.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path, PurePosixPath

_DYNAMIC_IMPORT_CALLS = {"import_module", "__import__"}


def is_test_path(path: Path) -> bool:
    """اختباريٌّ بالمجلَّد أو بأيٍّ من عُرفَي التسمية القائمَين في هذه الشجرة."""
    if any(part in {"tests", "tests_v9"} for part in path.parts):
        return True
    return path.name.startswith("test_") or path.name.endswith("_test.py")


def imports_of(path: Path) -> list[str]:
    """كلُّ ما تستورده وحدةٌ على القرص؛ ملفٌّ لا يُحلَّل يُقرأ فارغاً."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    return imported_names(tree)


def imported_names(tree: ast.AST) -> list[str]:
    """أسماءُ الاستيراد بكلّ صيغه: `import x` · `from x import y` · `from . import y` · الحرفيُّ الديناميكيّ."""
    names: list[str] = []
    for node in ast.walk(tree):
        names.extend(_names_of_import_node(node))
    return names


def _names_of_import_node(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        # `import a.b as c` يُدخِل `a` إلى النطاق، فالجذرُ يُقرأ أيضاً كي لا يفلت
        # `import config.guardrail_feature_flags` من فحصٍ يبحث عن الاسم الكامل أو جذره.
        out: list[str] = []
        for alias in node.names:
            out.append(alias.name)
            out.append(alias.name.split(".")[0])
        return out
    if isinstance(node, ast.ImportFrom):
        if node.module:
            return [node.module] + [f"{node.module}.{a.name}" for a in node.names]
        # `from . import X` — الوحدةُ `None` والاسمُ المستورَد هو الوحدة.
        return [a.name for a in node.names]
    if isinstance(node, ast.Call):
        target = _dynamic_import_target(node)
        return [target] if target else []
    return []


def _dynamic_import_target(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    else:
        return None
    if name not in _DYNAMIC_IMPORT_CALLS or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def guarded_import_names(tree: ast.AST) -> list[str]:
    """أسماءُ ما يُستورَد **داخل** `try` — أي ما له بديلٌ صامتٌ محتمل في `except`.

    يشمل `ast.Import` كما يشمل `ast.ImportFrom`: فحصٌ يقتصر على الثاني يفوّت
    `import …flags` داخل `try` ويمرّ أخضرَ على البديل الصامت نفسِه.
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for stmt in node.body:
            for inner in ast.walk(stmt):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    names.extend(_names_of_import_node(inner))
    return names


def copy_sources(dockerfile: Path) -> list[str]:
    """مُعامِلاتُ المصدر في كلّ سطر `COPY`: بلا الرايات وبلا الوِجهة (آخِرُ مُعامِل).

    مُغطًّى: `COPY a b /dst/` · `COPY --chown=u:g a /dst/` · صيغةُ مصفوفة JSON ·
    استمرارُ السطر بـ`\\`. ومُستثنًى بقصد: `COPY --from=<stage>` (انظر وثيقة الوحدة).
    """
    sources: list[str] = []
    for raw in _logical_lines(dockerfile.read_text(encoding="utf-8")):
        line = raw.strip()
        if not re.match(r"(?i)^copy\s", line):
            continue
        rest = line[len("COPY") :].strip()
        flags = re.match(r"(?i)^(?:--\S+\s+)*", rest)
        consumed = flags.group(0) if flags else ""
        if re.search(r"(?i)--from=", consumed):
            continue
        rest = rest[len(consumed) :].strip()
        if rest.startswith("["):
            try:
                operands = [str(x) for x in json.loads(rest)]
            except (ValueError, TypeError):
                operands = []
        else:
            operands = rest.split()
        if len(operands) >= 2:
            sources.extend(operands[:-1])
    return sources


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    buffer = ""
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        lines.append(buffer + stripped)
        buffer = ""
    if buffer:
        lines.append(buffer)
    return lines


def ships(source: str, target: str) -> bool:
    """هل يُدخِل مصدرُ `COPY` هذا المسارَ `target` (نسبيّاً للجذر) إلى الصورة؟"""
    normalized = source.strip().rstrip("/")
    if normalized in {"", ".", "./"}:
        return True
    src = PurePosixPath(normalized.removeprefix("./"))
    dst = PurePosixPath(target)
    return src == dst or src in dst.parents
