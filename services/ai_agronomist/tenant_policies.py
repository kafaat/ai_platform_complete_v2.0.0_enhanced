"""مخزن سياسة حوكمة الذكاء للمستأجِر (V52 — Durable AI Governance).

قبل V52 كان المخزن في الذاكرة فقط (يُفقَد عند إعادة التشغيل، بلا تدقيق) — رصده تدقيق
V51 كخطر P0. الآن المخزن **قابل للإدامة**: يُحقَن ``loader``/``saver`` يقرآن/يكتبان جدول
``tenant_ai_policies`` (انظر ``migrations/v124_tenant_ai_policies.sql``). بلا حاقن يبقى
المخزن محلّيّ-العمليّة (سلوك ما قبل V52) — فتعمل اختبارات الوحدة والتشغيل المحلّيّ بلا
قاعدة بيانات. الإنتاج يصل حاقناً مدعوماً بالقاعدة فتصير السياسة دائمة وقابلة للتدقيق.

العقد متوافق رجعيّاً: ``get_policy``/``set_policy`` يحتفظان بتواقيعهما السابقة.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("ai_agronomist.tenant_policies")

# مستويات مشاركة البيانات — كم من سياق الحقل يجوز أن يغادر حدّ المستأجِر.
# (مرآة ``shared/ai/provider_contract.DATA_SHARING_LEVELS`` — يفرض التطابقَ حارسُ
#  ``tests_v9/test_tenant_ai_policy_store_v52.py``.)
DATA_SHARING_LOCAL_ONLY = "local_only"
DATA_SHARING_REDACTED_EXTERNAL = "redacted_external"
DATA_SHARING_FULL_EXTERNAL = "full_external"
DATA_SHARING_LEVELS = (
    DATA_SHARING_LOCAL_ONLY,
    DATA_SHARING_REDACTED_EXTERNAL,
    DATA_SHARING_FULL_EXTERNAL,
)

PolicyLoader = Callable[[str], "dict[str, Any] | None"]
PolicySaver = Callable[[str, "dict[str, Any]"], None]


def default_policy() -> dict[str, Any]:
    """افتراضيّ متحفّظ: التوليد مسموح هنا (تحكمه الراية العامّة ``AI_GENERATION_ENABLED``
    المُعطَّلة افتراضيّاً)، لكنّ بيانات الحقل تبقى محلّيّة حتى يختار المستأجِر صراحةً
    مشاركةً خارجيّة."""
    return {
        "ai_generation_allowed": True,
        "allowed_providers": [],  # فارغ ⇒ لا تقييد إضافيّ فوق حلّ المزوّد العامّ.
        "allowed_models": [],  # فارغ ⇒ يُحال إلى كتالوج ``AI_MODELS``.
        "data_sharing_level": DATA_SHARING_LOCAL_ONLY,
        "redaction_profile": "default",
    }


def normalize_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """يدمج السياسة فوق الافتراضيّ ويضبط مستوى مشاركة البيانات على قيمة قانونيّة.

    يوحّد اسم العمود الدائم ``external_data_sharing_level`` (جدول v124) مع المفتاح
    المنطقيّ ``data_sharing_level`` كي يقبل المخزن صفّ القاعدة مباشرةً."""
    merged = dict(default_policy())
    if policy:
        merged.update(policy)
        # توافق اسم العمود في القاعدة ⇄ المفتاح المنطقيّ.
        if "external_data_sharing_level" in policy and "data_sharing_level" not in policy:
            merged["data_sharing_level"] = policy["external_data_sharing_level"]
    level = str(merged.get("data_sharing_level") or DATA_SHARING_LOCAL_ONLY).strip().lower()
    if level not in DATA_SHARING_LEVELS:
        level = DATA_SHARING_LOCAL_ONLY
    merged["data_sharing_level"] = level
    return merged


class TenantPolicyStore:
    """ذاكرة تخزين مؤقّت محلّيّة-العمليّة مع حاقن إدامة اختياريّ.

    متوافق رجعيّاً: بلا ``loader``/``saver`` يسلك كمخزن ما قبل V52 (قاموس داخليّ)."""

    def __init__(
        self,
        loader: PolicyLoader | None = None,
        saver: PolicySaver | None = None,
    ) -> None:
        self._p: dict[Any, dict[str, Any]] = {}
        self._loader = loader
        self._saver = saver

    def set_policy(self, tenant_id, policy):
        """يطبّع السياسة، يخزّنها في الكاش، ويُديمها (best-effort) إن وُجد ``saver``."""
        norm = normalize_policy(policy)
        self._p[tenant_id] = norm
        if self._saver is not None:
            try:
                self._saver(str(tenant_id), norm)
            except Exception as exc:  # الإدامة best-effort؛ الكاش يبقى المرجع الحيّ.
                logger.warning("durable policy save failed for tenant %s: %s", tenant_id, exc)
        return norm

    def get_policy(self, tenant_id):
        """يُرجِع سياسة المستأجِر: الكاش ⇒ الحاقن الدائم ⇒ ``{}`` (سلوك ما قبل V52).

        إبقاء الافتراضيّ ``{}`` يحفظ التوافق الرجعيّ (``tenant_allows_generation({})``
        يسمح حين تكون الراية العامّة مُفعَّلة)."""
        if tenant_id in self._p:
            return self._p[tenant_id]
        if self._loader is not None:
            try:
                loaded = self._loader(str(tenant_id))
            except Exception as exc:  # فشل القراءة الدائمة ⇒ سقوط آمن إلى الافتراضيّ.
                logger.warning("durable policy load failed for tenant %s: %s", tenant_id, exc)
                loaded = None
            if loaded is not None:
                norm = normalize_policy(loaded)
                self._p[tenant_id] = norm
                return norm
        return {}

    def data_sharing_level(self, tenant_id) -> str:
        """مستوى مشاركة البيانات الفعّال للمستأجِر (قانونيّ دائماً)."""
        return normalize_policy(self.get_policy(tenant_id))["data_sharing_level"]
