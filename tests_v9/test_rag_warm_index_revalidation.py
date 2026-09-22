"""D10 — فهرسُ RAG الدافئ يُراجِع صلاحيّتَه ولا يفترضها دائمة.

**العطلُ الذي وُجِد هذا لأجله (تدقيق 2026-09-22، RG-01..04):** شرطُ المطابقة
(`scroll == count`) يُفحَص **عند البناء** فقط. فبعده يعود المسارُ الدافئ من
`_ensure_sparse_index` بـ`_sparse_report` المحفوظ بلا استدعاء `count` ولا
`rebuild`. المقيس: بدأت المجموعةُ بعددٍ ١، وبعد البناء صار المصدرُ ٢ — فعاد
النداءُ التالي بالعدد **١**. فيُخدَم استرجاعٌ متقادمٌ بثقةِ فهرسٍ مُتحقَّقٍ منه.

**والحدُّ مُعلَنٌ كما أعلنه التدقيق:** الاستيعابُ داخل العمليّة نفسِها يُبطِل
`_sparse_ready` سلفاً، فالخطرُ يخصّ **كاتباً خارجيّاً** أو نسخةً أخرى أو تغيُّرَ
المجموعة خارج هذا المسار. ولم يُثبَت تقادمُ استرجاعٍ حيّ ولا وجودُ Qdrant منشورة
في البيئة الحاليّة — هذا قياسُ دالّةٍ بمُضاعَفاتٍ محقونة، لا شهادةُ تشغيل.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "services/rag-retrieval/main.py"


@pytest.fixture
def rag():
    """يحمّل الوحدةَ بمُضاعَفاتٍ محقونة — بلا Qdrant ولا Ollama."""
    pytest.importorskip("fastapi")
    svc = str(ROOT / "services/rag-retrieval")
    if svc not in sys.path:
        sys.path.insert(0, svc)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("rag_main_d10", SRC)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 — تبعيّاتٌ ناقصةٌ في بيئةٍ خفيفة
        pytest.skip("تعذّر استيراد rag-retrieval (تبعيّات ناقصة)")
    return module


class _Qdrant:
    def __init__(self, count: int):
        self.count = count
        self.count_calls = 0

    def collection_point_count(self) -> int:
        self.count_calls += 1
        return self.count


class _Retriever:
    def __init__(self, qdrant: _Qdrant):
        self._q = qdrant
        self.rebuilds = 0

    def rebuild_sparse_index(self) -> dict:
        self.rebuilds += 1
        # `corpus_identity` جزءٌ من عقد `readiness_problems`: بلا بصمةِ مجموعةٍ
        # مقيسةٍ يفشل الحكمُ مغلقاً — والمُضاعَفُ يطابق العقدَ ولا يلتفّ عليه.
        return {
            "total_points": self._q.count,
            "loaded_chunks": self._q.count,
            "skipped_points": 0,
            "corpus_identity": {
                "id_set_digest": f"digest-of-{self._q.count}",
                "point_count": self._q.count,
            },
        }


def _wire(rag, count: int):
    q = _Qdrant(count)
    r = _Retriever(q)
    rag._qdrant = q
    rag._retriever = r
    rag._sparse_ready = False
    rag._sparse_report = {"total_points": 0, "loaded_chunks": 0, "skipped_points": 0}
    rag._sparse_checked_at = 0.0
    rag._SPARSE_REVALIDATE_SECONDS = 0.0  # لا انتظار: القياسُ عن الصلاحيّة لا التوقيت
    return q, r


def test_a_corpus_that_grew_under_a_warm_index_is_detected(rag):
    """الحالةُ الفارقة: المجموعةُ تغيّرت **بعد** البناء.

    كان المسارُ الدافئ يعود بالعدد القديم بلا استدعاء `count` أصلاً.
    """
    q, r = _wire(rag, 1)

    first = rag._ensure_sparse_index()
    assert first["total_points"] == 1 and r.rebuilds == 1

    q.count = 2  # كاتبٌ خارجيٌّ أضاف نقطة
    second = rag._ensure_sparse_index()

    assert second["total_points"] == 2, "المسارُ الدافئ خدم عدداً متقادماً"
    assert r.rebuilds == 2, "لم يُعَد البناءُ رغم تغيُّر المجموعة"


def test_an_unchanged_corpus_does_not_trigger_a_rebuild(rag):
    """والاتّجاه الآخر: مجموعةٌ لم تتغيّر لا تُعاد بناءً — وإلّا صار العلاجُ كلفة."""
    q, r = _wire(rag, 3)

    rag._ensure_sparse_index()
    rag._ensure_sparse_index()
    rag._ensure_sparse_index()

    assert r.rebuilds == 1, "أُعيد البناءُ بلا تغيُّرٍ في المجموعة"
    assert q.count_calls >= 2, "لم يُعَد التحقّقُ أصلاً — العطلُ قائم"


def test_a_count_failure_does_not_drop_a_valid_warm_index(rag):
    """تعذُّرُ العدّ لا يُسقِط فهرساً صالحاً ولا يُفشِل المسارَ الدافئ.

    إسقاطُه كان سيحوّل عُطلاً عابراً في Qdrant إلى انقطاعِ استرجاعٍ كامل.
    """
    q, r = _wire(rag, 5)
    rag._ensure_sparse_index()

    def _boom():
        raise RuntimeError("qdrant unreachable")

    q.collection_point_count = _boom
    out = rag._ensure_sparse_index()

    assert out["total_points"] == 5
    assert r.rebuilds == 1, "أُعيد البناءُ على تعذُّرِ عدٍّ عابر"


def test_the_revalidation_window_suppresses_repeated_counts(rag):
    """والنافذةُ تمنع عدّاً في كلّ نداء — مقايضةٌ مُعلَنةٌ بين الكلفة والتقادم."""
    q, r = _wire(rag, 4)
    rag._SPARSE_REVALIDATE_SECONDS = 3600.0  # نافذةٌ طويلة

    rag._ensure_sparse_index()
    calls_after_build = q.count_calls
    rag._ensure_sparse_index()
    rag._ensure_sparse_index()

    assert q.count_calls == calls_after_build, "عُدَّت المجموعةُ داخل النافذة"
    assert r.rebuilds == 1
