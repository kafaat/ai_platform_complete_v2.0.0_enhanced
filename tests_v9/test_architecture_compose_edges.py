"""A Compose condition and a service property are not graph dependencies."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_only_list_or_mapping_dependencies_become_edges(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "compose_graph", ROOT / "scripts/ci/architecture_graph.py"
    )
    graph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graph)
    monkeypatch.setattr(graph, "ROOT", tmp_path)
    (tmp_path / "docker-compose.yml").write_text(
        """services:
  api:
    depends_on:
      db:
        condition: service_healthy
        restart: true
    environment:
      DATABASE_URL: synthetic
    volumes:
      - data:/data
  worker:
    depends_on: [api]
volumes:
  data:
    driver: local
""",
        encoding="utf-8",
    )
    nodes = {}
    edges = graph.compose_edges(nodes)
    assert {(x["source"], x["target"]) for x in edges} == {("api", "db"), ("worker", "api")}
    assert set(nodes) == {"api", "db", "worker"}


def test_test_only_imports_do_not_create_runtime_dependencies(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "python_graph", ROOT / "scripts/ci/architecture_graph.py"
    )
    graph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(graph)
    monkeypatch.setattr(graph, "ROOT", tmp_path)
    service = tmp_path / "services/platform"
    (service / "tests").mkdir(parents=True)
    (service / "tests/test_fake.py").write_text("import frontend.fixture\n", encoding="utf-8")
    (service / "test_local.py").write_text("import frontend.fixture\n", encoding="utf-8")
    (service / "app.py").write_text("import auth.runtime\n", encoding="utf-8")
    nodes = {
        "platform": {"paths": ["services/platform"]},
        "auth": {"paths": []},
        "frontend": {"paths": []},
    }
    edges = graph.python_edges(nodes)
    assert [(x["source"], x["target"], x["evidence"]) for x in edges] == [
        ("platform", "auth", "services/platform/app.py")
    ]
