"""S5 shrink witness: retired Farmonaut platform provider must not return.

The old connector had no production consumer.  S5 retires the provider identity
rather than preserving dead platform-owned outbound authority.  This test is the
end-state witness replacing the old connector behavior tests.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_retired_farmonaut_provider_is_absent_and_unimported():
    retired = ROOT / "services/sahool-platform/core/connectors/farmonaut.py"
    assert not retired.exists()
    offenders = []
    for p in sorted((ROOT / "services").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if "/tests/" in rel or p.name.startswith("test_"):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(
            r"(?:from|import)\\s+[^\\n]*core\\.connectors\\.farmonaut|FarmonautConnector", txt
        ):
            offenders.append(rel)
    assert offenders == []
