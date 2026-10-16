"""تصنيف استجلاء مجموعة Qdrant — SILENT-EXCEPTION-HANDLERS-11-01 (سلوكيّ).

كان ``ensure_collection`` يلتقط ``RuntimeError`` عارياً ويقرأه «المجموعة غير موجودة»،
بينما ``_request`` يطوي **كلّ** ``HTTPError`` في ``RuntimeError`` واحد. فمفتاح API خاطئ
(401) أو خدمة ساقطة (503) كانا يقودان إلى محاولة **إنشاء** المجموعة، فتفشل بخطأ ثانٍ
مُربِك بعد أن ضاع السبب الجذريّ. تشخيص «لماذا لا يصل RAG إلى Qdrant» كان أصعب ممّا يجب.

سطر تسجيل وحده ما كان ليكفي: العيب أنّ **رمز الحالة يُفقَد**، لا أنّه لا يُطبَع. فالعلاج
خطأ مُصنَّف يحفظ ``.status`` + تعداد نتيجة، والمستهلك يقرّر الإغلاق أو التدهور.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from copy import deepcopy
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "production_qdrant", ROOT / "services/sahool-platform/core/rag/production_qdrant.py"
)
pq = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
# التسجيل قبل التنفيذ: `@dataclass` يحلّ التلميحات عبر `sys.modules[cls.__module__]`،
# فبدونه ينهار التحميل الديناميكيّ بـAttributeError على None.
sys.modules["production_qdrant"] = pq
_SPEC.loader.exec_module(pq)

Status = pq.CollectionProbeStatus


def _client_raising(exc: Exception) -> pq.QdrantHttpClient:
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=384)

    def _boom(*_a, **_k):
        raise exc

    client._request = _boom  # type: ignore[method-assign]
    return client


def _client_ok() -> pq.QdrantHttpClient:
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=384)
    client._request = lambda *_a, **_k: {"result": {}}  # type: ignore[method-assign]
    return client


class _CollectionServer:
    """Small HTTP-state fixture: index writes cannot replace collection data."""

    def __init__(self, *, exists=True):
        self.exists = exists
        self.payload_schema = {}
        self.points = {"retained": {"metadata": {"tenant_id": "tenant-a"}}} if exists else {}
        self.calls = []
        self.index_reply = {"status": "ok", "result": {"status": "completed"}}
        self.persist_index = True
        self.index_error = None

    def request(self, method, path, payload=None):
        self.calls.append((method, path, deepcopy(payload)))
        if method == "GET" and path == "/collections/sahool":
            if not self.exists:
                raise pq.QdrantHTTPError(404, "not found")
            return {
                "status": "ok",
                "result": {
                    "config": {"params": {"vectors": {"size": 384, "distance": "Cosine"}}},
                    "payload_schema": deepcopy(self.payload_schema),
                },
            }
        if method == "PUT" and path == "/collections/sahool":
            assert not self.exists, "existing collections must never be recreated"
            self.exists = True
            return {"status": "ok", "result": True}
        if method == "PUT" and path == "/collections/sahool/index?wait=true":
            assert payload == {"field_name": "metadata.tenant_id", "field_schema": "keyword"}
            if self.index_error:
                raise self.index_error
            if self.persist_index:
                self.payload_schema["metadata.tenant_id"] = {"data_type": "keyword", "points": 1}
            return deepcopy(self.index_reply)
        raise AssertionError(f"unexpected or destructive request: {method} {path}")

    def client(self):
        client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=384)
        client._request = self.request
        return client


# ───────────────── كلّ صنف خطأ يُصنَّف على حدة ─────────────────


def test_existing_collection_is_exists():
    assert _client_ok().probe_collection() is Status.EXISTS


def test_404_is_not_found():
    c = _client_raising(pq.QdrantHTTPError(404, "not found"))
    assert c.probe_collection() is Status.NOT_FOUND


@pytest.mark.parametrize("code", [401, 403])
def test_auth_failure_is_not_read_as_absent(code: int):
    """الانحدار الأصليّ: 401 كان يُقرأ «غير موجودة» فيُحاوَل الإنشاء."""
    c = _client_raising(pq.QdrantHTTPError(code, "unauthorized"))
    assert c.probe_collection() is Status.UNAUTHORIZED


@pytest.mark.parametrize("code", [408, 429, 500, 503])
def test_timeout_ratelimit_and_server_errors_are_unavailable(code: int):
    c = _client_raising(pq.QdrantHTTPError(code, "boom"))
    assert c.probe_collection() is Status.UNAVAILABLE


def test_malformed_json_is_invalid_response():
    c = _client_raising(json.JSONDecodeError("bad", "{", 0))
    assert c.probe_collection() is Status.INVALID_RESPONSE


def test_network_failure_is_unavailable_not_absent():
    """انقطاع شبكة ليس غياب مجموعة — والفرق يقرّر: أعِد المحاولة أم أنشِئ."""
    c = _client_raising(urllib.error.URLError("connection refused"))
    assert c.probe_collection() is Status.UNAVAILABLE


# ───────────────── الأثر على القرار ─────────────────


def test_ensure_collection_creates_only_on_proven_absence():
    server = _CollectionServer(exists=False)
    server.client().ensure_collection()
    writes = [(method, path) for method, path, _ in server.calls if method != "GET"]
    assert writes == [
        ("PUT", "/collections/sahool"),
        ("PUT", "/collections/sahool/index?wait=true"),
    ], "غياب مُثبَت (404) ⇒ مجموعة ثمّ فهرس، بلا مساس بالنقاط"


@pytest.mark.parametrize("exists", [True, False])
def test_tenant_index_reconciles_existing_and_new_collection_idempotently(exists):
    server = _CollectionServer(exists=exists)
    points_before = deepcopy(server.points)
    client = server.client()
    client.ensure_collection()
    assert server.payload_schema["metadata.tenant_id"]["data_type"] == "keyword"
    writes_after_first = [call for call in server.calls if call[0] != "GET"]
    client.ensure_collection()
    assert [call for call in server.calls if call[0] != "GET"] == writes_after_first
    assert len(writes_after_first) == (1 if exists else 2)
    assert server.points == points_before


@pytest.mark.parametrize("params", [None, {"type": "keyword", "is_tenant": True}])
def test_existing_keyword_tenant_index_is_preserved_without_any_write(params):
    server = _CollectionServer()
    server.payload_schema = {
        "metadata.tenant_id": {"data_type": "keyword", "params": params, "points": 1},
        "other_field": {"data_type": "integer", "points": 1},
    }
    before = deepcopy(server.payload_schema)
    server.client().ensure_collection()
    assert all(method == "GET" for method, _, _ in server.calls)
    assert server.payload_schema == before


@pytest.mark.parametrize("schema", [None, [], "unknown"])
def test_unknown_payload_schema_does_not_trigger_a_write(schema):
    server = _CollectionServer()
    server.payload_schema = schema
    with pytest.raises(ValueError, match="payload schema"):
        server.client().ensure_collection()
    assert all(method == "GET" for method, _, _ in server.calls)


@pytest.mark.parametrize(
    "index",
    [
        None,
        "keyword",
        {},
        {"data_type": "integer"},
        {"data_type": "text"},
        {"data_type": "keyword", "params": {"type": "integer"}},
    ],
)
def test_incompatible_tenant_index_is_rejected_without_replacing_it(index):
    server = _CollectionServer()
    server.payload_schema["metadata.tenant_id"] = index
    with pytest.raises(ValueError, match="tenant payload index"):
        server.client().ensure_collection()
    assert all(method == "GET" for method, _, _ in server.calls)
    assert server.payload_schema["metadata.tenant_id"] == index


@pytest.mark.parametrize(
    "error",
    [
        pq.QdrantHTTPError(401, "denied"),
        pq.QdrantHTTPError(403, "forbidden"),
        pq.QdrantHTTPError(503, "unavailable"),
        urllib.error.URLError("offline"),
        json.JSONDecodeError("invalid", "{", 0),
    ],
)
def test_payload_index_api_errors_propagate_without_claiming_success(error):
    server = _CollectionServer()
    server.index_error = error
    with pytest.raises(type(error)) as exc:
        server.client().ensure_collection()
    assert exc.value is error
    assert server.payload_schema == {}
    assert [(m, p) for m, p, _ in server.calls if m != "GET"] == [
        ("PUT", "/collections/sahool/index?wait=true")
    ]


@pytest.mark.parametrize(
    "reply",
    [
        None,
        [],
        {},
        {"status": "error", "result": {"status": "completed"}},
        {"status": "ok", "result": None},
        {"status": "ok", "result": {"status": "acknowledged"}},
        {"status": "ok", "result": {"status": "wait_timeout"}},
    ],
)
def test_incomplete_index_creation_is_not_reported_as_success(reply):
    server = _CollectionServer()
    server.index_reply = reply
    with pytest.raises(RuntimeError, match="payload index"):
        server.client().ensure_collection()


def test_index_creation_requires_schema_readback_not_just_success_reply():
    server = _CollectionServer()
    server.persist_index = False
    with pytest.raises(RuntimeError, match="payload index"):
        server.client().ensure_collection()


def test_index_reconciliation_does_not_change_tenant_and_global_search_filters():
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=384)
    calls = []
    client._request = lambda *args: calls.append(args) or {"result": []}
    assert client.search([0.1], tenant_id="tenant-a", filters={"crop": "wheat"}) == []
    assert calls[0][2]["filter"] == {
        "must": [
            {"key": "metadata.tenant_id", "match": {"any": ["tenant-a", "__global__"]}},
            {
                "should": [
                    {"key": "metadata.crop", "match": {"value": "wheat"}},
                    {
                        "must": [
                            {"key": "metadata.tenant_id", "match": {"value": "__global__"}},
                            {
                                "should": [
                                    {"is_empty": {"key": "metadata.crop"}},
                                    {"is_null": {"key": "metadata.crop"}},
                                ]
                            },
                        ]
                    },
                ]
            },
        ]
    }


@pytest.mark.parametrize(
    "status", [Status.UNAUTHORIZED, Status.UNAVAILABLE, Status.INVALID_RESPONSE]
)
def test_ensure_collection_fails_closed_on_inconclusive_probe(status):
    """لا إنشاء على أساس فشل غير مُصنَّف — والرسالة تسمّي التصنيف لا «تعذّر الإنشاء»."""
    created: list[str] = []
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=384)
    client.probe_collection = lambda: status  # type: ignore[method-assign]
    client._request = lambda method, *_a, **_k: created.append(method) or {}  # type: ignore[method-assign]
    with pytest.raises(RuntimeError) as exc:
        client.ensure_collection()
    assert status.value in str(exc.value)
    assert created == [], "لم يكن يجوز إنشاء مجموعة بعد استجلاء غير حاسم"


def test_typed_error_keeps_the_status_code_reachable():
    """العيب الأصليّ: الرمز كان داخل نصّ الرسالة فقط — غير قابل للقراءة برمجيّاً."""
    err = pq.QdrantHTTPError(401, "no key")
    assert err.status == 401
    assert isinstance(err, RuntimeError), "التوافق: مستهلكو RuntimeError يبقون عاملين"


def test_existing_collection_vector_dimension_must_match_embedding_dimension():
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=0)
    client.probe_collection = lambda: Status.EXISTS  # type: ignore[method-assign]
    client.collection_vector_size = lambda: 768  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="vector-size mismatch"):
        client.ensure_collection(vector_size=384)


def test_collection_vector_size_reads_unnamed_vector_schema():
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool", vector_size=0)
    client._request = lambda *_a, **_k: {
        "result": {"config": {"params": {"vectors": {"size": 768, "distance": "Cosine"}}}}
    }  # type: ignore[method-assign]
    assert client.collection_vector_size() == 768


def test_ollama_embedding_provider_learns_dimension_and_rejects_drift(monkeypatch):
    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    payloads = iter([{"embedding": [0.1, 0.2, 0.3]}, {"embedding": [0.4, 0.5]}])
    monkeypatch.setattr(pq.urllib.request, "urlopen", lambda *_a, **_k: Resp(next(payloads)))
    provider = pq.OllamaEmbeddingProvider("http://ollama:11434", "nomic-embed-text")
    assert provider.embed("a") == [0.1, 0.2, 0.3]
    assert provider.dimensions == 3
    with pytest.raises(ValueError, match="dimension changed"):
        provider.embed("b")
