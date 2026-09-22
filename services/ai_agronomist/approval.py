"""بوّابة الموافقة البشريّة + إدامة تدقيق الأدوات (V55 — المرحلة ٤).

الأفعال عالية الأثر لا تُنفَّذ بقرار النموذج وحده: المنفّذ (المرحلة ٢) يُرجِع
``pending_approval``؛ هنا نُنشئ **طلب موافقة** يُدِيمه إنسان يقبله أو يرفضه، وكلّ ذلك
(وكلّ استدعاء أداة) يُدوَّن في سجلّ ``agent_tool_audit`` الدائم (v126، append-only).

دوالّ صرفة + حاقن إدامة (لا قاعدة في الاختبار). ``timestamp`` يُمرَّر من الخارج
(حتميّ). الوسائط تُنقَّح دائماً قبل الحفظ (لا أسرار في التدقيق).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("ai_agronomist.approval")

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_DENIED)

_SECRET_HINTS = ("token", "secret", "api_key", "apikey", "password", "authorization")
# حاجزُ عمقٍ للتنقيح المتداخل: بنيةٌ عميقةٌ أو دوّارةٌ لا يجوز أن تُسقِطه صامتاً.
_MAX_REDACT_DEPTH = 6
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# حاقن إدامة سجلّ التدقيق (يكتب صفّاً في agent_tool_audit). بلا حاقن ⇒ لا كتابة دائمة.
AuditSaver = Callable[["dict[str, Any]"], None]


def _redact_value(value: Any, *, depth: int = 0) -> Any:
    """تنقيحٌ **متداخل** — القواميسُ والقوائمُ تُنقَّح إلى العمق لا السطحَ وحدَه."""
    if depth > _MAX_REDACT_DEPTH:  # حاجزُ عمقٍ: بنيةٌ دوّارةٌ أو عميقةٌ لا تُسقِط التنقيح
        return "[redacted-depth]"
    if isinstance(value, dict):
        return _redact(value, depth=depth + 1)
    if isinstance(value, (list, tuple)):
        return [_redact_value(v, depth=depth + 1) for v in value]
    if isinstance(value, str):
        return _UUID_RE.sub("[redacted-id]", _EMAIL_RE.sub("[redacted-email]", value))
    return value


def _redact(params: dict[str, Any] | None, *, depth: int = 0) -> dict[str, Any]:
    """نسخةُ **العرض** المُنقَّحة.

    **العطلُ الذي وُجِد هذا لأجله (D04-أ):** كان التنقيحُ يمرّ على المستوى الأوّل
    فقط. فـ``params.nested.api_key`` يبقى في سجلّ التدقيق بنصّه، وكذلك ما يقع تحت
    قائمةٍ أو قاموسٍ متداخل. وسرٌّ في الطبقة الثانية مكشوفٌ كسرٍّ في الأولى سواءً.
    """
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if any(h in str(key).strip().lower() for h in _SECRET_HINTS):
            out[key] = "[redacted]"
        else:
            out[key] = _redact_value(value, depth=depth)
    return out


def _stable_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def input_hash(params: dict[str, Any] | None) -> str:
    """بصمةٌ قانونيّةٌ على المدخل **الأصليّ** المعياريّ — لا على تمثيله المُنقَّح.

    **العطلُ الذي وُجِد هذا لأجله (D04-ب):** كانت البصمةُ تُؤخَذ بعد التنقيح، فـUUIDان
    **مختلفان** يصيران ``[redacted-id]`` كلاهما ⇒ **بصمةٌ واحدة لمدخلين مختلفين**.
    وهذا ليس تصادماً في SHA-256 بل **فقدانَ دلالةٍ قبل التجزئة**: البصمةُ تصلح
    لتجميع نصوصٍ مُنقَّحة، ولا تُثبِت أنّ الموافقةَ مربوطةٌ بالكيان الأصليّ نفسِه —
    وهي تُستعمَل هنا لذلك بالضبط.

    **والسرُّ لا يُسرَّب رغم البصم على الأصل:** يُستعمَل HMAC-SHA256 بمفتاحٍ خادميّ
    (``SAHOOL_AGENT_TOKEN``) حين يتوفّر، فلا يُخمَّن معرّفٌ حسّاسٌ من البصمة
    بقاموسٍ — والبصمةُ لا تُعيد المدخلَ في الحالتين.

    **حدُّ صدقٍ مُعلَن:** بلا مفتاحٍ مضبوطٍ تعود إلى SHA-256 عارية. فالمعرّفُ منخفضُ
    الإنتروبيا قد يُخمَّن حينئذٍ — والأثرُ مقايضةٌ واعية: بصمةٌ **صادقةٌ** قابلةٌ
    للتخمين أفضلُ من بصمةٍ **كاذبةٍ** تساوي بين مدخلين.
    """
    payload = _stable_json(params or {})
    key = os.getenv("SAHOOL_AGENT_TOKEN", "")
    if key:
        return hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_result(result: Any, *, max_len: int = 240) -> str:
    """ملخّص قصير وآمن لنتيجة الأداة لأجل التدقيق/الشفافية، لا يحفظ كامل الحمولة."""
    if result is None:
        return "none"
    if isinstance(result, dict):
        keys = sorted(str(k) for k in result.keys())[:8]
        summary = {"type": "dict", "keys": keys}
        for preferred in ("field_id", "index", "layer", "ui_action", "ready", "state", "total"):
            if preferred in result:
                summary[preferred] = result.get(preferred)
        text = _stable_json(summary)
    elif isinstance(result, list):
        text = _stable_json({"type": "list", "count": len(result)})
    else:
        text = str(result)
    return text[:max_len]


def build_approval_request(
    *,
    request_id: str,
    tool_name: str,
    params: dict[str, Any] | None,
    tenant_id: str,
    actor: str,
    risk: str,
    capability: str | None,
    requested_at: str,
) -> dict[str, Any]:
    """يُنشئ طلب موافقة معلَّقاً لأداة مؤجَّلة (وسائطه مُنقَّحة)."""
    return {
        "id": str(request_id),
        "tool": tool_name,
        "params": _redact(params),
        "input_hash": input_hash(params),
        "result_summary": "pending_human_approval",
        "tenant_id": str(tenant_id),
        "actor": str(actor),
        "risk": risk,
        "capability": capability,
        "status": STATUS_PENDING,
        "requested_at": requested_at,
        "decided_by": None,
        "decided_at": None,
        "deny_reason": None,
    }


def approve(request: dict[str, Any], *, approver: str, decided_at: str) -> dict[str, Any]:
    """يوافق على طلب معلَّق (لا يوافق على غير المعلَّق — حماية من الموافقة المزدوجة)."""
    if request.get("status") != STATUS_PENDING:
        raise ValueError(f"لا يمكن الموافقة على طلب حالته {request.get('status')}")
    updated = dict(request)
    updated.update(
        {"status": STATUS_APPROVED, "decided_by": str(approver), "decided_at": decided_at}
    )
    return updated


def deny(
    request: dict[str, Any], *, approver: str, decided_at: str, reason: str = ""
) -> dict[str, Any]:
    if request.get("status") != STATUS_PENDING:
        raise ValueError(f"لا يمكن رفض طلب حالته {request.get('status')}")
    updated = dict(request)
    updated.update(
        {
            "status": STATUS_DENIED,
            "decided_by": str(approver),
            "decided_at": decided_at,
            "deny_reason": reason,
        }
    )
    return updated


def emit_audit(record: dict[str, Any], saver: AuditSaver | None) -> bool:
    """يُدِيم سجلّ تدقيق (best-effort). يُنقّح الوسائط قبل الحفظ. فشل الحفظ لا يرفع
    استثناءً للمستدعي (التدقيق لا يجب أن يُعطّل المسار). يُرجِع نجاح الإدامة."""
    safe = dict(record)
    raw_params = record.get("params") if isinstance(record.get("params"), dict) else {}
    safe["params"] = _redact(raw_params)
    safe.setdefault("input_hash", input_hash(raw_params))
    safe.setdefault("result_summary", summarize_result(record.get("result")))
    # D04-ج — **النتيجةُ تُنقَّح أيضاً.** كانت `result` تُحفَظ خاماً، فبقي
    # `result.authorization` في السجلّ رغم أنّ `params` نُقِّحت. والسرُّ في النتيجة
    # مكشوفٌ كالسرّ في المدخل سواءً — والتنقيحُ يقع **قبل كلّ مخزن** لا في مُعِينٍ
    # قد يتجاوزه مُستدعٍ آخر.
    if "result" in safe:
        safe["result"] = _redact_value(safe["result"])
    if saver is None:
        return False
    try:
        saver(safe)
        return True
    except Exception as exc:  # التدقيق best-effort — لا يُعطّل استدعاء الأداة.
        logger.warning("فشل إدامة تدقيق الأداة %s: %s", record.get("tool"), exc)
        return False
