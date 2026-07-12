from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "architecture" / "source_of_truth_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("source_of_truth_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_source_of_truth_audit_passes():
    module = load_module()
    assert module.audit(ROOT) == []


def test_field_twin_is_marked_as_derived_view():
    text = (ROOT / "services" / "sahool-platform" / "core" / "field_twin.py").read_text(
        encoding="utf-8"
    )
    assert "DERIVED_VIEW" in text
    assert "CanonicalFieldState remains authoritative" in text
