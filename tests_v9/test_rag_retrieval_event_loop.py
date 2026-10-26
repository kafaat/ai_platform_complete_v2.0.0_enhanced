"""``rag-retrieval`` لا يحجز حلقةَ الأحداث بإدخالٍ/إخراجٍ حاجب.

``/readyz`` و``/v1/search`` كانا ``async def`` يستدعيان urllib مباشرةً (تضمين Ollama
بمهلة ٢٠ ث، Qdrant بمهلة ٢٠ ث، تمريرٌ كامل للمجموعة) — ومع عاملِ uvicorn واحد يتوقّف
كلُّ طلبٍ آخر (``/healthz`` منها) حتّى يعود النداءُ البطيء. يُقاس هنا أنّ طلباً متزامناً
يكتمل بينما مُضاعَفٌ بطيء محجوز، وأنّ الحالةَ المشتركة تُلمَس تحت القفل.

فحص صرف بمُضاعَفاتٍ محقونة — بلا Qdrant ولا Ollama.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
RAG_MAIN = ROOT / "services" / "rag-retrieval" / "main.py"


@pytest.fixture
def rag(monkeypatch):
    pytest.importorskip("fastapi")
    for path in (str(RAG_MAIN.parent), str(ROOT)):
        if path not in sys.path:
            monkeypatch.syspath_prepend(path)
    monkeypatch.delenv("RAG_REINDEX_PROFILE_MANIFEST", raising=False)
    spec = importlib.util.spec_from_file_location("_rag_event_loop_main", RAG_MAIN)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 — تبعيّاتٌ ناقصةٌ في بيئةٍ خفيفة
        pytest.skip("تعذّر استيراد rag-retrieval (تبعيّات ناقصة)")
    return module


def _slow_call(started: threading.Event, release: threading.Event, result):
    def call(*_args, **_kwargs):
        started.set()
        release.wait(2.0)
        return result

    return call


async def _loop_stays_free(handler_coro, started, release) -> bool:
    task = asyncio.ensure_future(handler_coro)
    for _ in range(200):
        if started.is_set():
            break
        await asyncio.sleep(0.01)
    # If the handler ran the slow call on the loop thread, it has already finished
    # (after the stub's 2 s timeout) by the time this coroutine resumes.
    still_running = not task.done()
    release.set()
    await task
    return still_running


def test_readyz_runs_the_blocking_probe_off_the_event_loop(rag, monkeypatch):
    started, release = threading.Event(), threading.Event()
    rag._embedding_provider = types.SimpleNamespace(embed=_slow_call(started, release, [0.0] * 768))
    rag._qdrant = types.SimpleNamespace(collection_vector_size=lambda: 768)
    monkeypatch.setattr(rag, "_ensure_sparse_index", lambda: {"loaded_chunks": 3})

    assert asyncio.run(_loop_stays_free(rag.readyz(), started, release)), (
        "/readyz blocked the event loop while the embedding call was in flight"
    )


def test_search_runs_retrieval_off_the_event_loop_and_under_the_lock(rag, monkeypatch):
    started, release = threading.Event(), threading.Event()
    held: list[bool] = []
    slow = _slow_call(started, release, [])

    def retrieve(*args, **kwargs):
        held.append(rag._RETRIEVAL_LOCK.locked())
        return slow(*args, **kwargs)

    rag._retriever = types.SimpleNamespace(retrieve=retrieve)
    monkeypatch.setattr(rag, "_ensure_sparse_index", lambda: {"loaded_chunks": 1})
    monkeypatch.setattr(rag, "visible_corpus_count", lambda _report, _tenant: 1)
    req = rag.SearchRequest(tenant_id="tenant-a", query="wheat")

    assert asyncio.run(
        _loop_stays_free(rag.search(req, x_tenant_id="tenant-a"), started, release)
    ), "/v1/search blocked the event loop while retrieval was in flight"
    assert held == [True], "retrieval touched the shared index without the lock"
