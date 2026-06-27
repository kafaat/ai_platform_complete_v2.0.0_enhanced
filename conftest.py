"""Pytest path bootstrap for the consolidated SAHOOL archive.

The sahool-platform tests import `api.*` and `core.*` as top-level packages.
When tests are executed from the repository root, Python does not automatically
add services/sahool-platform to sys.path. This keeps local/CI test collection
consistent without changing application imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (ROOT, ROOT / "services" / "sahool-platform"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
