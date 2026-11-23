"""The canonical ingest keeps exactly one writer, and that writer stays one process.

RAG-INGEST-CROSS-REPLICA-PUBLICATION-NOT-COORDINATED-01 (open): rag-retrieval runs replicas
over one Qdrant collection with no shared lock, so two publications of one document racing
there can strip a chunk shared by both revisions from the winner (lab receipt 1582-v4).
#1582 closes the race where every publication starts: local-ai-rag, the only writer of
``/v1/ingest``, serialises publication per (tenant, document) in one process. That holds
only while (1) nothing else calls rag-retrieval's ingest, (2) local-ai-rag runs one worker
and one replica, and (3) the canonical call stays inside ``_publishing``. Each of these
fails here when it stops being true, so the mitigation cannot erode silently; the gap's
closing options (a shared per-document lock, or per-publication storage ids) are the way to
relax them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "services" / "local-ai-rag" / "main.py"
# Method or function names of an outgoing request: a client method (``c.post``), a bare
# helper (``post(url, ...)``) or urllib (``Request(url, data)``, ``urlopen(url, data)``).
_HTTP_METHODS = {"post", "put", "request", "send", "Request", "urlopen"}


def _calls_rag_ingest(path: Path) -> bool:
    """An HTTP call whose URL is an ingest route, wherever its host comes from.

    Conservative on purpose, since this guard is what keeps the single-writer premise true
    (Devin review on #1582, lab 1582-v5): an HTTP-method call counts when an argument
    contains ``/v1/ingest`` (with or without a host, so a relative path on a client built
    with ``base_url=RAG_RETRIEVAL_URL`` counts), or when an argument is a name or attribute
    assigned anywhere in the module from an expression containing ``/v1/ingest`` (a URL
    built before the call). Route decorators (``@app.post("/v1/ingest")``) declare an
    endpoint and are not calls out. Allowed callers are listed by name in ``_INGEST_CALLERS``.

    Parsed, not grepped: a guard that only mentions the path in a string is not a writer.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return False
    decorators = {
        id(d)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for d in node.decorator_list
    }
    ingest_urls: set[str] = set()

    def names_ingest(expr: ast.expr) -> bool:
        # String pieces joined in source order, so ``"/v1/" + "ingest"`` reads as the route
        # (lab 1582-v6, hospital review on #1582).
        pieces = sorted(
            (n for n in ast.walk(expr) if isinstance(n, ast.Constant) and isinstance(n.value, str)),
            key=lambda n: (n.lineno, n.col_offset),
        )
        if "/v1/ingest" in "".join(n.value for n in pieces):
            return True
        return "/v1/ingest" in ast.unparse(expr) or any(
            ast.unparse(n) in ingest_urls
            for n in ast.walk(expr)
            if isinstance(n, (ast.Name, ast.Attribute))
        )

    assignments = [
        (node.targets if isinstance(node, ast.Assign) else [node.target], node.value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
    ]
    grew = True
    while grew:  # to a fixed point: a URL built from a name that holds the route
        grew = False
        for targets, value in assignments:
            names = {ast.unparse(t) for t in targets}
            if not names <= ingest_urls and names_ingest(value):
                ingest_urls |= names
                grew = True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if called not in _HTTP_METHODS or id(node) in decorators:
            continue
        if any(names_ingest(arg) for arg in [*node.args, *(k.value for k in node.keywords)]):
            return True
    return False


_SKIP_PARTS = {"tests", "tests_v9", "node_modules", ".git", "__pycache__", ".venv", "venv"}


def _sources(tops):
    for top in tops:
        for path in (ROOT / top).rglob("*.py"):
            parts = set(path.relative_to(ROOT).parts)
            if parts & _SKIP_PARTS or path.name.startswith("test_"):
                continue
            yield path


def _all_sources():
    """Every Python file in the repository outside tests (``tools/`` and ``certification/`` too)."""
    for path in ROOT.glob("*.py"):
        if not path.name.startswith("test_"):
            yield path
    tops = [p.name for p in ROOT.iterdir() if p.is_dir() and p.name not in _SKIP_PARTS]
    yield from _sources(tops)


# Callers of an ingest route, allowed by name, with the reason:
#   local-ai-rag/main.py          the single writer, inside ``_publishing``;
#   staging/rag_fixture_probe.py  posts its fixture to local-ai-rag's own upload endpoint
#                                 (``sahool-local-ai-rag:8000``), i.e. through that lock.
_INGEST_CALLERS = ["scripts/staging/rag_fixture_probe.py", "services/local-ai-rag/main.py"]


def test_only_local_ai_rag_calls_the_canonical_ingest():
    writers = sorted(str(p.relative_to(ROOT)) for p in _all_sources() if _calls_rag_ingest(p))
    assert writers == _INGEST_CALLERS, (
        "a second writer of rag-retrieval /v1/ingest bypasses local-ai-rag's per-document "
        "serialisation (RAG-INGEST-CROSS-REPLICA-PUBLICATION-NOT-COORDINATED-01): " + str(writers)
    )


def test_the_fixture_probe_posts_to_local_ai_rag_not_to_rag_retrieval():
    source = (ROOT / "scripts" / "staging" / "rag_fixture_probe.py").read_text(encoding="utf-8")
    assert "http://sahool-local-ai-rag:8000/v1/ingest" in source
    assert "RAG_RETRIEVAL_URL" not in source and "sahool-rag-retrieval:8000/v1/ingest" not in source


# Code that drives the indexing service's write path directly. Allowed, with the reason:
#   production_qdrant.py      the write path itself (ingest -> ingest_documents -> settle);
#   rag-retrieval/main.py     the indexing service's /v1/ingest handler, i.e. local-ai-rag's
#                             calls arriving;
#   rag-retrieval/reindex_manifest.py  builds a separate versioned target collection, never
#                             the live one that tenant uploads publish into;
#   qdrant-seed/seed.py       writes the reference corpus, which no tenant ingest withdraws.
_WRITE_CALLS = {
    "ingest",
    "ingest_documents",
    "withdraw_document_points",
    "settle_document_publications",
    "upsert",
}
_KNOWN_WRITE_PATHS = {
    "services/sahool-platform/core/rag/production_qdrant.py",
    "services/rag-retrieval/main.py",
    "services/rag-retrieval/reindex_manifest.py",
    "services/qdrant-seed/seed.py",
    # An archived evidence witness: writes the disposable ``native_source`` and
    # ``native_baseline`` collections of a Qdrant it reaches on 127.0.0.1:17333.
    "certification/evidence/chatgpt_closure_nine_20261016/rag/native_reindex_witness.py",
}
_INDEX_CLIENTS = ("production_qdrant", "HybridQdrantRetriever", "QdrantHttpClient")


def _drives_index_writes(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not any(name in text for name in _INDEX_CLIENTS):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return any(
        isinstance(n, ast.Call) and getattr(n.func, "attr", None) in _WRITE_CALLS
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize(
    ("source", "writer"),
    [
        (
            "import httpx\nURL = 'http://sahool-rag-retrieval:8000'\n"
            "async def go(b):\n"
            "    async with httpx.AsyncClient(base_url=URL) as c:\n"
            "        await c.post('/v1/ingest', json=b)\n",
            True,
        ),
        (
            "import os, httpx\nBASE = os.getenv('RAG_RETRIEVAL_URL')\n"
            "def go(b, v):\n    httpx.Client(base_url=BASE).post(f'/v1/ingest?v={v}', json=b)\n",
            True,
        ),
        (
            "import httpx\nfrom os import getenv\nU = getenv('INDEXER')\n"
            "def go(b):\n    httpx.post(f'{U}/v1/ingest', json=b)\n",
            True,
        ),
        (
            "import httpx\nfrom os import getenv\n"
            "def go(b):\n    url = getenv('INDEXER') + '/v1/ingest'\n"
            "    httpx.post(url, json=b)\n",
            True,
        ),
        (
            "import requests\nINGEST = '/v1/ingest'\nclass C:\n"
            "    def __init__(self, base):\n        self.url = base + INGEST\n"
            "    def go(self, b):\n        requests.request('POST', self.url, json=b)\n",
            True,
        ),
        (
            "import urllib.request\nU = 'http://sahool-rag-retrieval:8000/v1/ingest'\n"
            "def go(b):\n    urllib.request.urlopen(urllib.request.Request(U, data=b))\n",
            True,
        ),
        (
            "def post(url, body):\n    ...\n"
            "def go(b):\n    post('http://sahool-rag-retrieval:8000/v1/ingest', b)\n",
            True,
        ),
        (
            "import httpx, os\nBASE = os.environ['RAG_RETRIEVAL_URL']\n"
            "def go(b):\n    httpx.post(BASE + '/v1/' + 'ingest', json=b)\n",
            True,
        ),
        (
            "import httpx\nROUTE = '/v1/' 'ingest'\ndef go(c, b):\n    c.post(ROUTE, json=b)\n",
            True,
        ),
        (
            "from fastapi import FastAPI\napp = FastAPI()\n"
            "@app.post('/v1/ingest')\ndef ingest():\n    return {}\n",
            False,
        ),
        (
            "import httpx\nDOC = 'see /v1/ingest'\n"
            "def go():\n    print(DOC)\n    httpx.get('http://rag/v1/search')\n",
            False,
        ),
    ],
    ids=[
        "base-url-host",
        "base-url-env-fstring",
        "url-from-another-name",
        "url-built-before-the-call",
        "url-built-from-a-constant",
        "urllib-request",
        "bare-helper",
        "route-split-across-pieces",
        "route-split-by-implicit-concatenation",
        "route-decorator",
        "mentioned-not-called",
    ],
)
def test_the_writer_detector_sees_every_way_to_reach_an_ingest_route(tmp_path, source, writer):
    module = tmp_path / "caller.py"
    module.write_text(source, encoding="utf-8")
    assert _calls_rag_ingest(module) is writer


def test_nothing_else_drives_the_index_write_path_directly():
    drivers = sorted(
        str(p.relative_to(ROOT))
        for p in _all_sources()
        if _drives_index_writes(p) and str(p.relative_to(ROOT)) not in _KNOWN_WRITE_PATHS
    )
    assert drivers == [], (
        "a module calling the retriever's ingest/withdraw/settle or the Qdrant upsert "
        "directly bypasses local-ai-rag's per-document serialisation: " + str(drivers)
    )


def test_local_ai_rag_runs_one_worker():
    service = ROOT / "services" / "local-ai-rag"
    dockerfile = (service / "Dockerfile").read_text(encoding="utf-8")
    cmd = [line for line in dockerfile.splitlines() if line.strip().startswith("CMD")]
    assert len(cmd) == 1 and '"--workers", "1"' in cmd[0], (
        "more than one uvicorn worker splits the in-process publication locks"
    )
    assert "gunicorn" not in dockerfile.lower()
    assert not [p.name for p in service.iterdir() if p.name.startswith("gunicorn")], (
        "a gunicorn config would run local-ai-rag under several worker processes"
    )


def test_local_ai_rag_runs_one_replica():
    compose = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
    start = compose.index("\n  sahool-local-ai-rag:\n")
    nxt = re.search(r"\n  [a-z0-9][a-z0-9_-]*:\n", compose[start + 1 :])
    block = compose[start : start + 1 + (nxt.start() if nxt else len(compose))]
    replicas = re.findall(r"replicas:\s*(\S+)", block)
    assert all(r.strip("'\"") == "1" for r in replicas), replicas
    assert "scale:" not in block
    # A command, entrypoint or worker setting here would replace the Dockerfile's one worker.
    for key in ("command:", "entrypoint:", "WEB_CONCURRENCY", "UVICORN_WORKERS", "--workers"):
        assert key not in block, f"compose sets {key!r} for local-ai-rag"
    for chart in (ROOT / "helm").rglob("*.yaml"):
        text = chart.read_text(encoding="utf-8", errors="replace")
        assert "local-ai-rag" not in text and "localAiRag" not in text, (
            f"{chart.relative_to(ROOT)} deploys local-ai-rag; a second replica splits the locks"
        )


def test_the_canonical_call_stays_inside_the_publication_lock():
    tree = ast.parse(WRITER.read_text(encoding="utf-8"))
    fn = next(
        n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ingest_documents"
    )
    guarded = []
    for node in ast.walk(fn):
        if isinstance(node, ast.AsyncWith) and any(
            isinstance(item.context_expr, ast.Call)
            and getattr(item.context_expr.func, "id", None) == "_publishing"
            for item in node.items
        ):
            guarded.extend(
                inner
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and getattr(inner.func, "attr", None) == "post"
            )
    posts = [
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "post"
    ]
    assert posts and posts == guarded, "every canonical ingest POST must run inside _publishing"


def _seed_tenant_check(env_value: str | None):
    """Run seed.py's module-level tenant statements (and only those) under an environment."""
    import os as _os

    tree = ast.parse((ROOT / "services" / "qdrant-seed" / "seed.py").read_text(encoding="utf-8"))
    nodes = [
        n
        for n in tree.body
        if (
            isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "SEED_TENANT_ID" for t in n.targets)
        )
        or (isinstance(n, ast.If) and "SEED_TENANT_ID" in ast.unparse(n.test))
    ]
    env = {} if env_value is None else {"QDRANT_SEED_TENANT_ID": env_value}
    fake_os = type("O", (), {"getenv": staticmethod(lambda k, d=None: env.get(k, d))})
    ns = {"os": fake_os, "RuntimeError": RuntimeError, "_os": _os}
    exec(compile(ast.Module(nodes, []), "seed.py", "exec"), ns)  # noqa: S102 - our own source
    return ns["SEED_TENANT_ID"]


@pytest.mark.parametrize("tenant", [None, "__seed_quarantine__", "__global__"])
def test_the_reference_seeder_accepts_only_the_reserved_tenants(tenant):
    assert _seed_tenant_check(tenant) == (tenant or "__seed_quarantine__")


@pytest.mark.parametrize("tenant", ["tenant-a", "00000000-0000-0000-0000-000000000001", " "])
def test_the_reference_seeder_refuses_a_tenant_it_could_publish_past_the_lock(tenant):
    with pytest.raises(RuntimeError):
        _seed_tenant_check(tenant)
