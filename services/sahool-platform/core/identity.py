"""
sahool_core.identity
=====================
Dual-ID Strategy — UUID داخلي + readable خارجي.

الفجوة المسدودة: المراجعة الاستراتيجية أكّدت أن رفضي المطلق لـUUID
خاطئ. الحلّ الأنضج: **استخدام النوعين معاً، لأغراض مختلفة**.

السبب التشغيلي:
  • Internal UUID للسلامة الهندسية:
    - Offline-first sync (لا تضارب عند المزامنة)
    - Event sourcing + audit chains
    - Async ingestion من مصادر متعدّدة
    - Public API exposure (لا يكشف عدد السجلات)
    - Merge safety بين tenants/regions

  • External Readable للتجربة البشرية:
    - دعم تلفوني (يستطيع المزارع قراءة "fld_yem_203")
    - تشخيص في السجلات (rec_irr_2026_05_31 أوضح من UUID)
    - عرض في الواجهة بدون "wall of UUIDs"
    - تتبّع بصري سريع

النمط: كل كيان يحمل الـid، مفهرس بكلاهما، يُعرَض حسب السياق.

المبادئ المحفوظة:
  • التوافق الخلفي: الـTEXT id الحالي يصبح readable_id (لا breaking change)
  • التأجيل ≠ الإغلاق: UUID مُضاف، الترقية الفعلية في PostgreSQL migration
  • Deterministic: مولّد الـreadable يستخدم سياقاً ثابتاً (region+type+date+counter)
  • Reverse-mappable: من أيّ معرّف يصل للآخر بسهولة

التكامل:
  ← canonical_schemas تستخدم IdentityPair الآن
  ← PostgreSQL migration plan يستخدم UUID كـPK، readable كـUNIQUE
  ← API endpoints تقبل أيّ معرّف، تعمل بالـUUID داخلياً
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EntityKind(str, Enum):
    """نوع الكيان — يحدّد بادئة الـreadable id."""

    TENANT = "tnt"
    USER = "usr"
    FARM = "frm"
    FIELD = "fld"
    SEASON = "ssn"
    OBSERVATION = "obs"
    RECOMMENDATION = "rec"
    ACTIVITY = "act"
    CALIBRATION = "cal"


# نمط readable id الصالح:
#   <kind>_<region>?_<type>?_<year>?_<counter>
#   مثال: fld_<region>_203، rec_irr_2026_05_31، cal_<district>_2025_v2
_READABLE_PATTERN = re.compile(
    r"^[a-z]{3}_[a-z0-9_]{1,80}$",
    re.IGNORECASE,
)


@dataclass
class IdentityPair:
    """زوج معرّفات لكيان واحد. يُحفظ كحقول في DB، يُستخدم حسب الحاجة.

    قواعد:
      • uuid: دائم، لا يتغيّر أبداً، يُولَّد عند الإنشاء
      • readable: قابل للتغيير (نادراً) إذا تطلّب العمل (مثل إعادة هيكلة region)
      • الـUUID هو "هويّة الكيان"، readable هو "اسم العرض"
    """

    uuid: str
    readable: str
    kind: EntityKind
    created_at: str = ""

    def __post_init__(self):
        # تحقّق صحّة UUID
        try:
            uuid.UUID(self.uuid)
        except ValueError as e:
            raise ValueError(f"UUID غير صالح: '{self.uuid}'") from e
        # تحقّق نمط readable
        if not _READABLE_PATTERN.match(self.readable):
            raise ValueError(
                f"readable id '{self.readable}' لا يطابق النمط "
                f"(<kind>_<context>، حروف صغيرة وأرقام و_)"
            )
        # تطابق البادئة مع النوع
        prefix = self.readable.split("_")[0]
        if prefix != self.kind.value:
            raise ValueError(f"بادئة '{prefix}' لا تطابق النوع '{self.kind.value}'")


def generate_uuid() -> str:
    """يولّد UUID v4 (random). الاختيار الأنضج لـsync ذي 100+ مستأجر."""
    return str(uuid.uuid4())


def generate_readable(
    kind: EntityKind,
    *,
    context: str | None = None,
    counter: int | None = None,
) -> str:
    """يولّد readable id قابل للقراءة.

    أمثلة:
      generate_readable(EntityKind.FIELD, context='r1_d2', counter=203)
        → 'fld_r1_d2_203'
      generate_readable(EntityKind.RECOMMENDATION, context='irr_2026_05')
        → 'rec_irr_2026_05'

    المبدأ: محتوى dependent على المعنى — لا hash عشوائي.
    لو ضاع counter، يجب أن يكون من السهل تخمين/مراجعة الـid."""
    parts = [kind.value]
    if context:
        # تنظيف: حروف صغيرة، _ بدلاً من الفواصل
        clean = re.sub(r"[^a-z0-9_]", "_", context.lower().strip())
        clean = re.sub(r"_+", "_", clean).strip("_")
        if clean:
            parts.append(clean)
    if counter is not None:
        parts.append(str(counter))
    if len(parts) == 1:
        # context فارغ → نضيف timestamp قصير لتجنّب التضارب
        parts.append(datetime.now().strftime("%y%m%d%H%M%S"))
    return "_".join(parts)


def new_identity(
    kind: EntityKind,
    *,
    context: str | None = None,
    counter: int | None = None,
) -> IdentityPair:
    """يولّد زوجاً جديداً. الاستخدام الموصى به لكل إنشاء جديد."""
    return IdentityPair(
        uuid=generate_uuid(),
        readable=generate_readable(kind, context=context, counter=counter),
        kind=kind,
        created_at=datetime.now().isoformat(),
    )


# ─── Identity Mapping Layer (لتسهيل البحث) ───────────────────────


@dataclass
class IdentityIndex:
    """فهرس داخلي للتحويل بين UUID و readable.

    في production: هذا جدول DB بـindexes على كلا العمودين.
    في النواة الحالية: in-memory للاختبار + التصميم."""

    by_uuid: dict[str, IdentityPair] = field(default_factory=dict)
    by_readable: dict[str, IdentityPair] = field(default_factory=dict)

    def register(self, pair: IdentityPair) -> None:
        """يسجّل زوجاً — يرفض التضارب صراحةً."""
        if pair.uuid in self.by_uuid:
            raise ValueError(
                f"UUID '{pair.uuid}' مُسجَّل بالفعل لـ'{self.by_uuid[pair.uuid].readable}'"
            )
        if pair.readable in self.by_readable:
            raise ValueError(
                f"readable '{pair.readable}' مُسجَّل بالفعل لـUUID "
                f"'{self.by_readable[pair.readable].uuid}'"
            )
        self.by_uuid[pair.uuid] = pair
        self.by_readable[pair.readable] = pair

    def resolve(self, any_id: str) -> IdentityPair | None:
        """يقبل أيّ معرّف (UUID أو readable) ويُرجع الزوج كاملاً.

        هذا الـAPI الموصى به: لا تفترض نوع المعرّف، استخدم resolve()."""
        # حاول UUID أولاً (أسرع للتمييز)
        try:
            uuid.UUID(any_id)
            return self.by_uuid.get(any_id)
        except (ValueError, AttributeError):
            # ليس UUID — تدفّق مقصود: نُكمل لمحاولة أنواع معرّفات أخرى أدناه
            pass  # noqa: S110 (fallthrough مقصود لا silent failure)
        # readable
        return self.by_readable.get(any_id)

    def to_uuid(self, any_id: str) -> str | None:
        """يحوّل أيّ معرّف إلى UUID. None إن لم يوجد."""
        pair = self.resolve(any_id)
        return pair.uuid if pair else None

    def to_readable(self, any_id: str) -> str | None:
        """يحوّل أيّ معرّف إلى readable."""
        pair = self.resolve(any_id)
        return pair.readable if pair else None

    def __len__(self) -> int:
        return len(self.by_uuid)


# ─── Migration Helper: ترقية canonical_schemas القديمة ───────────


def upgrade_legacy_id(legacy_id: str, kind: EntityKind) -> IdentityPair:
    """يُرقّي معرّف قديم (TEXT فقط) إلى IdentityPair.

    يحرس على readable id الموجود (لا breaking change)، يضيف UUID.
    يُستخدم عند migration من النواة الحالية إلى dual-ID."""
    # تحقّق أن legacy_id يطابق نمط readable
    if not _READABLE_PATTERN.match(legacy_id):
        # legacy بصيغة مختلفة → نُولّد readable جديد مع حفظ القديم في context
        clean_legacy = re.sub(r"[^a-z0-9_]", "_", legacy_id.lower())
        return new_identity(kind, context=f"legacy_{clean_legacy}")

    prefix = legacy_id.split("_")[0]
    if prefix == kind.value:
        # legacy_id صالح بالفعل — نحفظه ونضيف UUID
        return IdentityPair(
            uuid=generate_uuid(),
            readable=legacy_id,
            kind=kind,
            created_at=datetime.now().isoformat(),
        )
    else:
        # البادئة لا تطابق — نُولّد جديداً
        return new_identity(kind, context=legacy_id)


def identity_summary(index: IdentityIndex) -> dict:
    """ملخّص الفهرس للتشخيص."""
    by_kind: dict[str, int] = {}
    for pair in index.by_uuid.values():
        by_kind[pair.kind.value] = by_kind.get(pair.kind.value, 0) + 1
    return {
        "total_entities": len(index),
        "by_kind": by_kind,
        "summary_ar": (f"{len(index)} كيان مُسجَّل، موزّعة على {len(by_kind)} نوع"),
    }
