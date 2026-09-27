"""Consumer evidence must describe code calls, never quoted assertions."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "edges", ROOT / "scripts/diagnostics/resolve_inventory_edges.py"
)
edges = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edges)


def tree(tmp_path, body, filename="page.tsx"):
    files = {
        "frontend/src/config/endpoints.ts": "  platform: resolveHttpBase('VITE_PLATFORM', '/api', ''),\n",
        "frontend/src/services/api/client.ts": "const PLATFORM_URL = ENDPOINTS.platform;\nexport const kongApi = makeClient(PLATFORM_URL);\n",
        "frontend/nginx.conf": "upstream backend {\n server svc:8000;\n}\nlocation /api/ {\n proxy_pass http://backend/v1/;\n}\n",
        "frontend/src/" + filename: body,
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def resolve(root, method="POST"):
    return edges.resolve(
        [{"from": "svc", "to": "frontend", "entrypoints": [method + " /v1/query"]}],
        [{"component_id": "svc", "aliases": [], "compose_services": []}],
        root,
    )


@pytest.mark.parametrize(
    "body",
    [
        "expect(src).not.toContain(\"kongApi.post('/query'\");",
        "const example = \"kongApi.post('/query')\";",
        '// kongApi.post("/query")',
        '/* kongApi.post("/query") */',
        'const example = `kongApi.post("/query")`;',
    ],
)
def test_descriptions_are_not_calls(tmp_path, body):
    root = tree(tmp_path, body)
    calls, blind = edges.call_sites(root)
    assert calls == [] and blind == 0
    assert resolve(root)[0] == []


@pytest.mark.parametrize(
    "body",
    [
        'kongApi.post("/query");',
        'kongApi\n .post(\n "/query",\n {}\n);',
        'kongApi.post<{ result: string }>(\n "/query", {});',
    ],
)
def test_real_calls_resolve_across_lines(tmp_path, body):
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert len(resolved) == 1 and not remaining
    assert resolved[0]["evidence"]["method"] == "POST"
    assert report["scanner_blind_spots"] == 0


def test_http_method_mismatch_stays_unresolved(tmp_path):
    resolved, remaining, _ = resolve(tree(tmp_path, 'kongApi.get("/query");'))
    assert not resolved and len(remaining) == 1


@pytest.mark.parametrize(
    "body",
    [
        "kongApi.post(url);",
        'kongApi.post("/query" + suffix);',
        "kongApi.post(`/query/${choosePath()}`);",
    ],
)
def test_dynamic_paths_are_blind_spots(tmp_path, body):
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert not resolved and len(remaining) == 1
    assert report["scanner_blind_spots"] == 1


def test_test_calls_are_retained_separately(tmp_path):
    resolved, remaining, report = resolve(tree(tmp_path, 'kongApi.post("/query");', "page.test.ts"))
    assert not resolved and remaining
    assert report["test_call_sites"][0]["method"] == "POST"


def test_simple_template_parameter_is_resolved(tmp_path):
    calls, blind = edges.call_sites(tree(tmp_path, "kongApi.get(`/query/${fieldId}`);"))
    assert len(calls) == 1 and blind == 0
    assert edges.normalise(calls[0]["path"]) == "/query/{}"


@pytest.mark.parametrize(
    "body",
    [
        r'const pattern = /kongApi.post("\/query")/;',
        'const example = `text ${`kongApi.post("/query")`}`;',
        'const example = "escaped \\" kongApi.post(\'/query\')";',
    ],
)
def test_nested_and_escaped_descriptions_are_not_calls(tmp_path, body):
    assert edges.call_sites(tree(tmp_path, body))[0] == []


def test_comments_between_call_tokens_and_argument(tmp_path):
    resolved, _, _ = resolve(tree(tmp_path, 'kongApi /* client */ .post( /* path */ "/query");'))
    assert resolved


def test_methodless_contract_is_not_guessed(tmp_path):
    root = tree(tmp_path, 'kongApi.post("/query");')
    resolved, remaining, _ = edges.resolve(
        [{"from": "svc", "entrypoints": ["/v1/query"]}],
        [{"component_id": "svc", "aliases": [], "compose_services": []}],
        root,
    )
    assert not resolved and remaining


def test_negative_assertion_is_preserved_only_as_test_reference(tmp_path):
    root = tree(tmp_path, "expect(src).not.toContain(\"kongApi.post('/query'\");", "page.test.ts")
    resolved, remaining, report = resolve(root)
    assert not resolved and remaining
    assert report["test_call_sites"] == []
    assert report["non_executable_test_references"][0]["kind"] == "non_executable_test_reference"
