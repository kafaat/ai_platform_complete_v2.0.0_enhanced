"""Evidence extraction, weighting and proven dependencies in the capability map (R1/R2/R3).

The test-impact recall review (2026-11-09, anchor e374faf90) traced seven historical miss
events to the map, not to the escalation policy:

* R1 — one word scored twice: title "GDD" + alias "gdd" both normalize to ``gdd``.
* R2 — non-functional text counted: a fixture row ``"capability_id": "SOIL-001"`` gave a
  diagnostics test SOIL-001; comments about an MFA incident gave the shared loader SEC-004;
  a *software* inventory was read as farm inventory (FM-007).
* R3 — lexical similarity standing in for dependency: the token-guard test reads
  ``services/guardrails-engine/main.py`` by AST, the weather test imports ``open_meteo``,
  yet neither link existed.

Each class has a positive and a negative control here, and the seven events keep the
category they must have against the shipped map: SELECTED by a proven dependency, or
ESCALATED/FLOOR for a stated reason — never a domain link invented to look SELECTED.
SELECTED is a plan category, not an execution receipt.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses in the gate resolve through sys.modules
    spec.loader.exec_module(module)
    return module


ENGINE = _load("_r123_capability_mapping_engine", "scripts/ci/capability_mapping_engine.py")
SELECTOR = _load("_r123_test_impact", "scripts/ci/test_impact.py")
GATE = SELECTOR._engine()


def _cap(title: str) -> dict:
    return {"title": {"en": title}}


def _score(cid: str, title: str, rel: str, text: str, kind: str = "tests"):
    reading = ENGINE.scoring_text(rel, text, kind)
    return ENGINE.score_blob(cid, _cap(title), rel, reading.hay_path, reading.hay, reading.id_text)


# ── R1: normalize, then de-duplicate ────────────────────────────────────────────────


def test_equivalent_spellings_are_one_scoring_term():
    terms = ENGINE._scoring_terms("WX-006", "GDD")
    assert terms == (("gdd", ("GDD", "gdd")), ("growing degree", ("growing degree",)))


def test_gdd_and_gdd_do_not_double_count():
    score, hits = _score("WX-006", "GDD", "pkg/module.py", "x = accumulate_gdd(gdd, gdd)\n")
    # three occurrences of ONE term: 2 + 3 = 5, below the 8-point threshold. Before R1
    # the same text scored 10 (content:GDD + content:gdd) and bound the file.
    assert score == 5
    assert "content:GDD" in hits and "content:gdd" not in hits
    assert "dedup:GDD=gdd" in hits


def test_a_single_term_vocabulary_binds_only_by_repetition():
    two = _score("SAT-004", "NDMI", "pkg/indices.py", "ndmi = ndmi_band\n")[0]
    six = _score("SAT-004", "NDMI", "pkg/indices.py", "ndmi = " + " + ".join(["ndmi"] * 5) + "\n")
    assert two < 8, "two mentions bound NDMI only through the old double count"
    assert six[0] >= 8, six


# ── R2: comments, docstrings and fixture data are not functional evidence ───────────

_FIXTURE_TEST = '''"""A generic builder test."""
import json

def test_builder(tmp_path):
    # SOIL-001 in a comment
    row = {"capability_id": "SOIL-001", "entrypoints": ["POST /api/v1/soil"]}
    (tmp_path / "x.json").write_text(json.dumps({"capabilities": [row]}))
'''


def test_a_capability_id_in_a_fixture_row_is_not_explicit_evidence():
    score, hits = _score("SOIL-001", "Soil profile", "tests_v9/test_builder.py", _FIXTURE_TEST)
    assert "explicit_id" not in hits
    assert score < 8


def test_a_capability_id_in_functional_code_still_counts():
    text = 'def test_x(result):\n    assert result.capability == "SOIL-001"\n'
    _, hits = _score("SOIL-001", "Soil profile", "tests_v9/test_x.py", text)
    assert "explicit_id" in hits


def test_fixture_stripping_is_limited_to_test_files():
    text = 'EXAMPLE = {"capability_id": "SOIL-001"}\n'
    _, hits = _score("SOIL-001", "Soil profile", "services/soil/models.py", text, "backend")
    assert "explicit_id" in hits


def test_words_in_comments_are_not_evidence_but_identifiers_are():
    commented = "# a prior MFA import-cache failure, mfa_runtime cached main\nimport sys\n"
    assert "mfa" not in ENGINE.scoring_text("tests_v9/helper.py", commented, "other").hay
    code = "import mfa_runtime\nmfa_runtime.verify()\n"
    assert "mfa" in ENGINE.scoring_text("tests_v9/helper.py", code, "other").hay


def test_docstrings_stay_functional_evidence():
    """A docstring declares what a test is for; only comments and fixture data drop."""
    text = '"""Tenant isolation of the anomaly store under RLS."""\nimport sys\n'
    hay = ENGINE.scoring_text("tests_v9/test_x.py", text, "tests").hay
    assert "tenant isolation" in hay and "rls" in hay


def test_unparsable_python_keeps_the_raw_reading():
    reading = ENGINE.scoring_text("pkg/broken.py", "def (:\n  # MFA\n", "other")
    assert reading.reading == "raw" and "mfa" in reading.hay


def test_a_software_inventory_is_not_farm_inventory():
    text = "def build(out):\n    route_inventory = component_inventory(out)\n    return route_inventory\n"
    score, hits = _score(
        "FM-007",
        "Inventory and procurement",
        "scripts/diagnostics/build_main_inventory.py",
        text,
        "other",
    )
    assert score == 0 and not hits


def test_farm_inventory_in_context_still_binds():
    text = "def reorder(inventory):\n    return inventory.stock < inventory.reorder_level\n"
    score, hits = _score(
        "FM-007",
        "Inventory and procurement",
        "services/platform/routers/inventory.py",
        text,
        "backend",
    )
    assert score >= 8 and "path:inventory" in hits


# ── R3: proven test → source dependencies ───────────────────────────────────────────

_INDEX = ENGINE.repo_index(
    [
        "services/weather-service/gdd.py",
        "services/weather-service/tests/test_w.py",
        "services/guardrails-engine/main.py",
        "services/auth/main.py",
        "scripts/diagnostics/build_main_inventory.py",
        "tests_v9/service_module.py",
        "tests_v9/test_t.py",
        "docs/architecture/contract.json",
    ]
)


def _relations(rel: str, text: str):
    return ENGINE.extract_test_dependencies(rel, text, _INDEX)


def _edges(relations) -> set[tuple[str, str]]:
    return {(edge["source"], edge["kind"]) for edge in relations["edges"]}


def test_a_direct_import_is_an_import_edge():
    found = _relations(
        "services/weather-service/tests/test_w.py", "from gdd import accumulate_gdd\n"
    )
    assert _edges(found) == {("services/weather-service/gdd.py", "import")}
    assert found["bounded"] is True and found["unresolved"] == []


def test_reading_a_source_by_path_is_a_source_read_edge():
    text = (
        "import ast\nfrom pathlib import Path\nROOT = Path(__file__).resolve().parents[1]\n"
        'SOURCE = ROOT / "services/guardrails-engine/main.py"\n'
        "tree = ast.parse(SOURCE.read_text())\n"
    )
    assert _edges(_relations("tests_v9/test_t.py", text)) == {
        ("services/guardrails-engine/main.py", "source_read")
    }


def test_a_service_loader_resolves_to_the_service_main():
    text = (
        "import pathlib\nfrom tests_v9.service_module import load_service_main\n"
        "ROOT = pathlib.Path(__file__).resolve().parent.parent\n"
        '_DIR = str(ROOT / "services" / "auth")\n'
        'main = load_service_main(_DIR, required_attrs=("x",))\n'
    )
    found = _relations("tests_v9/test_t.py", text)
    assert ("services/auth/main.py", "loader") in _edges(found)
    assert ("tests_v9/service_module.py", "import") in _edges(found)
    # the shared harness has its own reads that are not analysed here
    assert found["bounded"] is False and "shared_test_helper" in found["unbounded_reasons"]


def test_a_local_helper_loader_is_resolved_through_its_literal_calls():
    text = (
        "import importlib.util\nfrom pathlib import Path\nROOT = Path(__file__).parents[1]\n"
        "def _load(rel, name):\n"
        "    spec = importlib.util.spec_from_file_location(name, ROOT / rel)\n"
        "    return spec\n"
        '_load("scripts/diagnostics/build_main_inventory.py", "inv")\n'
    )
    found = _relations("tests_v9/test_t.py", text)
    assert ("scripts/diagnostics/build_main_inventory.py", "loader") in _edges(found)
    assert found["unresolved"] == [] and found["bounded"] is True


def test_a_dynamic_relation_is_recorded_unresolved_never_guessed():
    text = "import importlib\ndef test_x(name):\n    importlib.import_module(name)\n"
    found = _relations("tests_v9/test_t.py", text)
    assert found["edges"] == []
    assert found["unresolved"] == [{"line": 3, "call": "import_module"}]
    assert found["bounded"] is False


def test_tree_wide_scans_and_data_reads_are_not_bounded():
    text = (
        "from pathlib import Path\nROOT = Path(__file__).parents[1]\n"
        'C = ROOT / "docs/architecture/contract.json"\n'
        "from gdd import x\n"
        'FILES = list(ROOT.rglob("*.py"))\n'
    )
    found = _relations("services/weather-service/tests/test_w.py", text)
    assert {"tree_wide_scan", "reads_repository_data_file"} <= set(found["unbounded_reasons"])


# ── R3 in the single engine: path-level selection, labels kept, floor kept ─────────

_REGISTRY = {
    "capabilities": [
        {"id": cid, "services": [], "tests": [], "apis": [], "evidence": [], "dependencies": []}
        for cid in ("SEC-006", "DEC-003", "WX-006")
    ]
}


def _mapping(relations: list[dict]) -> dict:
    return {
        "capabilities": [
            {"capability_id": "SEC-006", "tests": [{"path": "tests_v9/test_token.py"}]},
            {"capability_id": "DEC-003", "backend": [{"path": "services/guard/main.py"}]},
            {"capability_id": "WX-006", "backend": [{"path": "services/wx/gdd.py"}]},
        ],
        "test_dependencies": relations,
    }


def _relation(test: str, source: str, kind: str, bounded: bool = True) -> dict:
    return {
        "test": test,
        "bounded": bounded,
        "unbounded_reasons": [] if bounded else ["tree_wide_scan"],
        "edges": [{"source": source, "kind": kind, "line": 1}],
        "unresolved": [],
    }


def _plan(snapshot, changed: list[str], tests: list[str]):
    result = GATE.impact(changed, snapshot)
    selected, floor = SELECTOR.select(
        snapshot, set(result["affected"]), tests, result["dependent_tests"]
    )
    return result, selected, floor


def test_a_labelled_test_is_selected_by_its_source_without_relabelling():
    relations = [_relation("tests_v9/test_token.py", "services/guard/main.py", "source_read")]
    snapshot = GATE.build_snapshot(_REGISTRY, _mapping(relations), None, root=None)
    assert snapshot.references["tests_v9/test_token.py"].capabilities == {"SEC-006"}
    result, selected, _ = _plan(snapshot, ["services/guard/main.py"], ["tests_v9/test_token.py"])
    assert result["direct"] == ["DEC-003"], "a dependency adds no capability to impact"
    assert selected["tests_v9/test_token.py"]["dependencies"] == [
        "dependency:source_read:services/guard/main.py"
    ]


def test_without_the_edge_the_same_change_excludes_the_test():
    snapshot = GATE.build_snapshot(_REGISTRY, _mapping([]), None, root=None)
    _, selected, floor = _plan(snapshot, ["services/guard/main.py"], ["tests_v9/test_token.py"])
    assert "tests_v9/test_token.py" not in selected and "tests_v9/test_token.py" not in floor


def test_an_unlabelled_bounded_test_inherits_its_sources_capabilities():
    relations = [_relation("services/wx/tests/test_w.py", "services/wx/gdd.py", "import")]
    snapshot = GATE.build_snapshot(_REGISTRY, _mapping(relations), None, root=None)
    reference = snapshot.references["services/wx/tests/test_w.py"]
    assert reference.capabilities == {"WX-006"}
    assert reference.sources == {"mapping:dependency:import:services/wx/gdd.py"}


def test_an_unlabelled_unbounded_test_stays_in_the_floor():
    relations = [
        _relation("services/wx/tests/test_w.py", "services/wx/gdd.py", "import", bounded=False)
    ]
    snapshot = GATE.build_snapshot(_REGISTRY, _mapping(relations), None, root=None)
    _, selected, floor = _plan(snapshot, ["services/wx/gdd.py"], ["services/wx/tests/test_w.py"])
    assert floor == ["services/wx/tests/test_w.py"] and not selected


def test_snapshots_without_dependencies_still_load():
    snapshot = GATE.build_snapshot(_REGISTRY, {"capabilities": []}, None, root=None)
    assert snapshot.test_dependencies == {}
    merged = GATE.merge_snapshots(snapshot, snapshot)
    assert merged.test_dependencies == {}


# ── The seven reviewed events against the shipped map (counterfactual 2 inputs) ─────
#
# Inputs are each commit's changed paths minus the changed tests and minus the strict
# ``measured_on`` stamp paths (the review's second counterfactual; production policy
# escalates all seven on those stamps and stays unchanged). Only paths that can affect
# the plan are listed: sources, plus non-source paths kept for the escalation check.

_CASES = {
    "RTS-C01 fe4c7744d": (
        ["services/weather-service/open_meteo.py", "release/FILE_CHECKSUMS.sha256"],
        "services/weather-service/tests/test_missing_temperature_is_not_zero.py",
        "SELECTED",
        "dependency:import:services/weather-service/open_meteo.py",
    ),
    "RTS-C02 e55d50143": (
        ["services/weather-service/weather_runtime.py", "release/FILE_CHECKSUMS.sha256"],
        "services/weather-service/tests/test_crop_stress_endpoints.py",
        "SELECTED",
        "dependency:import:services/weather-service/weather_runtime.py",
    ),
    "RTS-C03 69e9d447f": (
        [
            "scripts/diagnostics/build_main_inventory.py",
            "scripts/diagnostics/resolve_inventory_edges.py",
        ],
        "tests_v9/test_main_inventory_generator.py",
        "ESCALATED",
        "scripts/diagnostics/build_main_inventory.py is a source file",
    ),
    "RTS-C03 bcd8ad8ad": (
        ["scripts/diagnostics/resolve_inventory_edges.py"],
        "tests_v9/test_main_inventory_generator.py",
        "ESCALATED",
        "scripts/diagnostics/resolve_inventory_edges.py is a source file",
    ),
    "RTS-C04 944e566c4": (
        ["services/guardrails-engine/main.py", "release/FILE_CHECKSUMS.sha256"],
        "tests_v9/test_guardrails_service_token_ascii.py",
        "SELECTED",
        "dependency:source_read:services/guardrails-engine/main.py",
    ),
    "RTS-C05 18d5ef4fa": (
        ["tests_v9/service_module.py"],
        "tests_v9/test_tenant_provisioning.py",
        "ESCALATED",
        "tests_v9/service_module.py is a source file",
    ),
    "RTS-C06 95c5cc525": (
        ["services/guardrails-engine/main.py", "tests_v9/service_module.py"],
        "tests_v9/test_rs_anomaly_pg_isolation_integration.py",
        "ESCALATED",
        "tests_v9/service_module.py is a source file",
    ),
}


@pytest.fixture(scope="module")
def shipped():
    snapshot = GATE.current_snapshot(root=ROOT)
    return snapshot, SELECTOR.load_policy(), SELECTOR.discover_test_files(ROOT)


@pytest.mark.parametrize("case", sorted(_CASES))
def test_reviewed_event_keeps_its_expected_category(case, shipped):
    snapshot, policy, tests = shipped
    changed, test, expected, evidence = _CASES[case]
    result, selected, floor = _plan(snapshot, changed, tests)
    unbound = {p for p in changed if not SELECTOR._is_bound(snapshot, p)}
    reasons = SELECTOR.escalation_reasons(
        changed, policy, governance_wide=result["governance_wide"], unbound=unbound
    )
    if expected == "SELECTED":
        assert not reasons, reasons
        assert evidence in selected[test].get("dependencies", []), selected.get(test)
    else:
        assert any(reason.startswith(evidence) for reason in reasons), reasons


def test_reviewed_labels_are_preserved_not_rewritten(shipped):
    snapshot, _, _ = shipped
    caps = {path: ref.capabilities for path, ref in snapshot.references.items()}
    assert "SEC-006" in caps["tests_v9/test_guardrails_service_token_ascii.py"]
    assert "DEC-003" not in caps["tests_v9/test_guardrails_service_token_ascii.py"]
    assert (
        "WX-006" in caps["services/weather-service/tests/test_missing_temperature_is_not_zero.py"]
    )
    assert "FM-001" in caps["tests_v9/test_tenant_provisioning.py"]
    assert "SEC-001" in caps["tests_v9/test_rs_anomaly_pg_isolation_integration.py"]
    # the fabricated fixture row and the software inventory no longer bind
    assert "tests_v9/test_main_inventory_generator.py" not in caps
    assert "scripts/diagnostics/build_main_inventory.py" not in caps
    assert "tests_v9/service_module.py" not in caps
