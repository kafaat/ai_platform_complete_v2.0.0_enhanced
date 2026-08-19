import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "services/decision-service/migrations"


def test_decision_service_numeric_migration_prefixes_are_unique():
    seen = {}
    duplicates = []
    for path in sorted(MIG.glob("*.sql")):
        m = re.match(r"^(\d+)_", path.name)
        assert m, f"migration lacks numeric prefix: {path.name}"
        number = m.group(1)
        if number in seen:
            duplicates.append((number, seen[number], path.name))
        else:
            seen[number] = path.name
    assert not duplicates, f"duplicate decision-service migration numbers: {duplicates}"
