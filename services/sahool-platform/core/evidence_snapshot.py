"""core/evidence_snapshot.py — تحضير لقطة رسم أدلّة الحقل للاستمرار — منطق صرف.

يحوّل مخرَج ``analyze`` (ومعه ``evidence_graph``) إلى صفّ لقطة قابل للإدراج: بصمة قرار
ثابتة + مصادر + فجوات + رسم **منقّى من الأسرار**. لا I/O — الإدراج/القراءة في الراوت
(tenant-scoped). **صدق/أمن:** لا توكن/سرّ يُخزَّن؛ لا لقطة بلا رسم أدلّة فعليّ.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# مفاتيح تُعامَل كأسرار وتُحذَف من أيّ مكان في الرسم قبل التخزين (أمن: لا اعتماد يُخزَّن).
_SECRET_KEY_HINTS = (
    "password",
    "token",
    "secret",
    "authorization",
    "api_key",
    "apikey",
    "netrc",
    "credential",
    "bearer",
    "access_key",
)


def _looks_secret(key: Any) -> bool:
    k = str(key).lower()
    return any(hint in k for hint in _SECRET_KEY_HINTS)


def strip_secrets(value: Any) -> Any:
    """يُزيل أيّ مفتاح يشبه سرّاً من بنية JSON متداخلة (قوائم/قواميس) — نسخ لا تعديل مكانيّ."""
    if isinstance(value, dict):
        return {k: strip_secrets(v) for k, v in value.items() if not _looks_secret(k)}
    if isinstance(value, list):
        return [strip_secrets(v) for v in value]
    return value


def recommendation_hash(analyze: dict[str, Any]) -> str:
    """بصمة **ثابتة** لمدخلات القرار (نفس المدخلات ⇒ نفس البصمة) — لكشف تغيّر التوصية.

    تُبنى من مجموعة صغيرة قانونيّة (نوع الإجراء + الحالة الفعليّة + قرائن + مفاتيح الأدلّة
    الحاضرة) مُسلسَلة بترتيب مفاتيح ثابت. لا تعتمد على وقت/معرّفات عابرة (توقيت/correlation).
    """
    analyze = analyze if isinstance(analyze, dict) else {}
    truths = analyze.get("operational_truths")
    truths = truths if isinstance(truths, dict) else {}
    decision = analyze.get("policy_decision")
    decision = decision if isinstance(decision, dict) else {}
    graph = analyze.get("evidence_graph")
    graph = graph if isinstance(graph, dict) else {}
    evidence_keys = sorted(
        n.get("id")
        for n in (graph.get("nodes") or [])
        if isinstance(n, dict) and str(n.get("id", "")).startswith("evidence:")
    )
    canonical = {
        "action_type": decision.get("action_type"),
        "effective_status": truths.get("effective_status"),
        "salinity_class": truths.get("salinity_class"),
        "ndvi_trend": truths.get("ndvi_trend"),
        "evidence_keys": evidence_keys,
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def should_persist(analyze: dict[str, Any]) -> bool:
    """هل تستحقّ هذه النتيجة لقطة؟ — فقط عند وجود رسم أدلّة بدليل حاضر أو توصية (لا فراغ)."""
    if not isinstance(analyze, dict):
        return False
    graph = analyze.get("evidence_graph")
    if not isinstance(graph, dict):
        return False
    summary = graph.get("summary") if isinstance(graph.get("summary"), dict) else {}
    return bool(summary.get("evidence_count")) or bool(summary.get("has_recommendation"))


def build_snapshot_payload(analyze: dict[str, Any]) -> dict[str, Any] | None:
    """يبني حمولة صفّ اللقطة (بلا tenant/field — يضيفهما الراوت من السياق الموثوق).

    ``None`` إن لم تستحقّ الاستمرار (لا رسم أدلّة). الرسم/المصادر/الفجوات **منقّاة من
    الأسرار**. ``confidence_score`` من التحليل؛ ``analysis_id`` = correlation_id.
    """
    if not should_persist(analyze):
        return None
    graph = strip_secrets(analyze.get("evidence_graph") or {})
    sources = sorted(
        {
            n.get("source")
            for n in (graph.get("nodes") or [])
            if isinstance(n, dict) and n.get("source")
        }
    )
    conf = analyze.get("confidence")
    try:
        conf_num = round(float(conf), 3) if conf is not None else None
    except (TypeError, ValueError):
        conf_num = None
    return {
        "analysis_id": analyze.get("correlation_id"),
        "recommendation_hash": recommendation_hash(analyze),
        "confidence_score": conf_num,
        "evidence_graph": graph,
        "evidence_sources": sources,
        "knowledge_gaps": graph.get("knowledge_gaps") or [],
    }
