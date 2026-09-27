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
        "frontend/src/" + filename: body + '\nimport { kongApi } from "./services/api/client";\n',
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


# JSX and template-expression regressions. Text, expression and file-scan units
# are kept separate; these tests do not assert runtime execution or import binding.
@pytest.mark.parametrize(
    "body",
    [
        'const p = <pre>kongApi.post("/query")</pre>;',
        'const p = <><pre>kongApi.post("/query")</pre></>;',
        'const p = <Panel.Text>kongApi.post("/query")</Panel.Text>;',
        "const p = <Box title='kongApi.post(\"/query\")' />;",
        'const p = <Box>{"kongApi.post(\\"/query\\")"}</Box>;',
        'const p = <Box>{/* kongApi.post("/query") */}</Box>;',
        'const p = <Box>{`kongApi.post("/query")`}</Box>;',
        'const p = <DataTable<Row>>kongApi.post("/query")</DataTable>;',
    ],
)
def test_jsx_non_code_never_resolves(tmp_path, body):
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert not resolved and remaining
    assert report["unparsed_source_files"] == []


@pytest.mark.parametrize(
    "body",
    [
        'const p = <p>Don\'t run this</p>;\nkongApi.post("/query");',
        'const p = <p>"example"</p>;\nkongApi.post("/query");',
        'const p = <p>{kongApi.post("/query")}</p>;',
        'const p = <Box value={kongApi.post("/query")} />;',
        'const p = <Box child={<Button onClick={() => kongApi.post("/query")} />} />;',
        'const p = ( /* start */ <><p>Don\'t run</p>{kongApi.post("/query")}</> );',
        'const p = <DataTable<Row> request={() => kongApi.post("/query")} />;',
        'const p = <DataTable<() => Row> request={() => kongApi.post("/query")} />;',
        'const p = `result: ${kongApi.post("/query")}`;',
        'const p = `result: ${`inner ${kongApi.post("/query")}`}`;',
        'const p = `${true ? <Box>{kongApi.post("/query")}</Box> : "none"}`;',
        'const p = <Box>{true ? <pre>example</pre> : <Box>{kongApi.post("/query")}</Box>}</Box>;',
        'const f = <K extends keyof State>(key: K) => kongApi.post("/query");',
        'const f = <T,>(value: T) => kongApi.post("/query");',
    ],
)
def test_executable_jsx_and_template_expressions_survive(tmp_path, body):
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert len(resolved) == 1 and not remaining
    assert report["scanner_blind_spots"] == 0
    assert report["unparsed_source_files"] == []
    assert resolved[0]["evidence"]["method"] == "POST"


def test_jsx_text_preserves_source_line_offsets(tmp_path):
    body = 'const p = (\n<pre>Don\'t use kongApi.post("/query")</pre>\n);\nawait kongApi.post("/query");'
    calls, blind = edges.call_sites(tree(tmp_path, body))
    assert blind == 0
    assert [(c["method"], c["site"]) for c in calls] == [("POST", "frontend/src/page.tsx:4")]


@pytest.mark.parametrize(
    "body",
    [
        'const p = <pre>unclosed; kongApi.post("/query");',
        'const p = <pre>example</div>; kongApi.post("/query");',
        "const p = \"unclosed; kongApi.post('/query');",
    ],
)
def test_unparsed_file_is_reported_not_silently_counted_as_zero_calls(tmp_path, body):
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert not resolved and remaining
    assert report["lexical_scan_complete"] is False
    assert report["unparsed_source_files"][0]["reason"] == "unparsed_source_file"
    assert report["unparsed_source_files"][0]["count_unit"] == "file_not_calls"
    assert report["scanner_blind_spots"] == 0
    assert report["scanner_blind_spots_are_exhaustive"] is False


def test_unsupported_call_inside_template_has_a_site(tmp_path):
    body = "const value = `result: ${kongApi.post(dynamicUrl)}`;"
    resolved, _, report = resolve(tree(tmp_path, body))
    assert not resolved and report["scanner_blind_spots"] == 1
    assert report["unsupported_call_sites"][0]["site"] == "frontend/src/page.tsx:1"
    assert report["unparsed_source_files"] == []


def test_unparsed_files_are_not_counted_as_unsupported_calls(tmp_path):
    root = tree(tmp_path, 'const p = <Box>unclosed; kongApi.post("/query");')
    calls, unsupported_calls = edges.call_sites(root)
    _, _, report = resolve(root)
    assert calls == [] and unsupported_calls == 0
    assert len(report["unparsed_source_files"]) == 1
    assert report["unsupported_call_sites"] == []
    assert report["scanner_blind_spots_unit"] == "detected_unsupported_application_calls"


def test_unparsed_test_file_is_not_classified_as_non_executable_reference(tmp_path):
    root = tree(tmp_path, 'const p = <Box>unclosed; kongApi.post("/query");', "page.test.tsx")
    _, _, report = resolve(root)
    assert report["unparsed_source_files"][0]["source_kind"] == "test"
    assert report["non_executable_test_references"] == []
    assert report["lexical_scan_complete"] is False


@pytest.mark.parametrize(
    "prefix",
    ["if (ready) ", "if (ready) {} else ", "const x = await ", 'const x = "prefix" + '],
)
def test_jsx_text_in_expression_statement_context_stays_non_code(tmp_path, prefix):
    body = prefix + '<pre>kongApi.post("/query")</pre>;'
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert not resolved and remaining
    assert report["unparsed_source_files"] == []


@pytest.mark.parametrize(
    "prefix",
    ["if (ready) ", "if (ready) {} else ", "const x = await ", 'const x = "prefix" + '],
)
def test_jsx_expression_in_statement_context_is_still_visible(tmp_path, prefix):
    body = prefix + '<pre>{kongApi.post("/query")}</pre>;'
    resolved, remaining, report = resolve(tree(tmp_path, body))
    assert resolved and not remaining
    assert report["unparsed_source_files"] == []


def test_import_binding_is_required(tmp_path):
    root = tree(tmp_path, 'function f(kongApi) { kongApi.post("/query"); }')
    assert not resolve(root)[0]


def test_second_operation_has_its_own_evidence(tmp_path):
    root = tree(tmp_path, 'kongApi.get("/query"); kongApi.post("/query");')
    r, u, _ = edges.resolve(
        [{"from": "svc", "entrypoints": ["GET /v1/query", "POST /v1/query"]}],
        [{"component_id": "svc", "aliases": [], "compose_services": []}],
        root,
    )
    assert {row["evidence"]["method"] for row in r} == {"GET", "POST"}
    assert not u


def test_all_call_sites_are_retained(tmp_path):
    root = tree(tmp_path, 'kongApi.post("/query");')
    (root / "frontend/src/zpage.tsx").write_text(
        'import { kongApi } from "./services/api/client";\nkongApi.post("/query");'
    )
    r, _, _ = resolve(root)
    assert "zpage.tsx:2" in str(r)


def test_unmatched_operation_remains_pending(tmp_path):
    root = tree(tmp_path, 'kongApi.get("/query");')
    r, u, _ = edges.resolve(
        [{"from": "svc", "entrypoints": ["GET /v1/query", "DELETE /v1/query"]}],
        [{"component_id": "svc", "aliases": [], "compose_services": []}],
        root,
    )
    assert r and u
    assert u[0]["entrypoints"] == ["DELETE /v1/query"]


@pytest.mark.parametrize(
    "body",
    [
        'function f(kongApi) { kongApi.post("/query"); }',
        'const f = (kongApi) => kongApi.post("/query");',
        'function f({kongApi}) { kongApi.post("/query"); }',
        'const kongApi = other; kongApi.post("/query");',
        'kongApi = other; kongApi.post("/query");',
        'obj.kongApi.post("/query");',
    ],
)
def test_shadow_or_ambiguous_identifier_use_is_not_proof(tmp_path, body):
    root = tree(tmp_path, body)
    assert not resolve(root)[0]


@pytest.mark.parametrize(
    "declaration",
    [
        "",
        'import type { kongApi } from "./services/api/client";',
        'import { kongApi } from "./unrelated";',
        '// import { kongApi } from "./services/api/client";',
        "const text = 'import { kongApi } from \"./services/api/client\";';",
    ],
)
def test_missing_or_wrong_import_never_resolves(tmp_path, declaration):
    root = tree(tmp_path, "")
    (root / "frontend/src/page.tsx").write_text(declaration + '\nkongApi.post("/query");')
    assert not resolve(root)[0]


def test_named_alias_and_reexport_chain(tmp_path):
    root = tree(tmp_path, "")
    (root / "frontend/src/facade.ts").write_text(
        'export { kongApi as platform } from "./services/api/client";'
    )
    (root / "frontend/src/page.tsx").write_text(
        'import { platform as http } from "./facade";\nhttp.post("/query");'
    )
    r, u, _ = resolve(root)
    assert r and not u
    assert r[0]["evidence"]["import_chain"] == [
        "frontend/src/page.tsx:1",
        "frontend/src/facade.ts:1",
    ]


def test_reexport_cycle_stays_unproven(tmp_path):
    root = tree(tmp_path, "")
    (root / "frontend/src/facade.ts").write_text('export { kongApi } from "./facade";')
    (root / "frontend/src/page.tsx").write_text(
        'import { kongApi } from "./facade";\nkongApi.post("/query");'
    )
    assert not resolve(root)[0]


def test_two_same_line_calls_are_both_retained(tmp_path):
    r, _, _ = resolve(tree(tmp_path, 'kongApi.post("/query"); kongApi.post("/query");'))
    assert len(r) == 2


def test_same_line_evidence_has_distinct_columns(tmp_path):
    r, _, _ = resolve(tree(tmp_path, 'kongApi.post("/query"); kongApi.post("/query");'))
    assert [row["evidence"]["call_column"] for row in r] == [1, 25]


def test_dotted_module_name_cannot_bind_a_different_module(tmp_path):
    root = tree(tmp_path, "")
    (root / "frontend/src/facade.ts").write_text('export { kongApi } from "./services/api/client";')
    (root / "frontend/src/facade.shadow.ts").write_text("export const kongApi = unrelatedClient;")
    (root / "frontend/src/page.tsx").write_text(
        'import { kongApi } from "./facade.shadow";\nkongApi.post("/query");'
    )
    assert not resolve(root)[0]


def test_dotted_module_name_retains_its_complete_filename(tmp_path):
    root = tree(tmp_path, "")
    (root / "frontend/src/facade.client.ts").write_text(
        'export { kongApi } from "./services/api/client";'
    )
    (root / "frontend/src/page.tsx").write_text(
        'import { kongApi } from "./facade.client";\nkongApi.post("/query");'
    )
    assert resolve(root)[0]


def test_dynamic_test_calls_do_not_enter_application_blind_spots(tmp_path):
    root = tree(tmp_path, "kongApi.post(applicationUrl);")
    (root / "frontend/src/page.test.tsx").write_text("kongApi.post(testUrl);")
    _, _, report = resolve(root)
    assert report["scanner_blind_spots"] == len(report["unsupported_call_sites"]) == 1
    assert all(x["source_kind"] == "application" for x in report["unsupported_call_sites"])
    assert len(report["test_call_sites"]) == 1
    assert report["test_call_sites"][0]["reason"] == "unsupported_or_dynamic_path"


def test_only_dynamic_test_calls_leave_application_blind_spots_empty(tmp_path):
    _, _, report = resolve(tree(tmp_path, "kongApi.post(url);", "page.test.tsx"))
    assert report["scanner_blind_spots"] == 0
    assert report["unsupported_call_sites"] == []
    assert len(report["test_call_sites"]) == 1


def test_expression_context_work_scales_with_source_length():
    class CountedText(str):
        sliced = 0

        def __getitem__(self, key):
            if isinstance(key, slice):
                self.sliced += len(range(*key.indices(len(self))))
            return super().__getitem__(key)

    class CountedMask(list):
        reads = 0

        def __getitem__(self, key):
            self.reads += len(range(*key.indices(len(self)))) if isinstance(key, slice) else 1
            return super().__getitem__(key)

    def work(repeats):
        text = CountedText("const ratio = left / right; const view = <pre>text</pre>;\n" * repeats)
        scanner = edges._CodeMask(text, jsx=True)
        scanner.mask = CountedMask(scanner.mask)
        scanner.code()
        assert "text" not in "".join(scanner.mask)
        return scanner.mask.reads + text.sliced

    assert work(200) <= 3 * work(100)
