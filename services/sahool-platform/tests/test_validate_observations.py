"""Tests for validate_observations.py — the CRITICAL quality gate that enforces
the Golden Rule (missing strict governor → BLOCKED). Previously had ZERO tests."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import validate_observations as vo


def _make_tenant(files: list[str]) -> Path:
    """Create a temp tenant dir with given files present."""
    d = Path(tempfile.mkdtemp())
    for f in files:
        (d / f).write_text("# stub\n", encoding="utf-8")
    return d


class TestValidateGate:
    def test_empty_tenant_blocks_or_low(self):
        # no files → missing critical observables → must NOT be HIGH
        d = _make_tenant([])
        r = vo.validate(d)
        assert r["quality_grade"] in ("BLOCKED", "LOW")

    def test_grade_is_one_of_four(self):
        d = _make_tenant(["farm_map.yaml"])
        r = vo.validate(d)
        assert r["quality_grade"] in ("BLOCKED", "LOW", "MEDIUM", "HIGH")

    def test_report_has_required_keys(self):
        d = _make_tenant([])
        r = vo.validate(d)
        for k in ("quality_grade", "missing_A", "blocking_observables", "A_present"):
            assert k in r

    def test_blocking_observables_is_list(self):
        d = _make_tenant([])
        r = vo.validate(d)
        assert isinstance(r["blocking_observables"], list)

    def test_more_files_never_worse_grade(self):
        # adding data should never DOWNGRADE the grade (monotonic)
        order = {"BLOCKED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        empty = vo.validate(_make_tenant([]))
        full = vo.validate(_make_tenant(
            ["farm_map.yaml", "well_specs.yaml", "yield_history.csv", "economics.yaml"]))
        assert order[full["quality_grade"]] >= order[empty["quality_grade"]]

    def test_matrix_and_fallback_load(self):
        # the gate depends on these configs existing and parsing
        assert len(vo.load_matrix()) > 0
        fb = vo.load_fallback()
        assert "no_fallback_allowed" in fb
