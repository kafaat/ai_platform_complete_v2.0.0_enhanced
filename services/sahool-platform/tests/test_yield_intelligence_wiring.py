"""yield_intelligence wired to its production consumer, and the mean it refuses to give.

A canonical yield state is identified by (field, season, source_sha256). The danger in
summarising harvest points is not a wrong number but a *plausible* one: average the first
page of a 40,000-point harvest and you get a figure that looks exactly like the field's
yield. So the consumer computes a state only over one ingestion of one season, over an
untruncated page, and otherwise reports not_evaluated with the reason named.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from core.yield_intelligence import (
    SCHEMA_VERSION,
    assess_yield_scope,
    build_canonical_yield_state,
    summarize_yield_scope,
)

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "yield_map_ingestion.py"


def _row(*, ingestion="ing-1", season="2026", yield_kg_ha=5000.0):
    return {"ingestion_id": ingestion, "season_id": season, "yield_kg_ha": yield_kg_ha}


def _summary(rows, *, truncated=False, sha="abc123"):
    """Exercise the real decision path: pure scope check, then pure summarisation."""
    rows = list(rows)
    scope = assess_yield_scope(rows=rows, truncated=truncated)
    return summarize_yield_scope(
        field_id="f1",
        rows=rows,
        scope=scope,
        source_sha256=sha if scope.evaluable else None,
    )


# ── the core contract, exercised directly ───────────────────────────────────
def test_missing_trueup_is_declared_not_assumed_to_be_one():
    """An uncalibrated mean must never masquerade as a calibrated one."""
    state = build_canonical_yield_state(
        field_id="f1",
        season_id="2026",
        source_sha256="abc",
        records=[{"yield_kg_ha": 4000}, {"yield_kg_ha": 6000}],
    )
    assert state.raw_mean_kg_ha == 5000.0
    assert state.calibrated_mean_kg_ha is None
    assert state.calibration_factor is None
    assert "trueup_not_applied" in state.limitations
    assert state.quality_status == "accepted_with_warning"


def test_invalid_records_are_counted_not_silently_dropped():
    state = build_canonical_yield_state(
        field_id="f1",
        season_id="2026",
        source_sha256="abc",
        records=[{"yield_kg_ha": 4000}, {"yield_kg_ha": "bad"}, {"yield_kg_ha": -1}],
    )
    assert state.record_count == 1
    assert "rejected_invalid_records:2" in state.limitations


def test_calibration_outside_the_trueup_range_raises():
    for bad in (0.5, 1.5):
        with pytest.raises(ValueError):
            build_canonical_yield_state(
                field_id="f1",
                season_id="2026",
                source_sha256="abc",
                records=[{"yield_kg_ha": 4000}],
                calibration_factor=bad,
            )


def test_state_digest_is_deterministic_for_identical_input():
    kwargs = dict(
        field_id="f1", season_id="2026", source_sha256="abc", records=[{"yield_kg_ha": 4000}]
    )
    assert build_canonical_yield_state(**kwargs).state_digest == (
        build_canonical_yield_state(**kwargs).state_digest
    )


# ── the consumer's refusals: the flattering mean it must not produce ────────
def test_truncated_page_is_never_averaged():
    """The headline case: a full page is not the harvest."""
    result = _summary([_row() for _ in range(3)], truncated=True)
    assert result["status"] == "not_evaluated"
    assert result["state"] is None
    assert "record_page_truncated" in result["limitations"]


def test_scope_spanning_two_ingestions_has_no_single_provenance():
    result = _summary([_row(ingestion="ing-1"), _row(ingestion="ing-2")])
    assert result["status"] == "not_evaluated"
    assert "multiple_ingestions_in_scope" in result["limitations"]


def test_scope_spanning_two_seasons_is_refused():
    result = _summary([_row(season="2025"), _row(season="2026")])
    assert result["status"] == "not_evaluated"
    assert "multiple_seasons_in_scope" in result["limitations"]


def test_absent_provenance_never_becomes_a_placeholder_digest():
    result = _summary([_row()], sha=None)
    assert result["status"] == "not_evaluated"
    assert "source_sha256_unavailable" in result["limitations"]
    assert result["state"] is None


def test_empty_scope_is_not_a_zero_yield():
    result = _summary([])
    assert result["status"] == "not_evaluated"
    assert "no_records_in_scope" in result["limitations"]


def test_single_ingestion_single_season_is_evaluated_with_real_provenance():
    result = _summary([_row(yield_kg_ha=4000.0), _row(yield_kg_ha=6000.0)])
    assert result["status"] == "evaluated"
    assert result["state"]["schema_version"] == SCHEMA_VERSION
    assert result["state"]["raw_mean_kg_ha"] == 5000.0
    assert result["state"]["source_sha256"] == "abc123"
    assert result["state"]["calibrated_mean_kg_ha"] is None


# ── the production consumer ─────────────────────────────────────────────────
def test_router_consumes_the_core():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "core.yield_intelligence"
        for alias in node.names
    }
    assert {"assess_yield_scope", "summarize_yield_scope"} <= imported, imported


def test_no_new_route_was_spent_on_the_summary():
    """The summary is a parameter on an existing route, not a new one (INT-004A)."""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    paths = [
        d.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for d in node.decorator_list
        if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
    ]
    assert paths.count("/api/v1/fields/{field_id}/yield-map-records") == 1
    assert not any("summary" in p for p in paths), paths


def test_calibration_factor_is_never_defaulted_in_the_summariser():
    """A default of 1.0 would silently turn an uncalibrated mean into a calibrated one.

    Checked on the AST of `summarize_yield_scope`, not on the file text, so a mention in
    a docstring or comment cannot satisfy it.
    """
    core = Path(__file__).resolve().parents[1] / "core" / "yield_intelligence.py"
    tree = ast.parse(core.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "summarize_yield_scope"
    )
    calls = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "build_canonical_yield_state"
    ]
    assert len(calls) == 1, "the summariser must build the state exactly once"
    passed = {kw.arg: kw.value for kw in calls[0].keywords}
    assert "calibration_factor" in passed, "calibration must be explicit, never omitted"
    value = passed["calibration_factor"]
    assert isinstance(value, ast.Constant) and value.value is None, (
        "calibration_factor must be passed as None until a stored TrueUp owner exists"
    )


def test_router_delegates_and_holds_no_yield_logic_of_its_own():
    """Logic in core, I/O at the edge: the router must not re-implement the rules."""
    source = ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.body = [
                n
                for n in node.body
                if not (
                    isinstance(n, ast.Expr)
                    and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str)
                )
            ]
    stripped = ast.unparse(tree)
    for rule in ("multiple_ingestions_in_scope", "record_page_truncated", "trueup_not_applied"):
        assert rule not in stripped, f"router re-implements {rule!r}; it belongs in core"
