from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "services" / "sahool-platform"
BASELINE_PATH = ROOT / "docs" / "architecture" / "platform_python_module_baseline.json"


def _current_platform_modules():
    modules = []
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        if rel.startswith("tests/") or "/tests/" in rel or rel.startswith("examples/"):
            continue
        modules.append(rel)
    return sorted(modules)


def test_platform_python_module_budget_does_not_grow():
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    current = _current_platform_modules()
    assert len(current) <= int(baseline["baseline_python_module_count"]), (
        f"sahool-platform Python module count grew from {baseline['baseline_python_module_count']} to {len(current)}. "
        "Add new domain code to its owner service, or deliberately update the extraction baseline."
    )


def test_no_new_untracked_platform_modules():
    baseline = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["modules"])
    current = set(_current_platform_modules())
    added = sorted(current - baseline)
    assert not added, (
        "New sahool-platform modules must be justified in docs/architecture/platform_python_module_baseline.json: "
        + repr(added[:20])
    )
