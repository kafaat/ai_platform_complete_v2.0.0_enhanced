"""مُزوِّدون يقرؤون المُنتَجات القانونيّة الجاهزة ويُغلّفونها بنَسَبها.

**ما يفعله المُزوِّد وما لا يفعله:** يقرأ قيمةً من مُنتَجٍ قانونيّ **مُسلَّمٍ إليه**
ولا يحسبها ولا يجلبها. فلو حسبها لصار مُنتِجاً ثانياً لمفتاحٍ له مُنتِجٌ واحد —
وهو «مصدر الحقيقة الظلّ» بعينه.

**ويفشل مغلقاً في حالتين، وكلتاهما مقيسة في هذا المستودع:**

- **قيمةٌ ليست عدداً منتهياً** ⇒ `None`. و`None` هنا يعني «احجب»، لا «استعمل صفراً».
- **قيمةٌ بلا بصمة مُنتِجها** ⇒ `None`. وهذا هو الصنف الذي وقع فعلاً في M2.6:
  قدرةٌ تُبلِّغ `verified` ونَسَبُها `None` — دليلٌ يعرض ثقبَه بوصفه حقيقةً
  مُتحقَّقة، وهو أسوأ من الحجب لأنّ من يقرأ `verified` لا يعود ينظر في الأدلّة.

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

import math
from typing import Any

from .contracts import KnowledgeRequirement, KnowledgeValue


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _digest_of(product: dict[str, Any], *keys: str) -> str:
    for key in keys:
        candidate = product.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return ""


def mapping_provider(
    product: dict[str, Any],
    *,
    source_of_truth: str,
    producer: str,
    field_by_key: dict[str, str],
    digest_keys: tuple[str, ...] = ("capability_digest", "profile_digest"),
):
    """يبني مُزوِّداً فوق مُنتَجٍ قانونيّ واحد مُسلَّمٍ بوصفه قاموساً.

    `field_by_key` يربط **المفتاح المنطقيّ** في السجلّ بـ**الحقل الفعليّ** في
    المُنتَج. والفصلُ بينهما مقصود: المفتاح المنطقيّ يقول ماذا تعني القيمة،
    والحقل يقول أين تسكن — واسمان فعليّان متطابقان لمُنتِجَين مختلفين لا
    يجعلان المعنى واحداً (وهو ما ظهر في `maximum_safe_depth_mm_event`).
    """

    def provide(req: KnowledgeRequirement) -> KnowledgeValue | None:
        field = field_by_key.get(req.key)
        if field is None:
            return None
        value = _finite(product.get(field))
        if value is None:
            return None
        digest = _digest_of(product, *digest_keys)
        if not digest:
            # قيمةٌ بلا بصمةِ مُنتِجها لا تُسلَّم: النَّسَب شرطٌ لا زينة.
            return None
        return KnowledgeValue(
            value=value,
            source_of_truth=source_of_truth,
            producer=producer,
            producer_version=str(product.get("product_version") or "") or None,
            observed_at=str(product.get("generated_at") or "") or None,
            effective_at=str(product.get("effective_at") or "") or None,
            quality=str(product.get("quality_status") or product.get("status") or "") or None,
            evidence_refs=(digest,),
        )

    return provide


def irrigation_capability_provider(capability_graph: dict[str, Any]):
    """مُزوِّد `irrigation.*` من الرسم البيانيّ للقدرة — مُنتِجُه القانونيّ."""
    return mapping_provider(
        capability_graph,
        source_of_truth="canonical_irrigation_capability_graph",
        producer="sahool-platform/canonical_irrigation_capability_graph",
        field_by_key={"irrigation.maximum_safe_depth_mm_event": "maximum_safe_depth_mm_event"},
        digest_keys=("capability_digest", "irrigation_capability_digest"),
    )


def root_zone_provider(root_zone_profile: dict[str, Any]):
    """مُزوِّد `root_zone.*` من مِلَفّ منطقة الجذر القانونيّ."""
    return mapping_provider(
        root_zone_profile,
        source_of_truth="canonical_root_zone_profile",
        producer="sahool-platform/canonical_root_zone_profile",
        field_by_key={"root_zone.root_zone_refill_cap_mm": "root_zone_refill_cap_mm"},
        digest_keys=("profile_digest",),
    )


def sprinkler_provider(sprinkler_capability: dict[str, Any]):
    """مُزوِّد `sprinkler.*` من قدرة الرشّ/الجريان القانونيّة."""
    return mapping_provider(
        sprinkler_capability,
        source_of_truth="canonical_sprinkler_runoff_capability",
        producer="sahool-platform/canonical_sprinkler_runoff_capability",
        field_by_key={"sprinkler.maximum_safe_depth_mm_event": "maximum_safe_depth_mm_event"},
        digest_keys=("capability_digest",),
    )
