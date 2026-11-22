"""F-D10 / F-D11 — the farm ledger's preview boundary is stated, and stock moves only one way.

F-D10: ``autowrite-preview`` builds a ledger payload and nothing in the repository applies it.
With ``FEATURE_OPERATION_LEDGER_AUTOWRITE`` on it still answered ``would_persist: true``, which
claims a writer that does not exist. The answer now says what was computed, that nothing was
written, and which human step writes it.

F-D11: the inventory projection sums input quantities and never deducts. With
``FEATURE_LEDGER_INVENTORY_SYNC`` on, every line lost its ``disabled_reason`` as if it were
posted. The only stock write is the explicit, flagged step on ``POST /farm-ledger/operations``
(``FEATURE_LEDGER_INVENTORY_DEDUCTION``, OFF by default); its live proof is
``tests_v9/test_farm_ledger_inventory_deduction_live_pg.py``. These tests are pure: no
database, no stand-in connection.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from core.farm_closed_loop import ResourceUse, build_inventory_projection

PLATFORM = Path(__file__).resolve().parents[1]
ROUTER = PLATFORM / "api" / "routers" / "farm_operations_ledger.py"
REPO = PLATFORM.parents[1]
DEDUCTION_FLAG = "FEATURE_LEDGER_INVENTORY_DEDUCTION"


def _router():
    from api import main as api_main
    from api.routers import farm_operations_ledger

    return api_main, farm_operations_ledger


def _user():
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id="u-boundary",
        tenant_id="00000000-0000-0000-0000-00000000b0d1",
        role=UserRole.OWNER,
        name_ar="مالك",
    )


def _function(name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {ROUTER}")


# ── F-D10: the autowrite preview says it wrote nothing and has no consumer ──────────────


def test_autowrite_preview_with_flag_on_does_not_claim_a_writer(monkeypatch):
    api_main, router = _router()
    monkeypatch.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")
    monkeypatch.setenv("FEATURE_OPERATION_LEDGER_AUTOWRITE", "true")
    monkeypatch.setattr(api_main, "_DB_POOL", None)
    req = router.OperationEventIn(
        occurred_on=date(2026, 11, 1), operation_type="fertilization", farm_id="farm-1"
    )
    out = asyncio.run(router.operation_autowrite_preview(req, user=_user()))

    assert out["ledger_payload"]["autowrite_eligible"] is True  # computed
    assert out["autowrite_enabled"] is True
    assert out["persisted"] is False  # nothing written
    assert out["would_persist"] is False  # no consumer applies it, flag or not
    assert out["autowrite_consumer"] is None
    assert out["disabled_reason"] == "no_autowrite_consumer"
    assert out["write_path"]["endpoint"] == "POST /api/v1/farm-ledger/operations"
    assert out["provenance"]["persisted"] is False


def test_autowrite_preview_with_flag_off_names_the_flag(monkeypatch):
    api_main, router = _router()
    monkeypatch.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")
    monkeypatch.delenv("FEATURE_OPERATION_LEDGER_AUTOWRITE", raising=False)
    monkeypatch.setattr(api_main, "_DB_POOL", None)
    req = router.OperationEventIn(occurred_on=date(2026, 11, 1), operation_type="irrigation")
    out = asyncio.run(router.operation_autowrite_preview(req, user=_user()))
    assert (out["persisted"], out["would_persist"]) == (False, False)
    assert out["disabled_reason"] == "feature_flag_off"


def test_autowrite_preview_body_never_writes():
    """The preview reads the field scope at most; no INSERT/UPDATE and no deduction call."""
    fn = _function("operation_autowrite_preview")
    src = ast.unparse(fn)
    for forbidden in ("INSERT", "UPDATE", "DELETE", ".execute(", "apply_inventory_deduction"):
        assert forbidden not in src, forbidden
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
    }
    assert not called & {"create_operation_ledger_record", "_persist", "_idempotent"}


# ── F-D11: the projection says it is a projection, flag or not ─────────────────────────


def test_inventory_projection_lines_stay_unposted_with_sync_flag_on():
    lines = build_inventory_projection(
        [ResourceUse("fertilizer", 5.0, "kg", 10.0, "item-1")], sync_enabled=True
    )
    assert lines[0].posting_mode == "projection_only"
    assert lines[0].disabled_reason == "projection_only"


def test_inventory_projection_answer_without_db_states_no_write(monkeypatch):
    api_main, router = _router()
    monkeypatch.setenv("FEATURE_FARM_OPERATIONS_LEDGER", "true")
    monkeypatch.setenv("FEATURE_LEDGER_INVENTORY_SYNC", "true")
    monkeypatch.setattr(api_main, "_DB_POOL", None)
    out = asyncio.run(router.get_inventory_projection("season-x", user=_user()))
    assert out["inventory_write"] is False
    assert out["write_path"]["flag"] == DEDUCTION_FLAG
    assert out["write_path"]["flag_enabled"] is False


def test_inventory_projection_body_never_writes():
    src = ast.unparse(_function("get_inventory_projection"))
    for forbidden in ("INSERT", "UPDATE", "DELETE", ".execute(", "apply_inventory_deduction"):
        assert forbidden not in src, forbidden


# ── F-D11: the deduction step — pure planning and preconditions ────────────────────────


def _inputs(*rows):
    from types import SimpleNamespace

    return [
        SimpleNamespace(
            input_type="fertilizer",
            inventory_item_id=item,
            inventory_batch_id=batch,
            quantity=qty,
            unit=unit,
        )
        for batch, item, qty, unit in rows
    ]


def test_deduction_plan_groups_by_named_batch_and_skips_unnamed():
    from core.farm_operations_ledger import plan_inventory_deduction

    plan = plan_inventory_deduction(
        _inputs(("b-2", "i-1", 1.5, "kg"), (None, "i-1", 9.0, "kg"), ("b-1", None, 2, "kg"))
        + _inputs(("b-2", "i-1", 0.5, " KG "))
    )
    assert [(line.batch_id, line.quantity) for line in plan] == [
        ("b-1", Decimal("2.000")),
        ("b-2", Decimal("2.000")),
    ]
    assert plan[1].item_id == "i-1" and plan[0].item_id is None


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([("b-1", "i-1", 0.0, "kg")], "inventory_deduction_quantity_must_be_positive"),
        ([("b-1", "i-1", 0.0004, "kg")], "inventory_deduction_quantity_must_be_positive"),
        ([("b-1", "i-1", 1, "kg"), ("b-1", "i-2", 1, "kg")], "inventory_batch_item_mismatch"),
        ([("b-1", "i-1", 1, "kg"), ("b-1", "i-1", 1, "L")], "inventory_batch_unit_mismatch"),
    ],
)
def test_deduction_plan_refuses_ambiguous_lines(rows, reason):
    from core.farm_operations_ledger import InventoryDeductionRefused, plan_inventory_deduction

    with pytest.raises(InventoryDeductionRefused) as caught:
        plan_inventory_deduction(_inputs(*rows))
    assert caught.value.detail["reason"] == reason


@pytest.mark.parametrize(
    ("enabled", "has_batches", "idem", "status", "expected"),
    [
        (False, True, None, "completed", None),  # flag off: nothing to refuse, nothing written
        (True, False, None, "completed", None),  # no named batch: the old path, untouched
        (True, True, None, "completed", 428),
        (True, True, "k", "planned", 409),
        (True, True, "k", "cancelled", 409),
        (True, True, "k", "completed", None),
    ],
)
def test_deduction_preconditions(enabled, has_batches, idem, status, expected):
    from core.farm_operations_ledger import inventory_deduction_refusal

    got = inventory_deduction_refusal(
        enabled=enabled, has_batches=has_batches, idempotency_key=idem, status=status
    )
    assert (got[0] if got else None) == expected


def test_deduction_flag_is_off_by_default_and_never_set_truthy_in_repo(monkeypatch):
    _, router = _router()
    monkeypatch.delenv(DEDUCTION_FLAG, raising=False)
    assert router._INVENTORY_DEDUCTION_FLAG == DEDUCTION_FLAG
    assert router._flag_enabled(DEDUCTION_FLAG) is False
    truthy = ("=1", "=true", "=yes", "=on", ": '1'", ': "1"', ": true", ': "true"')
    hits = []
    for pattern in ("*.env*", "*.yml", "*.yaml", "*.toml", "Dockerfile*"):
        for path in REPO.rglob(pattern):
            if "node_modules" in path.parts or ".git" in path.parts or not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                compact = line.replace(" ", "").lower()
                if DEDUCTION_FLAG.lower() in compact and any(
                    t.replace(" ", "") in compact for t in truthy
                ):
                    hits.append(f"{path.relative_to(REPO)}: {line.strip()}")
    assert not hits, hits


def test_deduction_is_called_only_from_the_operation_create_path():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    callers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef) and fn.name != "_persist":
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "apply_inventory_deduction"
                ):
                    callers.add(fn.name)
    assert callers == {"create_operation_ledger_record"}


def test_request_digest_unchanged_for_inputs_without_a_batch():
    """Receipts stored before ``inventory_batch_id`` existed still replay under their key."""
    _, router = _router()
    req = router.OperationLedgerIn(
        operation_date=date(2026, 11, 1),
        operation_type="fertilization",
        farm_id="farm-1",
        inputs=[{"input_type": "fertilizer", "quantity": 2, "unit": "kg"}],
    )
    legacy = req.model_dump(mode="json", exclude={"task_id"})
    for row in legacy["inputs"]:
        row.pop("inventory_batch_id")
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert router._request_digest(req) == expected

    named = req.model_copy(
        update={"inputs": [req.inputs[0].model_copy(update={"inventory_batch_id": "b-1"})]}
    )
    assert router._request_digest(named) != expected
