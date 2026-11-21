"""بوّابة: صيغ ضغط البخار/ET0 داخل محرّك الطقس فقط (WS-C.1b boundary)."""

from __future__ import annotations

import importlib.util
import json
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
    # WS-C.1b ratchet: ``_et0_from_weather_payload`` رُحِّل إلى منتج المحرّك (مستهلِك لا
    # مُنتِج محلّيّ) ⇒ حُذفت heuristic الاسم ``_et0_from*``، فلم يعد يُرصَد كنواة.
    assert not mod._defines_weather_formula("def _et0_from_weather_payload(): pass")
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


def test_zero_legacy_allowlist_is_empty_and_locked():
    """WS-C.1c Zero-Legacy LOCK: كلّ نوى ET0 رُحِّلت للمحرّك ⇒ allowlist فارغة أبداً.

    الرَّاتشِت النهائيّ: ``assert len(temporary_legacy_allowlist) == 0``. إعادة إضافة أيّ
    مدخل (حتّى «مؤقّت») تُفشِل هذا الاختبار والحارس معاً — لا نواة صيغة جديدة خارج المحرّك.
    """
    mod = _load()
    import json

    cfg = json.loads(mod._ALLOWLIST.read_text(encoding="utf-8"))
    assert len(cfg["temporary_legacy_allowlist"]) == 0, (
        "Zero-Legacy locked: temporary_legacy_allowlist must stay empty — implement any new "
        "formula in services/weather-service, do not re-add a platform-local ET0/SVP/GDD kernel."
    )
    # الحارس نفسه يفرض القفل ويبقى أخضر على الشجرة الحاليّة.
    violations, canonical_ok = mod.scan()
    assert canonical_ok and not violations


def _isolated_guard(tmp_path, monkeypatch):
    """Keep planted source faults out of the checkout and other test workers."""
    mod = _load()
    canonical = "services/weather-service/vapor_pressure.py"
    source = tmp_path / canonical
    source.parent.mkdir(parents=True)
    source.write_text("def svp(t): return 0.6108 * (17.27 + t)\n", encoding="utf-8")
    config = tmp_path / "allowlist.json"
    config.write_text(
        json.dumps({"canonical": canonical, "temporary_legacy_allowlist": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_ALLOWLIST", config)
    return mod, source, config


def test_main_rejects_formula_outside_weather_engine(tmp_path, monkeypatch, capsys):
    mod, _, _ = _isolated_guard(tmp_path, monkeypatch)
    assert mod.main() == 0
    capsys.readouterr()
    copied = tmp_path / "services/sahool-platform/api/parallel_et0.py"
    copied.parent.mkdir(parents=True)
    copied.write_text("def local_et0(t): return 0.0023 * (t + 17.8)\n", encoding="utf-8")
    assert mod.main() == 1
    diagnostic = capsys.readouterr().err
    assert "SVP/ET0/GDD kernel outside the Weather Engine" in diagnostic
    assert "services/sahool-platform/api/parallel_et0.py" in diagnostic


def test_main_rejects_missing_canonical_fingerprint(tmp_path, monkeypatch, capsys):
    mod, source, _ = _isolated_guard(tmp_path, monkeypatch)
    assert mod.main() == 0
    capsys.readouterr()
    source.write_text("def svp(t): return t\n", encoding="utf-8")
    assert mod.main() == 1
    assert "canonical vapor_pressure.py lost the SVP fingerprint" in capsys.readouterr().err


def test_main_rejects_reopened_legacy_allowlist(tmp_path, monkeypatch, capsys):
    mod, _, config = _isolated_guard(tmp_path, monkeypatch)
    assert mod.main() == 0
    capsys.readouterr()
    cfg = json.loads(config.read_text(encoding="utf-8"))
    cfg["temporary_legacy_allowlist"] = [
        {
            "path": "services/sahool-platform/api/parallel_et0.py",
            "owner": "fixture",
            "expires": "2026-11-30",
            "purpose": "A dated exception cannot reopen the zero-legacy lock",
        }
    ]
    config.write_text(json.dumps(cfg), encoding="utf-8")
    assert mod.main() == 1
    assert "Zero-Legacy is LOCKED" in capsys.readouterr().err


def test_stage_kc_policy_is_not_an_et0_kernel(tmp_path, monkeypatch):
    mod, _, _ = _isolated_guard(tmp_path, monkeypatch)
    season = tmp_path / "services/sahool-platform/core/season_phenology.py"
    season.parent.mkdir(parents=True)
    season.write_text(
        "def stage_kc(card, stage): return card['stage_kc_map'][stage]\n",
        encoding="utf-8",
    )
    assert mod.main() == 0
