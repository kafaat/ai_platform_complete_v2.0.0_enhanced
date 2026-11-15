"""R13 explorer route export: fail closed and keep source-declaration duplicates."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from scripts.ci.export_explorer_routes import create_catalog

pytestmark = pytest.mark.unit
HEAD = "a" * 40
SERVICES = [{"service": "svc", "routes": 2}, {"service": "empty", "routes": 0}]
ROUTES = [
    {"service": "svc", "method": "GET", "path": "/v1/a", "file": "services/svc/main.py", "line": 3, "function": "get_a"},
    {"service": "svc", "method": "POST", "path": "/v1/b", "file": "services/svc/main.py", "line": 7, "function": "post_b"},
]


def catalog(routes=None, services=None):
    return create_catalog(
        ROUTES if routes is None else routes,
        SERVICES if services is None else services,
        source_head=HEAD, source_sha256="f" * 64,
    )


def test_source_status_and_route_counts():
    c = catalog()
    assert c["counts"]["services"] == 2
    assert c["counts"]["route_declarations"] == 2
    assert c["counts"]["unique_service_method_path"] == 2
    assert c["service_route_counts"]["empty"] == 0
    assert all(x["runtime"] == "NOT_RUN" for x in c["routes"])
    assert c["source_commit"] == HEAD


def test_repeated_method_path_in_distinct_mcp_handlers_is_not_deleted():
    clone = {**ROUTES[0], "file": "services/svc/extra.py", "line": 5}
    c = catalog([ROUTES[0], clone], [{"service": "svc", "routes": 2}])
    assert c["counts"]["route_declarations"] == 2
    assert c["counts"]["unique_service_method_path"] == 1
    assert c["counts"]["ambiguous_declaration_groups"] == 1
    assert len(c["ambiguous_declarations"][0]["declarations"]) == 2


def test_identical_declaration_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_DECLARATION_ROW"):
        catalog([ROUTES[0], ROUTES[0]], [{"service": "svc", "routes": 2}])


@pytest.mark.parametrize(
    "modification, reason",
    [
        ({"method": "BOGUS"}, "UNKNOWN_SERVICE_OR_METHOD"),
        ({"service": "other"}, "UNKNOWN_SERVICE_OR_METHOD"),
        ({"path": "v1/a"}, "ROUTE_PATH_INVALID"),
        ({"file": "services/another/main.py"}, "ROUTE_SOURCE_INVALID"),
        ({"line": 0}, "MALFORMED_ROUTE_ROW"),
    ],
)
def test_invalid_route_rejected(modification, reason):
    with pytest.raises(ValueError, match=reason):
        catalog([{**ROUTES[0], **modification}, ROUTES[1]])


def test_incorrect_count_fails():
    with pytest.raises(ValueError, match="SERVICE_ROUTE_COUNTS_DRIFT"):
        catalog(services=[{"service": "svc", "routes": 3}])


def test_missing_inventory_and_unbound_commit_fails():
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_MISSING_OR_EMPTY"):
        catalog(routes=[])
    with pytest.raises(ValueError, match="SOURCE_COMMIT_UNBOUND"):
        create_catalog(ROUTES, SERVICES, source_head="unverified", source_sha256="x")


def test_dynamic_path_is_not_a_literal_verified_route():
    c = catalog([{**ROUTES[0], "method": "ANY", "path": "<dynamic>"}, ROUTES[1]])
    assert c["counts"]["unresolved_dynamic_paths"] == 1
    assert c["routes"][0]["path_resolution"] == "UNRESOLVED_DYNAMIC"


def test_cli_missing_files_is_explicit_failure(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "ci" / "export_explorer_routes.py"
    p = subprocess.run(
        [sys.executable, str(script),
         "--route-inventory", str(tmp_path / "none.json"),
         "--service-inventory", str(tmp_path / "none2.json"),
         "--out-dir", str(tmp_path / "out")],
        capture_output=True, text=True, check=False,
    )
    assert p.returncode == 2 and "SOURCE_INVENTORY_MISSING_OR_EMPTY" in p.stderr
    assert not (tmp_path / "out").exists()
