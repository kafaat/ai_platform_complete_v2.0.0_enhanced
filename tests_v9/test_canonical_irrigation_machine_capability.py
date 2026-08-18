"""S5 end-state witness for M2.5 machine capability.

The standalone platform compute module had no executable consumer.  Persisted canonical
machine capability tables remain; the dead duplicate calculation module must not return.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_m25_persisted_machine_capability_remains_without_dead_compute_module():
    assert not (
        ROOT / "services/sahool-platform/api/canonical_irrigation_machine_capability.py"
    ).exists()
    migration = (ROOT / "migrations/v172_irrigation_machine_capability.sql").read_text(
        encoding="utf-8"
    )
    assert "canonical_irrigation_machine_capabilities" in migration
    assert "irrigation_machine_spans" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
