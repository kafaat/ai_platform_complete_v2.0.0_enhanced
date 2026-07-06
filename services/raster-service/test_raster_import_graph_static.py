"""Static contract for raster-service import graph after main.py decomposition."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "ci" / "raster_import_graph_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("raster_import_graph_gate", GATE)
    assert spec and spec.loader, "unable to load raster_import_graph_gate.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raster_import_graph_is_main_free_acyclic_and_layered():
    gate = _load_gate()
    modules = gate._production_files()
    assert modules, "expected production raster-service modules"

    assert gate._main_dependency_offenders(modules) == []

    graph = gate._local_import_graph(modules)
    assert gate._cycles(graph) == []
    assert gate._core_to_router_edges(graph) == []
