"""`current_indicators` must stay a flat numeric map, and the canonical context must not.

Found in review of PR #778. The route briefly merged the canonical agronomic context
into `current_indicators`. That map becomes `provenance.input_snapshot`
(core/internal_orchestrator.py:238), which core/cross_reference_finder.py::
_compare_indicators later reads key-by-key against historical snapshots.

The failure is silent, not loud. `_compare_indicators` increments `total` BEFORE the
float() conversion and catches the resulting TypeError, so a dict-valued key present in
both snapshots inflates the denominator while `matched` can never rise. Every later
similarity score is diluted and genuinely similar records slip under `min_similarity` —
no exception, no log, just worse recommendations over time.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from core.cross_reference_finder import _compare_indicators

pytestmark = pytest.mark.unit

ROUTER = Path(__file__).resolve().parents[1] / "api" / "routers" / "recommendations.py"


def test_a_non_numeric_key_in_both_snapshots_dilutes_the_similarity_score():
    """The mechanism itself, pinned: this is why the map must stay numeric."""
    numeric_only = {"ndvi": 0.62, "soil_moisture": 18.0}
    clean_score, _ = _compare_indicators(numeric_only, dict(numeric_only))
    assert clean_score == 1.0

    polluted = {**numeric_only, "canonical_agronomic_context": {"season_id": "s-1"}}
    dirty_score, _ = _compare_indicators(polluted, dict(polluted))
    assert dirty_score < clean_score, (
        "a dict-valued indicator inflates `total` without ever matching — "
        "identical records must not score lower than perfect"
    )


def test_the_route_never_puts_the_canonical_context_into_the_indicator_map():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body[0].value.value = ""
    executable = ast.unparse(tree)
    # ast.unparse normalises quoting, so match on the normalised form.
    assert "'current_indicators': numeric_indicators" in executable, (
        "the payload must forward the validated numeric map"
    )
    assert "numeric_indicators = _numeric_indicator_map(req.current_indicators)" in executable, (
        "the map must pass the contract guard before reaching the engine"
    )
    assert "merged_indicators" not in executable, (
        "the canonical context must never be merged into current_indicators"
    )


def test_the_canonical_context_is_recorded_in_the_persisted_input_snapshot():
    """Dropping it entirely would lose the lineage the slice exists to persist."""
    source = ROUTER.read_text(encoding="utf-8")
    assert 'input_snapshot["canonical_agronomic_context"] = canonical_context' in source


def test_an_unavailable_canonical_read_still_records_an_explicit_limitation():
    """Silence and emptiness must not be the same signal.

    If the read fails and the key is simply omitted, "this field has no persisted
    canonical state" and "the canonical read broke" become indistinguishable to every
    downstream reader of the persisted provenance.
    """
    from api.routers.recommendations import _record_canonical_context

    enriched: dict = {}
    _record_canonical_context(
        enriched,
        {"season_id": None, "candidates": [], "limitations": ["CANONICAL_CONTEXT_UNAVAILABLE"]},
    )
    recorded = enriched["provenance"]["input_snapshot"]["canonical_agronomic_context"]
    assert recorded["limitations"] == ["CANONICAL_CONTEXT_UNAVAILABLE"]

    source = ROUTER.read_text(encoding="utf-8")
    route = source.split("async def recommendations_for_field(", 1)[1].split(
        '@router.get("/api/v1/recommendations/engines")', 1
    )[0]
    assert route.count("_record_canonical_context(enriched, canonical_context)") == 2, (
        "the failure path must record the context too, not fall through silently"
    )


def test_for_field_reuses_one_tenant_connection_for_read_and_write():
    """The persisted SoR read and recommendation/outbox write share one snapshot."""
    source = ROUTER.read_text(encoding="utf-8")
    route = source.split("async def recommendations_for_field(", 1)[1].split(
        '@router.get("/api/v1/recommendations/engines")', 1
    )[0]
    assert route.count("async with tenant_connection(user) as conn:") == 1
    assert "load_agronomic_context(conn, field_id=req.field_id)" in route
    assert "_persist_recommendation(user, req, enriched, conn=conn)" in route
    assert route.index("load_agronomic_context(conn") < route.index(
        "_persist_recommendation(user, req, enriched, conn=conn)"
    )


def test_a_non_numeric_indicator_is_rejected_at_the_edge():
    """The contract guard: the map may not become Mapping[str, float | dict]."""
    from api.routers.recommendations import _numeric_indicator_map
    from fastapi import HTTPException

    assert _numeric_indicator_map({"ndvi": 0.7, "ndmi": 0.3}) == {"ndvi": 0.7, "ndmi": 0.3}
    assert _numeric_indicator_map(None) == {}
    assert _numeric_indicator_map({"ndvi": None}) == {"ndvi": None}

    for bad in ({"x": {"a": 1}}, {"x": "0.5"}, {"x": [1, 2]}):
        with pytest.raises(HTTPException) as exc:
            _numeric_indicator_map(bad)
        assert exc.value.status_code == 422


def test_a_boolean_is_not_accepted_as_an_indicator_value():
    """bool subclasses int; admitting it lets a flag pose as a measurement."""
    from api.routers.recommendations import _numeric_indicator_map
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        _numeric_indicator_map({"irrigated": True})


def test_history_carrying_the_context_does_not_disturb_a_clean_live_map():
    """The persisted snapshot may hold it; the live map decides what is compared."""
    live = {"ndvi": 0.62, "soil_moisture": 18.0}
    historical = {**live, "canonical_agronomic_context": {"season_id": "s-1"}}
    score, _ = _compare_indicators(live, historical)
    assert score == 1.0, (
        "only keys present in the LIVE map are compared, so extra provenance in a "
        "stored snapshot must not dilute the score"
    )
