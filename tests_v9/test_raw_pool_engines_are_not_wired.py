"""محرّكا الاتّصال الخام لا يُوصَّلان بمسار طلبٍ إلّا مع ضبط GUC المستأجِر.

`TENANT-GUC-HELPER-NEVER-CALLED-01` قِيس وأُغلِق بالقياس (2026-09-13):

- `api/field_lifecycle.py` و`api/trueup.py` يكتسبان اتّصالاً خاماً من الـpool **بلا**
  `set_config('app.current_tenant', …)`، فتحت الدور المُقيَّد (`sahool_app`، FORCE RLS)
  تُرجِع استعلاماتُهما صفراً أو تُرفَض كتاباتُهما — وتعليقاتُهما تُعلِن ذلك حرفيّاً.
- والمقيسُ على الشجرة: `FieldLifecycleEngine` **لا يُنشَأ** في شيفرة الإنتاج إطلاقاً، و
  `TrueUpEngine` يُنشَأ في `api/main.py` **بلا pool** (`TrueUpEngine()` — compute النقيّ
  وحدَه على مسار الطلب). فلا اتّصالَ خامٍ موصولاً اليوم، والمُعينُ المذكور سابقاً
  (`_apply_tenant_guc`) حُذِف في #997 بعد أن ثبت أنّ أحداً لم يستدعه.

هذا الحارس يُثبِّت القياسَ: مَن يُوصِّل أحدَ المحرّكين بـpool على مسار طلبٍ يحمرّ هنا
حتّى يضبط الـGUC داخل المعاملة بالطريقة التي يضبطها بها `tenant_connection`، ثمّ يُحدِّث
هذا الاختبار **مع** الدليل. والتعليقاتُ التي تصف الشرط تبقى في المصدر فيقرؤها من يصل.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "services" / "sahool-platform" / "api"
RAW_POOL_ENGINES = {"FieldLifecycleEngine", "TrueUpEngine"}


def _production_modules() -> list[Path]:
    return sorted(
        p
        for p in API.rglob("*.py")
        if "tests" not in p.parts and not p.name.startswith("test_") and p.name != "conftest.py"
    )


def _engine_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in RAW_POOL_ENGINES:
            yield name, node


def _may_carry_a_pool(call: ast.Call) -> bool:
    """أيُّ وسيطٍ موضعيّ أو `pool=` أو مجموعةٌ مُمرَّرة (`*args` / `**kwargs`).

    `**kwargs` يُمثَّل في AST بـ`ast.keyword` عنوانُه `None`، فشرطُ `kw.arg == "pool"` وحدَه
    يعمى عنه (Copilot على #1000) — تُعامَل الخريطةُ المُمرَّرة كمخالفةٍ لأنّ الحارس لا
    يستطيع حلَّها سكونيّاً، ومَن يحتاجها يكتب `pool=` صريحةً مع ضبط الـGUC.
    """
    return bool(call.args) or any(kw.arg is None or kw.arg == "pool" for kw in call.keywords)


def test_no_raw_pool_engine_is_constructed_with_a_pool_on_a_request_path():
    wired = []
    for path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, call in _engine_calls(tree):
            if _may_carry_a_pool(call):
                wired.append(f"{path.relative_to(ROOT)}:{call.lineno} {name}(...pool)")
    assert not wired, (
        "محرّكٌ خامٌ وُصِّل بـpool بلا ضبط app.current_tenant — RLS ستُرجِع صفراً تحت "
        f"sahool_app. اضبط الـGUC داخل المعاملة كما في tenant_connection ثمّ حدِّث هذا "
        f"الاختبار مع الدليل: {wired}"
    )


def test_the_measurement_that_closed_the_gap_still_holds():
    """`TrueUpEngine()` بلا وسائط في `main.py`، و`FieldLifecycleEngine` بلا إنشاءٍ إنتاجيّ."""
    constructed: dict[str, list[str]] = {name: [] for name in RAW_POOL_ENGINES}
    for path in _production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, _call in _engine_calls(tree):
            constructed[name].append(str(path.relative_to(ROOT)))
    assert constructed["FieldLifecycleEngine"] == []
    assert constructed["TrueUpEngine"] == ["services/sahool-platform/api/main.py"]


@pytest.mark.parametrize(
    "source, wired",
    [
        ("TrueUpEngine()", False),
        ("TrueUpEngine(pool)", True),
        ("TrueUpEngine(pool=pool)", True),
        ("TrueUpEngine(*engines)", True),
        ("TrueUpEngine(**kwargs)", True),
        ("api.TrueUpEngine(**{'pool': pool})", True),
    ],
)
def test_the_predicate_sees_forwarded_mappings_not_only_a_literal_pool_keyword(
    source: str, wired: bool
):
    (call,) = [c for _n, c in _engine_calls(ast.parse(source))]
    assert _may_carry_a_pool(call) is wired, source


def test_both_engines_still_declare_the_guc_requirement_in_source():
    for rel in ("api/field_lifecycle.py", "api/trueup.py"):
        text = (ROOT / "services" / "sahool-platform" / rel).read_text(encoding="utf-8")
        assert "app.current_tenant" in text and "tenant_connection" in text, rel
