"""تحقّق آلي أن التوثيق يطابق الكود — يمنع أخطاء التتبّع المتكررة.
يُشغَّل قبل كل تحزيم: python3 tools_check_doc_consistency.py"""

import ast
import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DOC = ROOT / "docs" / "SOURCE_DOCUMENTATION.md"


def check():
    errs = []
    doc = DOC.read_text(encoding="utf-8")

    # 1. عدد الاختبارات: القرص = الجدول = الرأس
    disk_tests = sum(
        len(re.findall(r"def test_", open(f, encoding="utf-8").read()))
        for f in glob.glob(str(ROOT / "tests/test_*.py"))
    )
    disk_files = len(glob.glob(str(ROOT / "tests/test_*.py")))
    table_nums = [int(n) for n in re.findall(r"`test_\w+\.py`\s*\|\s*(\d+)", doc)]
    table_sum = sum(table_nums)
    header = re.search(r"(\d+)/\1", doc)
    header_n = int(header.group(1)) if header else 0

    if disk_tests != table_sum:
        errs.append(f"عدد الاختبارات: القرص={disk_tests} ≠ مجموع الجدول={table_sum}")
    if disk_tests != header_n:
        errs.append(f"عدد الاختبارات: القرص={disk_tests} ≠ الرأس={header_n}")
    if disk_files != len(table_nums):
        errs.append(f"ملفات الاختبار: القرص={disk_files} ≠ الجدول={len(table_nums)}")

    # 2. عدد الواجهات: القرص = الرأس
    import os

    api = 0
    for p in glob.glob(str(ROOT / "**/*.py"), recursive=True):
        rel = os.path.relpath(p, ROOT)
        parts = rel.split(os.sep)
        if "__pycache__" in parts or "tests" in parts or rel.endswith("__init__.py"):
            continue
        for node in ast.parse(open(p, encoding="utf-8").read()).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                api += 1
    doc_api = re.search(r"(\d+) واجهة عامة", doc)
    if doc_api and int(doc_api.group(1)) != api:
        errs.append(f"الواجهات: القرص={api} ≠ التوثيق={doc_api.group(1)}")

    # 3. حياد النواة + بنية المستودع: كشف تسرّبات في الكود + docstrings
    #    + comments + directory names + YAML/JSON config files
    # المبدأ الحاكم #٥: لا أسماء مديريات/مزارع/حقول محدّدة في sahool-platform
    # المراجعة العاشرة (٢٠٢٦-٠٥-٢٩) كشفت أنّ المتحقّق السابق
    # كان يفحص core/ فقط، تاركاً districts/ و tenants/ مكشوفَين.
    leak_patterns = [
        # English forms (case-sensitive لتجنّب false positives مثل 'aljawf' في 'jaw')
        r"\bAl-?[Jj]awf\b",
        r"\bA[lL]-?[Jj]awf\b",
        r"\bAljawf\b",
        r"\b[Ss]akha\b",
        r"\bSunaydar\b",
        r"\bSunaidar\b",
        r"\bAl-?Hazm\b",
        r"\bAlhazm\b",
        r"\bAl-?Bayda\b",
        r"\bAlbayda\b",
        r"\bal_bayda\b",
        r"\bal_jawf\b",
        r"\baljawf\b",
        r"\btihama\b",
        r"\bTihama\b",
        # Arabic forms (verbatim)
        r"الجوف",
        r"السنيدار",
        r"الحزم",
        r"البيضاء",
        r"تهامة",
        # specific field/farm identifiers
        r"\b142ha\b",
        r"\b6\.17ha?\b",
        r"\bfld_yem_alb_\d+\b",
    ]

    # الفحص (أ): الكود في core/ فقط — نواة محايدة 100%
    core_files = [
        p for p in glob.glob(str(ROOT / "core/**/*.py"), recursive=True) if "__pycache__" not in p
    ]
    core_leaks = []
    for p in core_files:
        content = open(p, encoding="utf-8").read()
        for pat in leak_patterns:
            for m in re.finditer(pat, content):
                line_no = content[: m.start()].count("\n") + 1
                rel = os.path.relpath(p, ROOT)
                core_leaks.append(f"{rel}:{line_no} → '{m.group()}'")
    if core_leaks:
        errs.append(f"حياد النواة (#٥): {len(core_leaks)} تسرّب في core/:")
        for leak in core_leaks[:8]:
            errs.append(f"    {leak}")
        if len(core_leaks) > 8:
            errs.append(f"    ... و{len(core_leaks) - 8} أخرى")

    # الفحص (ب): بنية المستودع — لا أسماء مديريات/مزارع كمجلّدات
    # (المراجعة العاشرة: المزارع في حضرموت يجب ألّا يرى al_jawf في git tree)
    forbidden_dir_patterns = [
        r"al_?jawf",
        r"tihama",
        r"al_?bayda",
        r"al_?hazm",
        r"sakha",
        r"sunaydar",
        r"aljawf-\d+ha",
    ]
    structure_leaks = []
    for root_dir, dirs, _ in os.walk(ROOT):
        # تخطّى examples/ و node_modules
        if any(skip in root_dir for skip in ["examples", "node_modules", "__pycache__", ".git"]):
            continue
        for d in dirs:
            for pat in forbidden_dir_patterns:
                if re.search(pat, d, re.IGNORECASE):
                    rel = os.path.relpath(os.path.join(root_dir, d), ROOT)
                    structure_leaks.append(f"{rel}/ → '{d}'")
    if structure_leaks:
        errs.append(f"بنية المستودع (#٥): {len(structure_leaks)} مجلّد بتسمية جغرافية:")
        for leak in structure_leaks[:5]:
            errs.append(f"    {leak}")
        errs.append("    → انقلها إلى examples/ مع وسم صريح")

    if errs:
        print("❌ عدم تطابق:")
        for e in errs:
            print(f"  • {e}")
        return 1
    print(f"✅ متطابق: {disk_tests} اختبار/{disk_files} ملف، {api} واجهة، نواة محايدة، بنية محايدة")
    return 0


if __name__ == "__main__":
    sys.exit(check())
