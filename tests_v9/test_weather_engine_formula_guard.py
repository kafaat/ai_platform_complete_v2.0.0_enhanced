"""بوّابة: صيغ ضغط البخار/ET0 داخل محرّك الطقس فقط (WS-C.1b boundary)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_GEN = Path(__file__).resolve().parent.parent / "scripts" / "ci" / "weather_engine_formula_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_weformula", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_guard_passes_current_tree():
    mod = _load()
    violations, canonical_ok = mod.scan()
    assert canonical_ok, "canonical vapor_pressure.py must hold the SVP fingerprint"
    assert not violations, f"formula outside Weather Engine / allowlist: {violations}"


def test_ast_detects_svp_et0_and_gdd_kernels():
    mod = _load()
    # ET0/SVP (C.1a/b)
    assert mod._defines_weather_formula("def penman_monteith_et0(): pass")
    assert mod._defines_weather_formula("def _svp(t): return 0")
    assert mod._defines_weather_formula("def hargreaves_x(): pass")
    # WS-C.1b: ``hargreaves`` كسلسلة فرعيّة ⇒ تُمسَك الأغلفة المفوِّضة أيضاً (لا تفلت بالتسمية)
    assert mod._defines_weather_formula("def _hargreaves_et0(): pass")
    assert mod._defines_weather_formula("def et0_hargreaves(): pass")
    # مُنتِج ET0 محلّيّ (اسم ``_et0_from*``) ⇒ يُرصَد ويُوثَّق حتى يُفوَّض
    assert mod._defines_weather_formula("def _et0_from_weather_payload(): pass")
    # GDD kernels (C.1c) — النواة لا السياسة
    assert mod._defines_weather_formula("def gdd_daily(): pass")
    assert mod._defines_weather_formula("def daily_gdd(): pass")
    assert mod._defines_weather_formula("def gdd_day(): pass")
    # سياسة/دوالّ عامّة لا تُكتشَف (عتبات محصول = سياسة Season مسموحة)
    assert not mod._defines_weather_formula("def compute_something(): pass")
    assert not mod._defines_weather_formula("def gdd_stage_thresholds(): pass")
    # مُفوِّضات المحرّك (تستهلك المنتج الكنسيّ) لا تُكتشَف كنواة
    assert not mod._defines_weather_formula("def get_et0_series(): pass")
    assert not mod._defines_weather_formula("def get_et0_product(): pass")


def test_hargreaves_math_fingerprint_catches_inline_reimpl():
    mod = _load()
    # نواة Hargreaves مضمّنة (سطريّة) بلا اسم مطابق ⇒ تُمسَك بالبصمة الرياضيّة
    # (0.0023 + 17.8 معاً) لا بالاسم — الثغرة التي أفلت منها خادم MCP.
    inline = "def anything(t):\n    return 0.0023 * (t + 17.8) * 1.0\n"
    assert mod._has_hargreaves_fingerprint(inline)
    # ملفّ بلا كلا الماركرين ⇒ لا بصمة (لا إيجابيّات كاذبة)
    assert not mod._has_hargreaves_fingerprint("x = 0.0023  # unrelated coefficient")
    assert not mod._has_hargreaves_fingerprint("y = 17.8  # unrelated threshold")


def test_allowlist_entries_have_owner_and_expiry():
    mod = _load()
    import json

    cfg = json.loads(mod._ALLOWLIST.read_text(encoding="utf-8"))
    for e in cfg["temporary_legacy_allowlist"]:
        assert e.get("owner") and e.get("expires") and e.get("purpose"), e
