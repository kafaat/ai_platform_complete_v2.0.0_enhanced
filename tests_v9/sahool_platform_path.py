from __future__ import annotations

import sys
from pathlib import Path


def ensure_platform_path() -> None:
    root = Path(__file__).resolve().parents[1]
    platform = root / "services" / "sahool-platform"
    if str(platform) not in sys.path:
        sys.path.insert(0, str(platform))
