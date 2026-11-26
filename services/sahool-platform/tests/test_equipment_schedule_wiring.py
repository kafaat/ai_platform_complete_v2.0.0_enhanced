"""Exercise the equipment route's SQL and mapping with synthetic relational data.

SQLite tests the portable query and its explicit tenant join, not PostgreSQL RLS.
The existing intelligence engine's verdicts are tested separately.
"""

from __future__ import annotations

import ast
import asyncio
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit
ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "equipment.py"


def exercise(summary, maintenance):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE equipment(equipment_id TEXT, tenant_id TEXT, name TEXT, type TEXT,
            status TEXT, operating_hours REAL, purchase_date TEXT);
        CREATE TABLE equipment_maintenance(equipment_id TEXT, tenant_id TEXT, kind TEXT,
            status TEXT, scheduled_date TEXT, performed_date TEXT);
        INSERT INTO equipment VALUES ('pump-a','a','Pump','pump','operational',300,NULL);
    """)
    db.executemany("INSERT INTO equipment_maintenance VALUES (?,?,?,?,?,?)", maintenance)

    class Connection:
        async def fetch(self, sql):
            result = [dict(r) for r in db.execute(sql)]
            for row in result:
                if row.get("next_service_date") is not None:
                    row["next_service_date"] = date.fromisoformat(row["next_service_date"])
            return result

    @asynccontextmanager
    async def tenant_connection(user):
        assert user == "tenant-a"
        yield Connection()

    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    function = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_equipment"
    )
    function.decorator_list = []
    function.args.defaults = []
    for arg in function.args.args:
        arg.annotation = None
    module = ast.Module(body=[function], type_ignores=[])
    # Capture the engine input; do not implement a second service-due rule.
    scope = {
        "tenant_connection": tenant_connection,
        "summarize_equipment": lambda *, assets: SimpleNamespace(
            to_dict=lambda: {"engine_input": assets}
        ),
    }
    exec(compile(ast.fix_missing_locations(module), str(ROUTER), "exec"), scope)
    try:
        return asyncio.run(scope["list_equipment"]("tenant-a", summary))
    finally:
        db.close()


@pytest.mark.parametrize(
    "rows, expected",
    [
        ([("pump-a", "a", "scheduled", "planned", "2026-11-01", None)], "2026-11-01"),
        (
            [
                ("pump-a", "a", "scheduled", "planned", "2027-01-01", None),
                ("pump-a", "a", "scheduled", "planned", "2026-11-01", None),
            ],
            "2026-11-01",
        ),
        (
            [
                ("pump-a", "a", "scheduled", "done", "2026-01-01", "2026-01-01"),
                ("pump-a", "a", "scheduled", "cancelled", "2026-01-01", None),
                ("pump-a", "a", "repair", "planned", "2026-01-01", None),
                ("pump-a", "a", "scheduled", "planned", "2026-01-01", "2026-01-01"),
                ("pump-a", "b", "scheduled", "planned", "2026-01-01", None),
                ("pump-b", "a", "scheduled", "planned", "2026-01-01", None),
            ],
            None,
        ),
        ([("pump-a", "a", "scheduled", "planned", None, None)], None),
    ],
)
def test_recorded_schedule_reaches_engine(rows, expected):
    result = exercise(True, rows)
    asset = result["intelligence"]["engine_input"][0]
    assert asset.get("next_service_date") == expected
    assert "service_interval_hours" not in asset
    assert "last_service_hours" not in asset


def test_legacy_list_has_no_new_field():
    result = exercise(False, [("pump-a", "a", "scheduled", "planned", "2026-11-01", None)])
    assert set(result[0]) == {
        "equipment_id", "name", "type", "status", "operating_hours", "purchase_date"
    }
