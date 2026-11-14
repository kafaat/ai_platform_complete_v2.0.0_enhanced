"""A farm-book receipt belongs to the field of the entry it backs (owner priority 7).

Before this change the link checked only the document's tenant and category, so an expense
on field A could cite a receipt recorded on field B of the same tenant, and the per-field
cost report would carry evidence from another field. The rule now enforced when an entry is
written (``_assert_receipt`` in ``api/routers/simple_farm_book.py``):

* a document with no field is a *shared receipt*, one purchase spanning several fields or
  the whole farm, and may back any entry of the tenant;
* a document recorded on a field may back only an entry on that same field; a farm-level
  entry (no field) cannot cite a field's receipt, because the report would then lose which
  field the evidence belongs to;
* linking a document is reading it: the caller must hold ``DOCUMENT_VIEW`` on the entry's
  farm (role and ``farm_ids_access``), decided on the server before the document is read;
* a reversal is checked against the field it inherits from the original.

The decisions are pure functions and are tested directly; where they are wired into the
write path is checked on the router's syntax tree.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CORE = os.fspath(ROOT / "services" / "sahool-platform")
ROUTER = ROOT / "services" / "sahool-platform" / "api" / "routers" / "simple_farm_book.py"


@pytest.fixture(scope="module")
def mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.routers.simple_farm_book as m

    return m


def _user(role: str = "owner", farms: list[str] | None = None):
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id="u_receipt",
        tenant_id="00000000-0000-0000-0000-0000000000aa",
        role=UserRole(role),
        name_ar="مختبر",
        farm_ids_access=farms or [],
        is_active=True,
    )


def test_a_receipt_recorded_on_another_field_is_refused(mod):
    assert mod._receipt_field_refusal("field-b", "field-a") == "receipt_field_mismatch"


def test_a_field_receipt_cannot_back_a_farm_level_entry(mod):
    assert mod._receipt_field_refusal("field-b", None) == "receipt_field_mismatch"
    assert mod._receipt_field_refusal("field-b", "  ") == "receipt_field_mismatch"


def test_a_receipt_on_the_same_field_is_accepted(mod):
    assert mod._receipt_field_refusal("field-a", "field-a") is None
    assert mod._receipt_field_refusal(" field-a ", "field-a") is None


def test_a_shared_receipt_without_a_field_backs_any_entry(mod):
    for entry_field in ("field-a", None):
        assert mod._receipt_field_refusal(None, entry_field) is None
        assert mod._receipt_field_refusal("", entry_field) is None


def test_linking_needs_document_view_on_the_entry_farm(mod):
    # PLATFORM_ADMIN holds neither ACTIVITY_EXECUTE nor DOCUMENT_VIEW; a manager limited to
    # another farm holds the role permission but not this farm.
    assert not mod._may_link_receipt(_user("platform_admin"), "farm-1")
    assert not mod._may_link_receipt(_user("manager", farms=["farm-9"]), "farm-1")
    inactive = _user("owner")
    inactive.is_active = False
    assert not mod._may_link_receipt(inactive, "farm-1")
    assert mod._may_link_receipt(_user("manager", farms=["farm-1"]), "farm-1")
    for role in ("owner", "manager", "worker"):  # the roles that may write entries
        assert mod._may_link_receipt(_user(role), "farm-1"), role


def test_writing_an_entry_needs_activity_execute_on_its_farm(mod):
    assert not mod._may_write_on_farm(_user("manager", farms=["farm-9"]), "farm-1")
    assert not mod._may_write_on_farm(_user("viewer"), "farm-1")
    assert mod._may_write_on_farm(_user("manager", farms=["farm-1"]), "farm-1")
    for role in ("owner", "manager", "worker"):
        assert mod._may_write_on_farm(_user(role), "farm-1"), role


def _function(source: str, name: str) -> ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name
    )


def _calls_in_order(fn: ast.AST) -> list[str]:
    calls = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            f = n.func
            name = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            calls.append((n.lineno, n.col_offset, name))
    return [name for _, _, name in sorted(calls)]


def test_the_permission_is_decided_before_the_document_is_read_and_the_field_is_compared():
    calls = _calls_in_order(_function(ROUTER.read_text(encoding="utf-8"), "_assert_receipt"))
    assert calls.index("_may_link_receipt") < calls.index("fetchrow")
    assert calls.index("fetchrow") < calls.index("_receipt_field_refusal")


def test_the_farm_is_authorised_before_any_connection_and_the_field_must_be_on_it():
    source = ROUTER.read_text(encoding="utf-8")
    create = _calls_in_order(_function(source, "create_entry"))
    assert create.index("_may_write_on_farm") < create.index("tenant_connection")
    scope = ast.get_source_segment(source, _function(source, "_assert_scope")) or ""
    assert "SELECT farm_id FROM fields WHERE field_id=$1" in scope
    assert '"field_not_in_farm"' in scope
    receipt = _calls_in_order(_function(source, "_assert_receipt"))
    assert receipt.count("_may_link_receipt") == 2, (
        "entry farm before the read, document farm after"
    )


def test_the_receipt_is_checked_on_every_new_entry_after_the_reversal_inherits_its_field():
    source = ROUTER.read_text(encoding="utf-8")
    calls = [
        c for c in _calls_in_order(_function(source, "create_entry")) if c.startswith("_assert")
    ]
    assert calls.index("_assert_reversal") < calls.index("_assert_receipt")
    scope = ast.get_source_segment(source, _function(source, "_assert_scope")) or ""
    assert "documents" not in scope, "the receipt lookup lives in one place, after inheritance"
    receipt = ast.get_source_segment(source, _function(source, "_assert_receipt")) or ""
    assert "AND d.category IN ('image','report','other')" in receipt
