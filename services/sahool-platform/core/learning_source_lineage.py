"""core/learning_source_lineage.py — نَسَب مصدر التعلّم (Learning Source Lineage) — جسر #2.

يسدّ أخطر فجوة في حلقة التعلّم (تدقيق 2026-07-08): تحديثات التعلّم
(``online_learning_updates``) كانت **بلا رابط مصدر** — يتعذّر إثبات «أيّ نتيجة/قرار غيّر
السياسة؟» أو تمييز التعلّم من الضوضاء.

يُرجِع لكلّ تحديث نَسَبه الصريح + حكم قابليّة التتبّع + هل **يُطبَّق**:

  • ``source_type`` ∈ {recommendation_outcome, outcome_record, execution_feedback, human_feedback}
  • ``source_id`` + ``field_id``/``season_id``/``recommendation_id``/``decision_id``/``evidence_snapshot_id``
  • ``traceability_status`` ∈ {traceable, pending_review, rejected_untraceable}
  • ``applies``: **لا تحديث بلا مصدر يُطبِّق تغيير سياسة** — traceable فقط يُطبَّق.

قواعد الصدق:
  • نوع مصدر غير معروف/غائب ⇒ ``rejected_untraceable`` + ``applies=False``.
  • نوع صحيح لكن بلا معرّف ⇒ ``pending_review`` + ``applies=False`` (قرينة ناقصة، تُراجَع لا تُطبَّق).
  • نوع صحيح + معرّف ⇒ ``traceable`` + ``applies=True``.
  • المُصنِّف **كلّيّ**: أيّ مُدخَل يُنتِج حالةً واحدة (لا يتيم بلا حكم).

منطق نقيّ (لا شبكة/قاعدة) — يستدعيه كاتب online_learning_updates ومُلخِّص التعلّم.
"""

from __future__ import annotations

VALID_SOURCE_TYPES = frozenset(
    {"recommendation_outcome", "outcome_record", "execution_feedback", "human_feedback"}
)

_LINEAGE_KEYS = (
    "field_id",
    "season_id",
    "recommendation_id",
    "decision_id",
    "evidence_snapshot_id",
)


def classify_traceability(source_type: str | None, source_id: str | None) -> str:
    """يحكم قابليّة التتبّع من (النوع، المعرّف). كلّيّ: يُرجِع دائماً حالةً معروفة."""
    if not source_type or source_type not in VALID_SOURCE_TYPES:
        return "rejected_untraceable"
    if not source_id:
        return "pending_review"
    return "traceable"


def _pick(update: dict, src: dict, key: str):
    val = update.get(key)
    if val is None:
        val = src.get(key)
    if isinstance(val, str):
        val = val.strip() or None
    return val


def resolve_learning_source(update: dict) -> dict:
    """يستخرج نَسَب مصدر تحديث تعلّم ويحكم قابليّة تتبّعه وقابليّة تطبيقه.

    يقبل الحقول مسطّحة على ``update`` أو مُعشَّشة تحت ``update['source']``.
    يُعيد قاموساً بكلّ حقول النَّسَب + ``traceability_status`` + ``applies`` (bool).

    **حدٌّ مُعلَن (U07):** حقولُ المراجعة (``review_status``/``agronomically_approved``/``review``)
    تُحسَب هنا وتُعرَض في الملخّص، لكنّ كاتبَ ``online_learning_updates`` (``phase_runtime_store``)
    لا يُديمها — الجدولُ (v151) لا يملك عموداً لها، وإضافتُه هجرةٌ خلف GATE-01. الصفوفُ
    المقروءة بلا ``review_status`` تُعَدّ ``unreviewed`` (لا اعتماداً ضمنيّاً).
    """
    src = update.get("source") if isinstance(update.get("source"), dict) else {}
    source_type = _pick(update, src, "source_type")
    source_id = _pick(update, src, "source_id")
    status = classify_traceability(source_type, source_id)
    review = resolve_agronomic_review(update)
    out = {
        "source_type": source_type if source_type in VALID_SOURCE_TYPES else None,
        "source_id": source_id,
        "traceability_status": status,
        # صدق: فقط المُتتبَّع بالكامل يُطبِّق تغيير سياسة.
        "applies": status == "traceable",
        # U07 (التدقيق الموحَّد 2026-09-13): «قابل للتتبّع» شكلٌ (نوع + معرّف)، لا اعتمادٌ
        # زراعيّ. الاعتمادُ يحمل مراجِعاً وحكماً وأدلّة صريحة، ويُعلَن مستقلّاً.
        "review_status": review["review_status"],
        "agronomically_approved": review["agronomically_approved"],
        "review": review["review"],
    }
    for k in _LINEAGE_KEYS:
        out[k] = _pick(update, src, k)
    return out


_REVIEW_VERDICTS = frozenset({"approved", "rejected"})


def resolve_agronomic_review(update: dict) -> dict:
    """يحكم اعتمادَ المراجعة الزراعيّة من كتلة ``review`` (مسطّحة أو تحت ``source``).

    ``approved`` يشترط ``reviewer_id`` غير فارغ و``verdict == "approved"`` و``evidence_ids``
    غير فارغة — وإلّا ``unreviewed`` (أو ``rejected`` عند حكم الرفض الصريح). غيابُ الكتلة
    ⇒ ``unreviewed``، لا ``approved`` ضمناً.
    """
    src = update.get("source") if isinstance(update.get("source"), dict) else {}
    block = update.get("review")
    if not isinstance(block, dict):
        block = src.get("review") if isinstance(src.get("review"), dict) else None
    if not block:
        return {"review_status": "unreviewed", "agronomically_approved": False, "review": None}
    reviewer = block.get("reviewer_id")
    verdict = block.get("verdict")
    # معرّفاتُ الأدلّة **قائمةٌ** من نصوص غير فارغة بعد التشذيب — `" "` ليس دليلاً، ونصٌّ
    # مفرد (`"claim-1"`) ليس قائمةً تُقطَّع حروفاً (Copilot على #1001).
    raw_ids = block.get("evidence_ids")
    if not isinstance(raw_ids, (list, tuple, set, frozenset)):
        raw_ids = []
    evidence = [e.strip() for e in raw_ids if isinstance(e, str) and e.strip()]
    # هويّةُ المراجِع نصٌّ غير فارغ فقط — رقمٌ أو قيمةٌ صادقة أخرى ليست مراجِعاً (Copilot على #1001).
    reviewer = reviewer.strip() or None if isinstance(reviewer, str) else None
    if verdict == "rejected" and reviewer:
        status = "rejected"
    elif verdict == "approved" and reviewer and evidence:
        status = "approved"
    else:
        status = "unreviewed"
    return {
        "review_status": status,
        "agronomically_approved": status == "approved",
        "review": {
            "reviewer_id": reviewer,
            "verdict": verdict if verdict in _REVIEW_VERDICTS else None,
            "evidence_ids": evidence,
            "reviewed_at": block.get("reviewed_at"),
        },
    }


def summarize_learning_sources(rows: list[dict]) -> dict:
    """يُلخِّص نَسَب مصادر تحديثات التعلّم: أعداد حسب النوع والحالة + نسبة المُتتبَّع.

    ``rows`` صفوف تحمل ``source_type``/``traceability_status`` (كما تُخزَّن). صدق: الصفّ بلا
    حالة يُعَدّ ``unverified`` (سجلّ قديم قبل الجسر) لا يُهمَل.
    """
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_review: dict[str, int] = {}
    for r in rows:
        st = r.get("source_type") or "unknown"
        stt = r.get("traceability_status") or "unverified"
        rv = r.get("review_status") or "unreviewed"
        by_type[st] = by_type.get(st, 0) + 1
        by_status[stt] = by_status.get(stt, 0) + 1
        by_review[rv] = by_review.get(rv, 0) + 1
    total = len(rows)
    traceable = by_status.get("traceable", 0)
    return {
        "total": total,
        "traceable": traceable,
        "untraceable": total - traceable,
        "by_source_type": by_type,
        "by_traceability_status": by_status,
        # U07: المُتتبَّع ≠ المُعتمَد — يُعرَضان معاً.
        "by_review_status": by_review,
        "agronomically_approved": by_review.get("approved", 0),
        "traceable_ratio": round(traceable / total, 3) if total else None,
    }
