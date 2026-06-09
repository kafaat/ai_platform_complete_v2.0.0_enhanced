"""
core.connectors.base
====================
الأساس المشترك لكل الموصّلات الخارجية (Copernicus, Open-Meteo...).

أفضل الممارسات المطبّقة:
  • واجهة موحّدة: كل موصّل يُرجع ConnectorResult (بيانات + مصدر + خطأ + حالة).
  • لا مفاتيح مكشوفة: المفاتيح من متغيّرات البيئة، لا في الكود.
  • Fallback: عند فشل المصدر، حالة واضحة لا انهيار.
  • Provenance: كل قيمة تحمل مصدرها ونسبة خطئها (دستور المعلومة).
  • Cache: تجنّب الطلبات المكرّرة (احترام حدود الـ API ووفّر الموارد).

كل موصّل يرث BaseConnector ويطبّق fetch(). الاتصال الفعلي بالشبكة
يحدث في بيئة السيرفر المحلي (GPU 50/90)؛ هنا الواجهة والمنطق.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# عتبة السحب الموحّدة (C6): فوقها → الرادar (S1) بدل البصري (S2).
# ثابت مشترك يمنع تكرار القيمة السحرية عبر الموصّلات و pipeline (DRY).
CLOUD_THRESHOLD_PCT: float = 20.0


class FetchStatus(str, Enum):
    OK = "ok"
    FALLBACK = "fallback"        # المصدر فشل، استُخدم بديل
    UNAVAILABLE = "unavailable"  # لا مصدر ولا بديل
    CACHED = "cached"            # من الذاكرة المؤقتة


@dataclass
class ConnectorResult:
    """نتيجة موحّدة من أي موصّل — تحمل نسبها (provenance)."""
    source: str                  # "open-meteo", "copernicus-s2"...
    status: FetchStatus
    data: dict[str, Any] = field(default_factory=dict)
    error_margin: float = -1.0   # نسبة الخطأ المرجعية للمصدر
    fetched_at: str = ""
    note_ar: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.utcnow().isoformat()

    @property
    def usable(self) -> bool:
        return self.status in (FetchStatus.OK, FetchStatus.CACHED, FetchStatus.FALLBACK)


class BaseConnector(ABC):
    """الأساس المشترك. كل موصّل خارجي يرثه."""

    source_name: str = "base"
    requires_key: bool = False
    key_env_var: str = ""

    def __init__(self):
        self._cache: dict[str, ConnectorResult] = {}

    def _get_key(self) -> str | None:
        """المفتاح من البيئة فقط — لا يُكتب في الكود أبداً."""
        if not self.requires_key:
            return None
        key = os.environ.get(self.key_env_var)
        return key

    def is_configured(self) -> bool:
        """هل الموصّل جاهز للاتصال الفعلي؟"""
        if self.requires_key:
            return self._get_key() is not None
        return True

    @abstractmethod
    def fetch(self, **kwargs) -> ConnectorResult:
        """يجلب البيانات. كل موصّل يطبّقها. يجب أن يُرجع ConnectorResult دائماً
        (حتى عند الفشل — بحالة UNAVAILABLE، لا استثناء غير مُعالَج)."""
        ...

    def _cache_key(self, **kwargs) -> str:
        return f"{self.source_name}:" + ":".join(
            f"{k}={v}" for k, v in sorted(kwargs.items())
        )
