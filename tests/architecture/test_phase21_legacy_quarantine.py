from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "architecture" / "legacy_path_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("legacy_path_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_quarantine_audit_has_no_unapproved_runtime_findings():
    module = load_module()
    assert module.audit(ROOT) == []


def test_legacy_quarantine_allowlist_exists():
    allowlist = ROOT / "architecture" / "legacy_quarantine_allowlist.json"
    assert allowlist.exists()
    text = allowlist.read_text(encoding="utf-8")
    assert "allowed" in text
    assert "services/sahool-platform/api/main.py" in text
