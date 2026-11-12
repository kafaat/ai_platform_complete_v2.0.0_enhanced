"""events.entity_type: what the code emits, what Python validates and what the CHECK accepts agree.

Until this change the CHECK held 11 categories while the platform emitted 34, so the database
rejected every event for harvest lots, tasks, alerts, calibration overrides, decision records
and more. Non-critical emits swallowed that; critical ones aborted the business write. Test
doubles accept any value, so nothing caught it.

Three sources must stay equal:
  * ``ALLOWED_ENTITY_TYPES`` in services/sahool-platform/core/event_schema.py;
  * the ``wanted`` list in migrations/v51_review_round2_fixes.sql;
  * every entity_type literal a call site passes to an emit path (``_emit_domain_event``,
    ``EventBus.emit``, ``new_event``, or SQL ``emit_event(...)``), which must be a subset.

A call site whose value cannot be read statically must be a declared pass-through below.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
V51 = ROOT / "migrations" / "v51_review_round2_fixes.sql"
MANIFEST = ROOT / "migrations" / "MANIFEST.txt"

# Functions that forward an entity_type they received; the value is checked at their callers.
PASS_THROUGH = {
    ("services/sahool-platform/api/main.py", "entity_type"),
    ("services/sahool-platform/api/event_bus.py", "entity_type"),
    ("services/sahool-platform/core/event_schema.py", "entity_type"),
    ("services/sahool-platform/api/irrigation_execution_request_port.py", "args['entity_type']"),
}

_EMIT_SQL = re.compile(r"emit_event\s*\(\s*([^,]+),\s*([^,]+),", re.S)


def _allowed() -> frozenset[str]:
    sys.path.insert(0, str(PLATFORM))
    try:
        from core.event_schema import ALLOWED_ENTITY_TYPES
    finally:
        sys.path.remove(str(PLATFORM))
    return ALLOWED_ENTITY_TYPES


def _module_strings(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        value = getattr(node, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    out[target.id] = value.value
    return out


def _values(node: ast.AST, consts: dict[str, str]) -> set[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        a, b = _values(node.body, consts), _values(node.orelse, consts)
        return None if a is None or b is None else a | b
    if isinstance(node, ast.Name) and node.id in consts:
        return {consts[node.id]}
    return None


def _emitted() -> tuple[dict[str, set[str]], list[tuple[str, str, int]]]:
    found: dict[str, set[str]] = {}
    unresolved: list[tuple[str, str, int]] = []
    for base in ("services", "shared"):
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or path.name.startswith("test_") or "/node_modules/" in rel:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            consts = _module_strings(tree)
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                nodes: list[ast.AST] = []
                if name == "_emit_domain_event" and len(call.args) >= 4:
                    nodes.append(call.args[3])
                if name == "new_event" and len(call.args) >= 2:
                    nodes.append(call.args[1])
                if name in {"emit", "_emit_domain_event", "new_event", "EventEnvelope"}:
                    nodes += [k.value for k in call.keywords if k.arg == "entity_type"]
                if call.args:
                    sql = _values(call.args[0], consts)
                    match = _EMIT_SQL.search(next(iter(sql))) if sql and len(sql) == 1 else None
                    if match:
                        second = match.group(2).strip()
                        literal = re.match(r"'([^']*)'", second)
                        placeholder = re.match(r"\$(\d+)", second)
                        if literal:
                            found.setdefault(literal.group(1), set()).add(f"{rel}:{call.lineno}")
                        elif placeholder and int(placeholder.group(1)) < len(call.args):
                            nodes.append(call.args[int(placeholder.group(1))])
                for node in nodes:
                    values = _values(node, consts)
                    if values is None:
                        unresolved.append((rel, ast.unparse(node), call.lineno))
                        continue
                    for value in values:
                        found.setdefault(value, set()).add(f"{rel}:{call.lineno}")
    return found, unresolved


def _v51_values() -> set[str]:
    text = V51.read_text(encoding="utf-8")
    block = re.search(r"wanted\s+text\[\]\s*:=\s*ARRAY\[(.*?)\];", text, re.S)
    assert block, "v51 no longer declares its `wanted` list"
    return set(re.findall(r"'([a-z_]+)'", block.group(1)))


def test_inventory_is_not_vacuous():
    found, _ = _emitted()
    # A broken extractor would make the subset check pass on nothing.
    assert len(found) >= 25, sorted(found)
    assert "harvest_lot" in found and "field" in found


def test_every_emitted_entity_type_is_allowed():
    found, _ = _emitted()
    allowed = _allowed()
    missing = {value: sorted(sites)[:3] for value, sites in found.items() if value not in allowed}
    assert not missing, (
        "entity_type values emitted but rejected by events_entity_type_check — add them to "
        f"ALLOWED_ENTITY_TYPES and to a new migration widening the CHECK: {missing}"
    )


def test_unreadable_entity_types_are_declared_pass_throughs():
    _, unresolved = _emitted()
    undeclared = [
        (rel, expr, line) for rel, expr, line in unresolved if (rel, expr) not in PASS_THROUGH
    ]
    assert not undeclared, (
        "entity_type passed as a value the guard cannot read; use a literal or a module "
        f"constant, or declare a forwarding function in PASS_THROUGH: {undeclared}"
    )


def test_migration_and_python_set_are_identical():
    assert _v51_values() == set(_allowed())


def test_v51_is_the_only_manifest_entry_redefining_the_constraint():
    entries = [ln.strip() for ln in MANIFEST.read_text(encoding="utf-8").splitlines()]
    entries = [e for e in entries if e and not e.startswith("#")]
    definers = [
        e
        for e in entries
        if "events_entity_type_check" in (ROOT / "migrations" / e).read_text(encoding="utf-8")
    ]
    assert definers == [V51.name], definers


def test_v51_does_not_narrow_a_wider_constraint_on_rerun():
    # MANIFEST re-runs on every deploy; v51's unconditional DROP+ADD narrowed the CHECK back
    # to 11 values and failed once a row held a newer category.
    text = V51.read_text(encoding="utf-8")
    section = text[text.index("── (1)") : text.index("── (2)")]
    assert "pg_get_constraintdef" in section and "RETURN" in section, section


def test_validate_envelope_rejects_an_unknown_entity_type():
    sys.path.insert(0, str(PLATFORM))
    try:
        from core.event_schema import new_event, validate_envelope
    finally:
        sys.path.remove(str(PLATFORM))
    tenant = "00000000-0000-4000-8000-000000000001"
    assert validate_envelope(new_event("harvest.lot.created", "harvest_lot", "l1", tenant)) == []
    errors = validate_envelope(new_event("x.created", "not_a_category", "e1", tenant))
    assert any("entity_type" in e for e in errors), errors
