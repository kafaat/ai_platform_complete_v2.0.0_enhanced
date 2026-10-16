"""Stored trace identity must survive public result projections; no DB claims."""

import ast
import importlib.util
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CORRELATION = UUID("21ff8426-f30e-4ff2-b8f9-9d69655fd4b4")


def _load_function(relative_path, name):
    # Pure row projections are extracted to avoid booting unrelated API routes.
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"Any": object}
    exec(compile(ast.Module(body=[function], type_ignores=[]), relative_path, "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize(
    "path,name",
    [
        ("services/decision-service/persistence.py", "_authoritative_review"),
        ("services/decision-service/persistence.py", "_authoritative_execution_plan"),
        ("services/decision-service/persistence.py", "_authoritative_dispatch_authorization"),
        ("services/decision-service/persistence.py", "_authoritative_execution_request"),
        ("services/sahool-platform/api/routers/decision_record.py", "_shape_decision_row"),
        ("services/sahool-platform/api/routers/decision_dispatch.py", "_shape_dispatch_row"),
        ("services/sahool-platform/api/routers/decision_dispatch.py", "_shape_ledger_row"),
    ],
)
@pytest.mark.parametrize("identity", [CORRELATION, None])
def test_persisted_correlation_survives_projection(path, name, identity):
    function = _load_function(path, name)
    # Only representation conversion is under test; unrelated row keys are null.
    row = defaultdict(lambda: None, correlation_id=identity)
    result = function(row, replay=True) if name.startswith("_authoritative") else function(row)
    assert result["correlation_id"] == (str(identity) if identity else None)
    assert row["correlation_id"] == identity
