"""حارس — بوّابة تباين توكِنات التصميم (WCAG): صحّة الحساب + مرور الأزواج الأساسيّة."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "ci" / "design_token_contrast_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("sahool_contrast_gate", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_contrast_ratio_known_anchors():
    g = _load()
    assert g.contrast_ratio("#000000", "#FFFFFF") == 21.0  # أقصى تباين
    assert g.contrast_ratio("#777777", "#777777") == 1.0  # نفس اللون
    # التناظر: ترتيب اللونين لا يغيّر النسبة.
    assert g.contrast_ratio("#2C1A0E", "#FBF7F0") == g.contrast_ratio("#FBF7F0", "#2C1A0E")


def test_relative_luminance_bounds():
    g = _load()
    assert round(g.relative_luminance("#FFFFFF"), 3) == 1.0
    assert round(g.relative_luminance("#000000"), 3) == 0.0


def test_parse_tokens_extracts_brand_and_adds_white():
    g = _load()
    toks = g.parse_tokens(g.TOKENS.read_text(encoding="utf-8"))
    assert toks.get("ink") == "#2C1A0E" and toks.get("gold") == "#E8A020"
    assert toks.get("white") == "#FFFFFF"  # مُضاف صراحةً (لون overlay)


def test_critical_body_text_pairs_meet_aa_today():
    g = _load()
    toks = g.parse_tokens(g.TOKENS.read_text(encoding="utf-8"))
    for fg, bg in g.CRITICAL_PAIRS:
        assert g.contrast_ratio(toks[fg], toks[bg]) >= 4.5, f"{fg}/{bg} دون AA"


def test_gate_passes_green_today():
    assert _load().run() == 0
