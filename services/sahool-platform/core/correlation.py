"""طبقة ربط (correlation) خفيفة — نمط OpenTelemetry بلا تبعيّة ثقيلة.

النمط مستلهَم من OpenTelemetry/distributed tracing — لكن خفيف، نقيّ-بايثون،
بلا collector/exporter/agent (نفس فلسفة workflow_engine: نمط لا infra ثقيلة).

يسدّ فجوة حقيقيّة: النظام يملك operation_id/workflow_id/event_id/command_id،
لكنّها **منفصلة** — لا خيط يربط السلسلة الكاملة عبر الخدمات. عند تتبّع مشكلة
("أيّ workflow أنتج أيّ command أنتج أيّ event؟") لا رابط. هذا يضيف
correlation_id واحداً يمرّ بكلّ شيء + causation (من أنتج من).

التصميم:
- correlation_id: ثابت طوال السلسلة (الطلب الواحد عبر الخدمات).
- causation_id: معرّف الخطوة التي أنتجت هذه (الأب المباشر) — لبناء الشجرة.
- contextvars: انتشار تلقائي ضمن async دون تمرير يدوي (آمن مع concurrency).
- صدق: لا يخترع ربطاً؛ يسجّل ما يُمرَّر فعلاً. غياب السياق يُعلَن (None).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

# سياق الربط الحالي (ينتشر تلقائيّاً ضمن async tasks)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_causation_id: ContextVar[str | None] = ContextVar("causation_id", default=None)


def new_correlation_id() -> str:
    """يولّد correlation_id جديداً (بداية سلسلة/طلب)."""
    return f"corr-{uuid.uuid4().hex[:16]}"


def set_correlation(correlation_id: str | None = None, causation_id: str | None = None) -> str:
    """يضبط سياق الربط الحالي. يولّد correlation_id إن لم يُمرَّر.

    Returns: الـcorrelation_id الفعّال (للتسجيل/التمرير لخدمة تالية).
    """
    cid = correlation_id or new_correlation_id()
    _correlation_id.set(cid)
    _causation_id.set(causation_id)
    return cid


def get_correlation_id() -> str | None:
    """الـcorrelation_id الحالي (None إن لم يُضبَط — صدق: لا اختراع)."""
    return _correlation_id.get()


def get_causation_id() -> str | None:
    """معرّف السبب المباشر (الأب) الحالي."""
    return _causation_id.get()


def correlation_headers() -> dict:
    """رؤوس HTTP لتمرير السياق لخدمة تالية (انتشار عبر الخدمات).

    صدق: يُمرّر فقط ما هو مضبوط فعلاً (لا رؤوس فارغة مضلّلة).
    """
    h: dict = {}
    cid = _correlation_id.get()
    if cid:
        h["X-Correlation-Id"] = cid
    cause = _causation_id.get()
    if cause:
        h["X-Causation-Id"] = cause
    return h


def from_headers(headers: dict) -> str:
    """يستخرج/ينشئ سياق الربط من رؤوس طلب وارد (انتشار عبر الخدمات).

    إن حمل الطلب X-Correlation-Id (من خدمة سابقة) نواصله؛ وإلّا نبدأ سلسلة
    جديدة. الـcausation يصبح ما حمله الطلب (الخطوة السابقة سبب هذه).
    """
    incoming = headers.get("X-Correlation-Id") or headers.get("x-correlation-id")
    cause = headers.get("X-Causation-Id") or headers.get("x-causation-id")
    return set_correlation(incoming, cause)


@dataclass
class TraceLink:
    """رابط واحد في السلسلة: كيان (workflow/command/event) + سببه المباشر."""

    kind: str  # "workflow" | "command" | "event" | "operation" | ...
    entity_id: str
    correlation_id: str
    causation_id: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "entity_id": self.entity_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "metadata": self.metadata,
        }


def link(kind: str, entity_id: str, metadata: dict | None = None) -> TraceLink:
    """يبني رابط trace للكيان الحالي تحت السياق الحالي.

    يربط الكيان (مثلاً event جديد) بالـcorrelation الحالي وبالسبب المباشر.
    استخدامه عند إنشاء workflow/command/event يبني الشجرة الكاملة لاحقاً.
    """
    return TraceLink(
        kind=kind,
        entity_id=entity_id,
        correlation_id=_correlation_id.get() or new_correlation_id(),
        causation_id=_causation_id.get(),
        metadata=metadata or {},
    )


def build_trace_tree(links: list[TraceLink]) -> dict:
    """يبني شجرة سببيّة من روابط trace لنفس الـcorrelation (للرصد).

    صدق: يجمع فقط روابط نفس الـcorrelation_id؛ يبني علاقة سبب→نتيجة من
    causation_id. الروابط بلا سبب = جذور. يكشف اليتيمة (سبب مفقود) بصدق.
    """
    if not links:
        return {"correlation_id": None, "roots": [], "total": 0}
    cid = links[0].correlation_id
    same = [lnk for lnk in links if lnk.correlation_id == cid]
    by_id = {lnk.entity_id: lnk for lnk in same}
    children: dict = {}
    roots: list = []
    orphans: list = []
    for lnk in same:
        if lnk.causation_id is None:
            roots.append(lnk.entity_id)
        elif lnk.causation_id in by_id:
            children.setdefault(lnk.causation_id, []).append(lnk.entity_id)
        else:
            orphans.append(lnk.entity_id)  # سبب مفقود — يُعلَن بصدق
    return {
        "correlation_id": cid,
        "total": len(same),
        "roots": roots,
        "children": children,
        "orphans": orphans,  # روابط بسبب مفقود (لا نخفيها)
    }
