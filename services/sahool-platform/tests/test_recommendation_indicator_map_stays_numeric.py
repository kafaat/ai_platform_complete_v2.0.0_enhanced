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
    assert "'current_indicators': dict(req.current_indicators or {})" in executable, (
        "the payload must forward the client's indicators unchanged"
    )
    assert "merged_indicators" not in executable, (
        "the canonical context must never be merged into current_indicators"
    )


def test_the_canonical_context_is_recorded_as_provenance_lineage():
    """Dropping it entirely would lose the lineage the slice exists to persist."""
    source = ROUTER.read_text(encoding="utf-8")
    assert 'provenance["canonical_agronomic_context"] = canonical_context' in source
