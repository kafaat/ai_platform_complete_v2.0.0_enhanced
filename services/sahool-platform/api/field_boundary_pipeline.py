"""api/field_boundary_pipeline.py — إطار pipeline استخلاص حدود الحقل (7 مراحل).

هذا هو **إطار التشغيل** (framework) الذي يُجسّد معماريّة استخلاص الحدود التي
حدّدها المستخدم، كسلسلة مراحل تصريحيّة (declarative staged pipeline) — **وليس**
نموذج ML واحد غامض. المعماريّة بترتيبها:

    multi_temporal_composite → crop_mask → delineation → polygon_vectorize
        → topology_clean → confidence_score → human_review → (persist)

مبدأ الصدق (لا حدود مُلفّقة):
  • المراحل الحتميّة/القابلة للتنفيذ (تَجهيز المتجهات، تنظيف الطوبولوجيا،
    حساب الثقة، بوّابة المراجعة البشريّة، الحفظ) مُنفّذة فعليّاً كـhooks نقيّة
    تعمل على قاموس السياق (ctx) وقابلة للاختبار.
  • مراحل ML الثلاث (multi_temporal_composite, crop_mask, delineation) هي
    **سقالات صادقة (scaffolds)**: عند استدعائها دون نموذج/مزوّد راستر مُهيّأ
    تُعيد علامة واضحة {"status": "scaffold", ...} ولا تُلفّق أقنعة أو مضلّعات،
    وتُسجّل المرحلة في ctx["unimplemented_stages"]. يُمكن لاحقاً ربط تنفيذ
    حقيقيّ عبر register_stage_impl(stage_id).
  • تنظيف الطوبولوجيا الفعليّ يجري في PostGIS (متابعة منفصلة)؛ هنا hook
    تمريريّ فقط يحافظ على المضلّعات كما هي دون تعديل مُلفّق.

⚠ لا يُنتج هذا الإطار أيّ حدود/أقنعة/مضلّعات حقيقيّة من تلقاء نفسه — فهو
يُنظّم تدفّق المراحل بصدق بانتظار ربط النماذج وبيانات الراستر.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from api.field_boundary_contracts import validate_ml_stage_output

# نوع دالّة تنفيذ المرحلة: تأخذ السياق وتُعيد قاموس تحديثات يُدمج في السياق.
StageImpl = Callable[[dict], dict]


@dataclass(frozen=True)
class PipelineStage:
    """وصف تصريحيّ لمرحلة واحدة في pipeline الحدود (غير قابل للتعديل)."""

    id: str
    name_ar: str
    # نوع المرحلة بصدق: "ml" (سقالة) | "deterministic" | "hil" | "persist"
    kind: str
    description_ar: str


# ترتيب المراحل السبع + الحفظ كما حدّدها المستخدم، بأنواعها الصادقة.
BOUNDARY_PIPELINE: tuple[PipelineStage, ...] = (
    PipelineStage(
        id="multi_temporal_composite",
        name_ar="تركيب متعدّد الأزمنة",
        kind="ml",
        description_ar="بناء مُركّب راستر متعدّد الأزمنة (يحتاج بيانات راستر/مزوّد) — سقالة.",
    ),
    PipelineStage(
        id="crop_mask",
        name_ar="قناع المحصول",
        kind="ml",
        description_ar="تصنيف بكسلات المحصول لإنتاج قناع (يحتاج نموذج) — سقالة.",
    ),
    PipelineStage(
        id="delineation",
        name_ar="ترسيم الحدود",
        kind="ml",
        description_ar="استخلاص حدود الحقول من القناع (يحتاج نموذج) — سقالة.",
    ),
    PipelineStage(
        id="polygon_vectorize",
        name_ar="تَجهيز المضلّعات",
        kind="deterministic",
        description_ar="تحويل الحدود النقطيّة إلى مضلّعات متّجهة — hook حتميّ تمريريّ.",
    ),
    PipelineStage(
        id="topology_clean",
        name_ar="تنظيف الطوبولوجيا",
        kind="deterministic",
        description_ar="تنظيف الطوبولوجيا (التنفيذ الفعليّ في PostGIS) — hook تمريريّ.",
    ),
    PipelineStage(
        id="confidence_score",
        name_ar="حساب الثقة",
        kind="deterministic",
        description_ar="إسناد درجة ثقة للحدود — مبدئيّاً None بانتظار مدخلات ML.",
    ),
    PipelineStage(
        id="human_review",
        name_ar="المراجعة البشريّة",
        kind="hil",
        description_ar="بوّابة مراجعة بشريّة (human-in-the-loop) — تُعلّم الحالة كـ unreviewed.",
    ),
    PipelineStage(
        id="persist",
        name_ar="الحفظ",
        kind="persist",
        description_ar="حفظ الحدود في PostGIS — hook تمريريّ (لا اتّصال شبكة هنا).",
    ),
)


# ---------------------------------------------------------------------------
# سجلّ تنفيذ المراحل — يسمح بربط تنفيذ حقيقيّ لاحقاً لأيّ مرحلة.
# ---------------------------------------------------------------------------
_STAGE_IMPLS: dict[str, StageImpl] = {}


def register_stage_impl(stage_id: str) -> Callable[[StageImpl], StageImpl]:
    """مُزخرِف يربط دالّة تنفيذ حقيقيّة بمرحلة، فيتجاوز التنفيذ الافتراضيّ.

    الاستخدام:
        @register_stage_impl("crop_mask")
        def real_crop_mask(ctx: dict) -> dict:
            ...  # تنفيذ حقيقيّ يُعيد قاموس تحديثات للسياق
    """
    if stage_id not in {s.id for s in BOUNDARY_PIPELINE}:
        raise KeyError(f"مرحلة غير معروفة: {stage_id}")

    def _decorator(fn: StageImpl) -> StageImpl:
        _STAGE_IMPLS[stage_id] = fn
        return fn

    return _decorator


def _scaffold_marker(stage: PipelineStage) -> dict:
    """علامة سقالة صادقة لمراحل ML غير المُنفّذة — لا تُلفّق أيّ مخرجات."""
    return {
        "status": "scaffold",
        "stage": stage.id,
        "note_ar": "تحتاج نموذج/راستر — غير مُنفّذة",
    }


def _ml_scaffold_impl(stage: PipelineStage) -> StageImpl:
    """تنفيذ افتراضيّ لمرحلة ML: يُعيد علامة سقالة ويُسجّل المرحلة كغير مُنفّذة."""

    def _impl(ctx: dict) -> dict:
        unimplemented = ctx.setdefault("unimplemented_stages", [])
        if stage.id not in unimplemented:
            unimplemented.append(stage.id)
        # لا قناع/مضلّع مُلفّق — فقط علامة صادقة تحت مفتاح المرحلة.
        return {stage.id: _scaffold_marker(stage)}

    return _impl


def _polygon_vectorize_impl(ctx: dict) -> dict:
    """hook حتميّ: لا مضلّعات بلا مخرجات ترسيم حقيقيّة — يُمرّر الموجود فقط."""
    polygons = ctx.get("polygons")
    return {"polygons": polygons}  # لا تلفيق: يبقى None إن لم تُنتج delineation شيئاً


def _topology_clean_impl(ctx: dict) -> dict:
    """hook تمريريّ: التنظيف الفعليّ في PostGIS — هنا نمرّر المضلّعات كما هي."""
    return {
        "polygons": ctx.get("polygons"),
        "topology_note_ar": "التنظيف الفعليّ يجري في PostGIS (متابعة منفصلة).",
    }


def _confidence_score_impl(ctx: dict) -> dict:
    """hook حتميّ: ثقة مبدئيّة None — لا رقم مُلفّق بلا مدخلات ML."""
    return {
        "confidence": None,
        "confidence_note_ar": "لا درجة ثقة بلا مخرجات ML حقيقيّة (مبدئيّاً None).",
    }


def _human_review_impl(ctx: dict) -> dict:
    """بوّابة HIL: تُعلّم الحدود بأنّها بانتظار مراجعة بشريّة."""
    return {"review_status": "unreviewed"}


def _persist_impl(ctx: dict) -> dict:
    """hook حفظ: لا اتّصال شبكة/قاعدة بيانات هنا — يُعلّم النيّة فقط."""
    return {
        "persisted": False,
        "persist_note_ar": "الحفظ في PostGIS غير مُنفّذ هنا (لا اتّصال شبكة).",
    }


# التنفيذات الافتراضيّة: مراحل ML سقالات، والباقي hooks حتميّة حقيقيّة.
_DEFAULT_IMPLS: dict[str, StageImpl] = {
    "polygon_vectorize": _polygon_vectorize_impl,
    "topology_clean": _topology_clean_impl,
    "confidence_score": _confidence_score_impl,
    "human_review": _human_review_impl,
    "persist": _persist_impl,
}


def _impl_for(stage: PipelineStage) -> StageImpl:
    """يختار التنفيذ: المُسجّل عبر register_stage_impl له الأولويّة، ثمّ الافتراضيّ."""
    if stage.id in _STAGE_IMPLS:
        return _STAGE_IMPLS[stage.id]
    if stage.kind == "ml":
        return _ml_scaffold_impl(stage)
    return _DEFAULT_IMPLS[stage.id]


def run_pipeline(ctx: dict | None = None) -> dict:
    """يُشغّل مراحل BOUNDARY_PIPELINE بالترتيب على السياق ويُعيده مُحدّثاً.

    نقيّ: لا يرفع استثناءً على سياق طبيعيّ، ولا يُلفّق حدوداً. يُجمّع نتائج
    كلّ مرحلة في ctx ويُلخّص أيّها جرى فعليّاً وأيّها سقالة.
    """
    ctx = dict(ctx) if ctx else {}
    ctx.setdefault("unimplemented_stages", [])

    summary: list[dict] = []
    for stage in BOUNDARY_PIPELINE:
        impl = _impl_for(stage)
        overridden = stage.id in _STAGE_IMPLS
        updates = impl(ctx)
        if updates:
            ctx.update(updates)

        is_scaffold = stage.kind == "ml" and not overridden
        entry = {
            "stage": stage.id,
            "kind": stage.kind,
            "ran": "scaffold" if is_scaffold else "real",
            "overridden": overridden,
        }
        # تحقّق عقد المخرجات فقط لمراحل ML المُتجاوَزة بتنفيذ حقيقيّ —
        # السقالات الصادقة وكلّ المراحل الحتميّة تبقى مدخلاتها كما هي.
        if overridden and stage.kind == "ml":
            entry["contract_violations"] = validate_ml_stage_output(stage.id, updates or {})
        summary.append(entry)

    ctx["summary"] = summary
    return ctx


def list_stages() -> list[dict]:
    """يُعيد وصف المراحل بالترتيب (id, name_ar, kind, description_ar)."""
    return [
        {
            "id": s.id,
            "name_ar": s.name_ar,
            "kind": s.kind,
            "description_ar": s.description_ar,
        }
        for s in BOUNDARY_PIPELINE
    ]


def get_stage(stage_id: str) -> PipelineStage:
    """يُعيد وصف مرحلة بمعرّفها، أو يرفع KeyError إن لم تُوجد."""
    for s in BOUNDARY_PIPELINE:
        if s.id == stage_id:
            return s
    raise KeyError(f"مرحلة غير معروفة: {stage_id}")
