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
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool")

    def _boom(*_a, **_k):
        raise exc

    client._request = _boom  # type: ignore[method-assign]
    return client


def _client_ok() -> pq.QdrantHttpClient:
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool")
    client._request = lambda *_a, **_k: {"result": {}}  # type: ignore[method-assign]
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
    created: list[str] = []
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool")
    client.probe_collection = lambda: Status.NOT_FOUND  # type: ignore[method-assign]
    client._request = lambda method, *_a, **_k: created.append(method) or {}  # type: ignore[method-assign]
    client.ensure_collection()
    assert created == ["PUT"], "غياب مُثبَت (404) ⇒ يُنشأ"


@pytest.mark.parametrize(
    "status", [Status.UNAUTHORIZED, Status.UNAVAILABLE, Status.INVALID_RESPONSE]
)
def test_ensure_collection_fails_closed_on_inconclusive_probe(status):
    """لا إنشاء على أساس فشل غير مُصنَّف — والرسالة تسمّي التصنيف لا «تعذّر الإنشاء»."""
    created: list[str] = []
    client = pq.QdrantHttpClient("http://qdrant:6333", "sahool")
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
