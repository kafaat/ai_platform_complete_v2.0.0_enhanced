from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "certification" / "validate_certification_matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_certification_matrix", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_certification_matrix_is_honest_and_pending():
    module = load_module()
    assert module.validate(ROOT / "PRODUCTION_CERTIFICATION_MATRIX.md") == []


def test_certification_matrix_contains_soak_columns():
    text = (ROOT / "PRODUCTION_CERTIFICATION_MATRIX.md").read_text(encoding="utf-8")
    assert "7-day soak" in text
    assert "14-day soak" in text
    assert "PENDING" in text
