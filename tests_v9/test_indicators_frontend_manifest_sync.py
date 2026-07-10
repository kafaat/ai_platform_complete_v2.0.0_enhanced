"""بوّابة مزامنة: مانيفست الواجهة المُولَّد يطابق المصدر الأوحد (WS-B.2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_GEN = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "ci"
    / "generate_indicators_frontend_manifest.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_gen_fe_manifest", _GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_frontend_manifest_in_sync():
    mod = _load()
    assert mod._OUT.read_text(encoding="utf-8") == mod.render(), (
        "indicatorsRegistry.generated.ts انحرف عن config — أعِد التوليد: "
        "python scripts/ci/generate_indicators_frontend_manifest.py"
    )


def test_manifest_projection_is_public_only():
    mod = _load()
    _d, _v, public = mod.build()
    assert public
    for row in public:
        assert "formula_ref" not in row and "computation" not in row
        assert "availability" in row and "source_class" in row
