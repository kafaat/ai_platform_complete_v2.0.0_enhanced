"""stream_registry.py — سجلّ بثوث نشِط في الذاكرة (خالٍ من fastapi).

سجلّ خيطيّ الأمان (``threading.Lock``) معزول بالمستأجِر لحالة البثوث الحيّة.
منطق صرف قابل للاختبار الوحدويّ — لا ``datetime.now`` عند الاستيراد؛ الطابع الزمنيّ
يُحقَن من المُستدعي (تحديد سلوكيّ). ``list_by_tenant`` لا يُسرّب بثوث مستأجِر آخر.

يبقى خالياً من fastapi/httpx كي تختبره طبقة الوحدات (بلا خدمات).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Any

# الحالات القانونيّة لدورة حياة البثّ.
VALID_STATES: frozenset[str] = frozenset({"pending", "live", "recording", "stopped", "error"})


@dataclass(frozen=True)
class StreamEntry:
    """قيد بثّ غير قابل للتعديل — يُعاد كنسخة كي لا يُفسِد المُستدعي حالة السجلّ."""

    stream_id: str
    tenant_id: str
    source_url: str
    state: str
    created_at: Any
    last_event: str | None = None


class StreamRegistry:
    """سجلّ بثوث نشِط، خيطيّ الأمان، معزول بالمستأجِر (في الذاكرة).

    كلّ العمليّات تحت قفل واحد؛ العائد نسخ ``StreamEntry`` مجمّدة كي لا تتسرّب مراجع
    قابلة للتعديل إلى المُستدعي. الطابع الزمنيّ (``created_at``) يُحقَن — لا يُقرأ من
    الساعة داخليّاً — فالسلوك محدَّد وقابل للاختبار.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[str, StreamEntry] = {}

    def register(
        self,
        *,
        stream_id: str,
        tenant_id: str,
        source_url: str,
        created_at: Any,
        state: str = "pending",
        last_event: str | None = None,
    ) -> StreamEntry:
        """يسجّل (أو يستبدل) قيد بثّ. حالة غير قانونيّة ⇒ ``ValueError``."""
        if state not in VALID_STATES:
            raise ValueError(f"حالة بثّ غير قانونيّة: {state!r} (المسموح: {sorted(VALID_STATES)})")
        entry = StreamEntry(
            stream_id=stream_id,
            tenant_id=str(tenant_id),
            source_url=source_url,
            state=state,
            created_at=created_at,
            last_event=last_event,
        )
        with self._lock:
            self._streams[stream_id] = entry
        return entry

    def get(self, stream_id: str) -> StreamEntry | None:
        """يُرجِع قيد البثّ (نسخة) أو ``None`` إن لم يُسجَّل."""
        with self._lock:
            return self._streams.get(stream_id)

    def list_by_tenant(self, tenant_id: str) -> list[StreamEntry]:
        """بثوث المستأجِر فقط — لا يُسرّب أبداً بثوث مستأجِر آخر.

        مستأجِر فارغ ⇒ قائمة فارغة (fail-closed: لا يطابق أيّ بثّ مملوك).
        """
        tid = str(tenant_id or "")
        if not tid:
            return []
        with self._lock:
            return [e for e in self._streams.values() if e.tenant_id == tid]

    def update_state(
        self, stream_id: str, state: str, last_event: str | None = None
    ) -> StreamEntry | None:
        """ينقل بثّاً إلى حالة جديدة. غير مسجَّل ⇒ ``None``؛ حالة غير قانونيّة ⇒ ``ValueError``."""
        if state not in VALID_STATES:
            raise ValueError(f"حالة بثّ غير قانونيّة: {state!r} (المسموح: {sorted(VALID_STATES)})")
        with self._lock:
            cur = self._streams.get(stream_id)
            if cur is None:
                return None
            updated = replace(
                cur,
                state=state,
                last_event=last_event if last_event is not None else cur.last_event,
            )
            self._streams[stream_id] = updated
            return updated

    def remove(self, stream_id: str) -> bool:
        """يزيل بثّاً. يُرجِع ``True`` إن كان موجوداً، وإلّا ``False``."""
        with self._lock:
            return self._streams.pop(stream_id, None) is not None
