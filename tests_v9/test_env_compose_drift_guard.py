"""حارس انجراف env↔compose (السجل التشغيليّ #3) + برهان سلبيّ.

يفرض شروط المالك الأربعة على `scripts/ci/env_compose_drift_guard.py`:
  ① النطاق الذكيّ: يُكتشَف المقروء **بلا افتراضيّ** فقط (getenv بلا default / environ[] / environ.get بلا default)؛
     ذوات الافتراضيّات خارج النطاق (برهان سلبيّ: متغيّر بافتراضيّ لا يُلتقَط).
  ② المطابقة ضدّ compose **و** .env.example (المُصنَّف في .env.example ⇒ «محقون» لا «مفقود»).
  ③ قائمة استثناء معلَّبة: كلّ مدخل بـ{category, why} (تُراجَع كمراجعة كود).
  ④ حازم الآن: الحالة الحاليّة نظيفة (missing(unclassified)=0)، وبرهان سلبيّ أنّ متغيّراً جديداً غير مُصنَّف يُحمِّر.

فحص وحدة صرف — ``pytest -m unit`` (لا شبكة/قاعدة). يُشغَّل الحارس عبر importlib بلا side-effects.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_GUARD = _ROOT / "scripts" / "ci" / "env_compose_drift_guard.py"
_ALLOWLIST = _ROOT / "scripts" / "ci" / "env_compose_drift_allowlist.json"


def _load_guard():
    spec = importlib.util.spec_from_file_location("env_compose_drift_guard", _GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_guard_and_allowlist_exist():
    assert _GUARD.is_file(), "حارس الانجراف مفقود"
    assert _ALLOWLIST.is_file(), "قائمة الاستثناء مفقودة"


def test_condition1_only_no_default_reads_detected():
    """① يلتقط المقروء بلا افتراضيّ فقط — برهان سلبيّ: المقروء بافتراضيّ خارج النطاق."""
    g = _load_guard()
    text = (
        'a = os.getenv("REQUIRED_NO_DEFAULT")\n'
        'b = os.environ["REQUIRED_INDEX"]\n'
        'c = os.environ.get("REQUIRED_GET")\n'
        'd = os.getenv("HAS_DEFAULT", "x")\n'  # برهان سلبيّ: بافتراضيّ ⇒ لا يُلتقَط
        'e = os.environ.get("HAS_DEFAULT2", "y")\n'  # برهان سلبيّ
    )
    found = g.required_env_vars(text)
    assert {"REQUIRED_NO_DEFAULT", "REQUIRED_INDEX", "REQUIRED_GET"} <= found
    assert "HAS_DEFAULT" not in found, "المقروء بافتراضيّ يجب أن يخرج من النطاق (①)"
    assert "HAS_DEFAULT2" not in found


def test_condition2_env_example_classified_as_injected():
    """② الموثَّق في .env.example (غائب من compose) ⇒ محقون لا مفقود."""
    g = _load_guard()
    required = {"SECRET_X": ["svc/a.py"]}
    buckets = g.classify(
        required, compose_provided=set(), env_declared={"SECRET_X"}, allowlist=set()
    )
    assert not buckets["missing"], "الموثَّق في .env.example يجب ألّا يكون مفقوداً"
    assert [r["var"] for r in buckets["injected"]] == ["SECRET_X"]


def test_condition3_allowlist_every_entry_has_category_and_why():
    """③ كلّ مدخل استثناء مُبرَّر: {category, why} مطلوبان (يُراجَع كمراجعة كود)."""
    data = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
    intentional = data.get("intentional", {})
    assert intentional, "قائمة الاستثناء فارغة — لا مدخلات مُصنَّفة"
    for var, meta in intentional.items():
        assert isinstance(meta, dict), f"{var}: القيمة يجب أن تكون كائناً {{category, why}}"
        assert meta.get("category") in {"A", "B", "C", "D"}, f"{var}: فئة غير صالحة"
        assert isinstance(meta.get("why"), str) and len(meta["why"]) >= 15, f"{var}: تبرير ناقص"


def test_condition4_current_tree_is_clean():
    """④ الحالة الحاليّة نظيفة: لا مفقود غير مُصنَّف (الحارس أخضر على الشجرة)."""
    g = _load_guard()
    res = g._scan_repo()
    missing = [r["var"] for r in res["buckets"]["missing"]]
    assert not missing, f"مفقود غير مُصنَّف (صنّفه في القائمة أو زوّده): {missing}"


def test_condition4_negative_proof_new_unclassified_var_would_trip():
    """④ برهان سلبيّ: متغيّر مقروء بلا افتراضيّ، غائب من compose/.env.example/القائمة ⇒ مفقود (يُحمِّر)."""
    g = _load_guard()
    required = {"BRAND_NEW_UNCLASSIFIED_VAR": ["svc/new.py"]}
    buckets = g.classify(required, compose_provided=set(), env_declared=set(), allowlist=set())
    assert [r["var"] for r in buckets["missing"]] == ["BRAND_NEW_UNCLASSIFIED_VAR"], (
        "متغيّر جديد غير مُصنَّف يجب أن يقع في «مفقود» — وإلّا الحارس بلا أسنان"
    )
    # ومع تصنيفه في القائمة يخرج من «مفقود» (المسار المقصود للإصلاح).
    ok = g.classify(required, set(), set(), allowlist={"BRAND_NEW_UNCLASSIFIED_VAR"})
    assert not ok["missing"], "التصنيف في القائمة يجب أن يُخرِجه من المفقود"
