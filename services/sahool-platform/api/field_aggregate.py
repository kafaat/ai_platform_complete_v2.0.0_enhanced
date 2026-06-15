"""api/field_aggregate.py — حدّ كتابة موحّد للحقل (Field Aggregate Root، P2).

المرحلة ٣ من خارطة ما بعد التشغيل: مصدر حقيقة واحد لكتابة الحقل وما يتفرّع عنه
(موسم/نشاط)، فتمرّ التغييرات عبر مسار موحّد:

    Command → FieldAggregate (تحقّق الـinvariants) → (تغيير حالة + أحداث) ذرّيّاً

هذه **الشريحة الأولى التدريجيّة غير الكاسرة**:
  • النواة النقيّة `FieldAggregate` (بلا I/O) — تأخذ لقطة حالة، تُرجِع الأحداث
    المقصودة أو ترفع `FieldInvariantError`. قابلة للاختبار offline بالكامل.
  • معالِجات أوامر تُسجَّل على `CommandDispatcher` القائم (`command_store.py`)،
    مُحقَّنة بمنافذ (تحميل حالة/حفظ/إصدار) فتُختبَر بمتجر ومنافذ وهميّة.

⚠ هذا التعريف **مطابِق لسلوك endpoints الإنتاج الحيّة** (مصدر الحقيقة:
`api/routers/fields.py` + المساعِدات في `api/main.py`) — فُصِّل ليكون مواصفةً
أمينةً لها تمهيداً لتوصيله لاحقاً دون تراجع سلوكيّ. توجيه endpoint حيّ فعليّ عبر
هذا المسار = الشريحة التالية (يحتاج اختبار تكامل على قاعدة حيّة — موثَّق في
POST_DEPLOYMENT_ROADMAP المرحلة ٣، خطوة ٣). حتى ذلك يبقى **غير موصول** (لا
يستعمله أيّ endpoint حيّ)، فهذا الملفّ لا يغيّر أيّ سلوك تشغيليّ.

⚠ الـinvariants (مطابِقة لما تفرضه الـendpoints فعليّاً، مكان واحد لا تكرار):
  • إنشاء حقل موجود → 409: يطابق `_persist_field` (تكرار الاسم ⇒ 409
    `duplicate_field_name`). [main.py ~L1093]
  • تحديث/موسم/نشاط على حقل غير موجود → 404: يطابق `_assert_field_in_tenant`
    (و`update_field` يؤكّد الوجود قبل الكتابة). [main.py ~L1498؛ fields.py ~L338]
  • بدء موسم وهناك نشط = **استبدال (supersede) لا رفض**: مطابِق لثابت v44 في
    `create_season` — يُغلق الموسم النشط آليّاً (SEASON_CLOSED بسبب
    `superseded_by_new_season`) ثمّ يُنشئ الجديد (SEASON_CREATED) ضمن معاملة
    واحدة. [fields.py ~L462–533]
  • النواة **نقيّة حتميّة**: لا تكتب القاعدة ولا تُصدِر — تصف الأثر فقط.
  • الأحداث من `EventType` القائم (لا قيم سحريّة)؛ خريطة أحداث النشاط مطابِقة لما
    يُصدِره `create_activity` فعليّاً عبر `_activity_event_type`. [fields.py ~L1085]
  • لا يستبدل المسارات الحاليّة دفعةً واحدة — يُمهِّد لتوجيهها تدريجيّاً.

  ملاحظة حدّ نقاء (honesty): معرّف الموسم الجديد (`season_id`) يُولّده الـendpoint
  (I/O، `ssn_…uuid`) لا النواة. نمرّره عبر `data["season_id"]` كي يتمكّن الأثر من
  الإشارة إليه في `superseded_by`؛ وإن غاب، نُصدِر SEASON_CLOSED **دون** المفتاح
  `superseded_by` ويملؤه منفذ `apply_change` بعد توليد المعرّف (نفس المعاملة).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import Enum
from typing import Any

from api.event_bus import EventType


class FieldCommandType(str, Enum):
    """أنواع أوامر الحقل (أمريّة) — مميَّزة عن أحداثه (الماضية في EventType)."""

    CREATE_FIELD = "field.create"
    UPDATE_FIELD = "field.update"
    START_SEASON = "field.season.start"
    RECORD_ACTIVITY = "field.activity.record"


class FieldInvariantError(Exception):
    """انتهاك invariant للحقل — يحمل رسالة عربيّة ورمز HTTP لترجمته في الـendpoint."""

    def __init__(self, message_ar: str, http_status: int):
        super().__init__(message_ar)
        self.message_ar = message_ar
        self.http_status = http_status


@dataclass
class FieldState:
    """لقطة حالة الحقل المحمّلة من القاعدة — مدخل نقيّ للـaggregate (لا I/O داخله)."""

    field_id: str
    exists: bool
    has_active_season: bool = False
    active_season_id: str | None = None
    lifecycle_state: str | None = None


@dataclass
class FieldEffect:
    """أثر العمليّة المقصود: الأحداث الواجب إصدارها (type, payload) — لا تغييرٌ مُطبَّق."""

    events: list[tuple[str, dict]] = dc_field(default_factory=list)


def _payload(field_id: str, data: dict) -> dict:
    """payload الحدث: field_id + بقيّة الحقول (دون تكرار field_id)."""
    return {"field_id": field_id, **{k: v for k, v in data.items() if k != "field_id"}}


# خريطة (نوع النشاط، أُنجِز؟) → حدث عمليّة محدَّد (operation.*). مصدر واحد لدلالة
# أحداث النشاط — يستعمله الـaggregate و(تفويضاً) endpoint النشاط في main.
_ACTIVITY_OP_EVENT = {
    ("planting", True): EventType.PLANTING_COMPLETED,
    ("planting", False): EventType.PLANTING_STARTED,
    ("irrigation", True): EventType.IRRIGATION_COMPLETED,
    ("irrigation", False): EventType.IRRIGATION_STARTED,
    ("harvest", True): EventType.HARVEST_COMPLETED,
    ("harvest", False): EventType.HARVEST_STARTED,
    ("fertilization", True): EventType.FERTILIZER_APPLIED,
    ("spraying", True): EventType.PESTICIDE_APPLIED,
}


def activity_event_for(activity_type: str, status: str) -> EventType:
    """يربط نوع النشاط + حالته (done/planned) بحدث عمليّة محدَّد، وإلّا ACTIVITY_RECORDED.

    مصدر واحد للدلالة (لا تكرار): الـaggregate يستعمله مباشرةً، و`main._activity_event_type`
    يفوّض إليه — فيُصدِر المساران الحدثَ نفسه.
    """
    return _ACTIVITY_OP_EVENT.get((activity_type, status == "done"), EventType.ACTIVITY_RECORDED)


class FieldAggregate:
    """حدّ الحقل: يتحقّق من الـinvariants ويصف الأثر (أحداث) — نقيّ، لا I/O."""

    def __init__(self, state: FieldState):
        self.state = state

    def create(self, data: dict) -> FieldEffect:
        if self.state.exists:
            raise FieldInvariantError("الحقل موجود مسبقاً — لا إنشاء مكرّر", 409)
        return FieldEffect([(EventType.FIELD_CREATED.value, _payload(self.state.field_id, data))])

    def update(self, data: dict) -> FieldEffect:
        self._require_exists()
        return FieldEffect([(EventType.FIELD_UPDATED.value, _payload(self.state.field_id, data))])

    def start_season(self, data: dict) -> FieldEffect:
        """بدء موسم بدلالة **الاستبدال (supersede)** المطابِقة لثابت v44 في
        `create_season`: إن وُجد موسم نشط، يُغلق آليّاً (SEASON_CLOSED) قبل إنشاء
        الجديد (SEASON_CREATED) — لا رفض 409. حقل غير موجود → 404 (`_require_exists`،
        مطابِق لـ`_assert_field_in_tenant`).

        ترتيب الأحداث (مطابِق لترتيب الـendpoint): SEASON_CLOSED ثمّ SEASON_CREATED.
        payload الإغلاق: {field_id, reason:"superseded_by_new_season", superseded_by}.
        معرّف الموسم الجديد I/O (يولّده الـendpoint) — يُمرَّر عبر `data["season_id"]`؛
        وإن غاب يُحذف `superseded_by` ويملؤه `apply_change` بعد التوليد (نفس المعاملة).
        """
        self._require_exists()
        events: list[tuple[str, dict]] = []
        if self.state.has_active_season:
            close_payload = {
                "field_id": self.state.field_id,
                "reason": "superseded_by_new_season",
            }
            new_season_id = data.get("season_id")
            if new_season_id is not None:
                close_payload["superseded_by"] = new_season_id
            events.append((EventType.SEASON_CLOSED.value, close_payload))
        events.append((EventType.SEASON_CREATED.value, _payload(self.state.field_id, data)))
        return FieldEffect(events)

    def record_activity(self, data: dict) -> FieldEffect:
        self._require_exists()
        # الحدث محدَّد بنوع النشاط/حالته (operation.*) — أدقّ من ACTIVITY_RECORDED العامّ.
        event = activity_event_for(data.get("activity_type", ""), data.get("status", ""))
        return FieldEffect([(event.value, _payload(self.state.field_id, data))])

    def _require_exists(self) -> None:
        if not self.state.exists:
            raise FieldInvariantError("الحقل غير موجود ضمن هذا المستأجِر", 404)


# منافذ مُحقَنة (تجعل المعالِجات قابلة للاختبار بلا قاعدة):
StateLoader = Callable[[str], Awaitable[FieldState]]  # field_id → لقطة الحالة
ChangeApplier = Callable[[Any, FieldState], Awaitable[None]]  # (command, state) → حفظ التغيير
EventEmitter = Callable[[str, str, dict], Awaitable[None]]  # (event_type, field_id, payload)

_OP_BY_COMMAND = {
    FieldCommandType.CREATE_FIELD.value: "create",
    FieldCommandType.UPDATE_FIELD.value: "update",
    FieldCommandType.START_SEASON.value: "start_season",
    FieldCommandType.RECORD_ACTIVITY.value: "record_activity",
}


def build_field_handlers(
    *,
    load_state: StateLoader,
    apply_change: ChangeApplier,
    emit_event: EventEmitter,
) -> dict[str, Callable[[Any], Awaitable[dict]]]:
    """يبني معالِجات أوامر الحقل فوق منافذ مُحقَنة (للتسجيل على CommandDispatcher).

    كلّ معالِج: حمّل الحالة → FieldAggregate (تحقّق invariant) → طبّق التغيير + أصدِر
    الأحداث. انتهاك invariant يرفع FieldInvariantError (يلتقطه الـdispatcher → FAILED؛
    والـendpoint لاحقاً يترجمه لرمز HTTP). الذرّيّة مسؤوليّة apply_change (معاملة واحدة).
    """

    async def _handle(command: Any) -> dict:
        field_id = (command.payload or {}).get("field_id")
        if not field_id:
            raise FieldInvariantError("payload يفتقد field_id", 422)
        state = await load_state(field_id)
        agg = FieldAggregate(state)
        effect: FieldEffect = getattr(agg, _OP_BY_COMMAND[command.command_type])(command.payload)
        await apply_change(command, state)
        for event_type, payload in effect.events:
            await emit_event(event_type, field_id, payload)
        return {
            "field_id": field_id,
            "command_type": command.command_type,
            "events_emitted": [et for et, _ in effect.events],
        }

    return {ct.value: _handle for ct in FieldCommandType}


def register_field_handlers(
    dispatcher: Any,
    *,
    load_state: StateLoader,
    apply_change: ChangeApplier,
    emit_event: EventEmitter,
) -> list[str]:
    """يسجّل معالِجات الحقل على CommandDispatcher القائم. يُرجِع الأنواع المُسجَّلة."""
    handlers = build_field_handlers(
        load_state=load_state, apply_change=apply_change, emit_event=emit_event
    )
    for command_type, handler in handlers.items():
        dispatcher.register(command_type, handler)
    return sorted(handlers)
