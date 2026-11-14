"""أزمنة رصد الإشارات بصيغتها القانونيّة (قرار المالك 2026-11-14: النسب الزمنيّ يُحفَظ).

مصدر واحد تستعمله الحالة القانونيّة (services/sahool-platform/core/agronomic_state_engine.py)
ومغلّفها في المرحلة 9 (shared/field_runtime_cohesion.py)، فلا يُبصَم زمن غير مُطبَّع.
نقيّ: بلا قاعدة ولا شبكة ولا ساعة.
"""

from __future__ import annotations

from datetime import UTC, datetime


def canonical_observed_at(value: object) -> str:
    """زمن رصد إشارة بصيغته القانونيّة: لحظة مُدرَكة المنطقة، مُطبَّعة إلى UTC (ISO 8601).

    كـ``AwareDatetime`` في AC-1 (decision-service agronomic_context/contracts.py): طابع
    بلا منطقة زمنيّة (ومنه التاريخ المجرّد ``2026-06-16``) أو غير قابل للتحليل ⇒
    ``ValueError``. لا افتراض UTC هنا: مقارنة naive بمُدرَك تُعيد ترتيب الأحداث بصمت.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as e:
            raise ValueError(f"observed_at غير قابل للتحليل: {value!r}") from e
    else:
        raise ValueError(f"observed_at يجب أن يكون نصّ ISO 8601 أو datetime: {value!r}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"observed_at بلا منطقة زمنيّة مرفوض: {value!r}")
    return dt.astimezone(UTC).isoformat()


def canonical_observations(value: object) -> tuple[tuple[str, str], ...]:
    """أزمنة رصد الإشارات بشكلها المحفوظ: أزواج (source, observed_at UTC) مرتّبة زمنيّاً.

    تقبل أزواجاً أو قواميس ``{"source", "observed_at"}`` (شكل to_dict). كلّ زمن يمرّ
    بـ``canonical_observed_at``، فلا يدخل الحالة طابع naive. الترتيب باللحظة ثمّ المصدر،
    فلا يتغيّر بترتيب وصول الإشارات.
    """
    pairs: list[tuple[str, str]] = []
    for item in value or ():
        if isinstance(item, dict):
            source, observed = item.get("source"), item.get("observed_at")
        else:
            source, observed = item
        if not isinstance(source, str) or not source:
            raise ValueError(f"signal_observations: مصدر غير صالح {source!r}")
        pairs.append((source, canonical_observed_at(observed)))
    return tuple(sorted(pairs, key=lambda p: (datetime.fromisoformat(p[1]), p[0])))
