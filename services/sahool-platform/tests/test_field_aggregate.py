"""اختبارات Field Aggregate Root (offline) — النواة النقيّة + مسار الـdispatcher.

يتحقّق من أنّ النواة **مطابِقة لسلوك endpoints الإنتاج** (مصدر الحقيقة
`api/routers/fields.py`): إنشاء مكرّر→409 (`duplicate_field_name`)، حقل مفقود→404
(`_assert_field_in_tenant`)، وبدء موسم وهناك نشط = **استبدال (supersede) v44** لا
رفض 409 (SEASON_CLOSED مُستبدَل ثمّ SEASON_CREATED)؛ والأحداث الصحيحة؛ ومسار
CommandDispatcher القائم كاملاً (نجاح/فشل/idempotency) بمتجر ومنافذ وهميّة بلا قاعدة.
"""

import pytest
from api.command_store import Command, CommandDispatcher, CommandStatus
from api.event_bus import EventType
from api.field_aggregate import (
    FieldAggregate,
    FieldCommandType,
    FieldInvariantError,
    FieldState,
    activity_event_for,
    register_field_handlers,
)

# ─── النواة النقيّة: الـinvariants + الأحداث ──────────────────────────────


def test_create_on_new_field_emits_field_created():
    eff = FieldAggregate(FieldState("f1", exists=False)).create({"name": "حقل"})
    assert eff.events == [(EventType.FIELD_CREATED.value, {"field_id": "f1", "name": "حقل"})]


def test_create_on_existing_field_conflicts_409():
    with pytest.raises(FieldInvariantError) as e:
        FieldAggregate(FieldState("f1", exists=True)).create({})
    assert e.value.http_status == 409


def test_update_missing_field_is_404():
    with pytest.raises(FieldInvariantError) as e:
        FieldAggregate(FieldState("f1", exists=False)).update({})
    assert e.value.http_status == 404


def test_start_season_without_active_emits_only_season_created():
    # لا موسم نشط ⇒ حدث واحد فقط: SEASON_CREATED (بلا إغلاق سابق).
    eff = FieldAggregate(FieldState("f1", exists=True)).start_season({"season_id": "s1"})
    assert eff.events == [(EventType.SEASON_CREATED.value, {"field_id": "f1", "season_id": "s1"})]


def test_start_season_missing_field_is_404():
    with pytest.raises(FieldInvariantError) as e:
        FieldAggregate(FieldState("f1", exists=False)).start_season({"season_id": "s1"})
    assert e.value.http_status == 404


def test_start_season_with_active_supersedes_not_409():
    # ثابت v44 (مطابِق لـcreate_season): موسم نشط موجود ⇒ استبدال لا رفض —
    # SEASON_CLOSED(superseded) ثمّ SEASON_CREATED بنفس الترتيب، بلا رفع 409.
    state = FieldState("f1", exists=True, has_active_season=True, active_season_id="s0")
    eff = FieldAggregate(state).start_season({"season_id": "s1"})
    assert [et for et, _ in eff.events] == [
        EventType.SEASON_CLOSED.value,
        EventType.SEASON_CREATED.value,
    ]
    # payload الإغلاق يطابق ما يُصدِره الـendpoint حرفيّاً.
    assert eff.events[0][1] == {
        "field_id": "f1",
        "reason": "superseded_by_new_season",
        "superseded_by": "s1",
    }


def test_start_season_with_active_omits_superseded_by_when_season_id_absent():
    # honesty: معرّف الموسم الجديد I/O؛ إن غاب يُحذف superseded_by (يملؤه apply_change).
    state = FieldState("f1", exists=True, has_active_season=True, active_season_id="s0")
    eff = FieldAggregate(state).start_season({"crops": ["wheat"]})
    assert [et for et, _ in eff.events] == [
        EventType.SEASON_CLOSED.value,
        EventType.SEASON_CREATED.value,
    ]
    assert "superseded_by" not in eff.events[0][1]
    assert eff.events[0][1] == {"field_id": "f1", "reason": "superseded_by_new_season"}


def test_record_activity_requires_existing_field():
    with pytest.raises(FieldInvariantError) as e:
        FieldAggregate(FieldState("f1", exists=False)).record_activity({})
    assert e.value.http_status == 404
    # بلا نوع نشاط معروف → الحدث العامّ ACTIVITY_RECORDED.
    eff = FieldAggregate(FieldState("f1", exists=True)).record_activity({"activity_id": "a1"})
    assert eff.events[0][0] == EventType.ACTIVITY_RECORDED.value


def test_record_activity_emits_operation_specific_event():
    # نوع/حالة معروفان → حدث عمليّة محدَّد (أدقّ من العامّ).
    eff = FieldAggregate(FieldState("f1", exists=True)).record_activity(
        {"activity_id": "a1", "activity_type": "harvest", "status": "done"}
    )
    assert eff.events[0][0] == EventType.HARVEST_COMPLETED.value


def test_activity_event_for_single_source_mapping():
    assert activity_event_for("planting", "done") == EventType.PLANTING_COMPLETED
    assert activity_event_for("planting", "planned") == EventType.PLANTING_STARTED
    assert activity_event_for("fertilization", "done") == EventType.FERTILIZER_APPLIED
    # تسميد غير مُنجَز / نوع مجهول → العامّ.
    assert activity_event_for("fertilization", "planned") == EventType.ACTIVITY_RECORDED
    assert activity_event_for("scouting", "done") == EventType.ACTIVITY_RECORDED


def test_main_activity_event_type_delegates_identically():
    # main._activity_event_type يفوّض ويُرجِع اسم العضو نفسه (توافق خلفيّ).
    from api.field_aggregate import activity_event_for as _src
    from api.main import _activity_event_type

    for atype in ("planting", "irrigation", "harvest", "fertilization", "spraying", "scouting"):
        for status in ("done", "planned"):
            assert _activity_event_type(atype, status) == _src(atype, status).name


# ─── مسار CommandDispatcher القائم (متجر + منافذ وهميّة) ──────────────────


class _FakeStore:
    """متجر أوامر في الذاكرة يطابق عقد CommandStore الذي يستعمله CommandDispatcher."""

    def __init__(self):
        self.commands: dict[str, Command] = {}

    async def get(self, command_id):
        return self.commands.get(command_id)

    async def insert(self, cmd: Command) -> bool:
        if cmd.command_id in self.commands:
            return False  # ON CONFLICT DO NOTHING
        cmd.status = CommandStatus.PENDING
        self.commands[cmd.command_id] = cmd
        return True

    async def mark_processing(self, command_id):
        self.commands[command_id].status = CommandStatus.PROCESSING

    async def mark_succeeded(self, command_id, result):
        c = self.commands[command_id]
        c.status, c.result = CommandStatus.SUCCEEDED, result

    async def mark_failed(self, command_id, error):
        c = self.commands[command_id]
        c.status, c.error = CommandStatus.FAILED, error
        c.retry_count += 1


def _wire(initial_states: dict[str, FieldState]):
    """يبني dispatcher + منافذ وهميّة، ويُرجِع (dispatcher, emitted, applied)."""
    emitted: list[tuple[str, str, dict]] = []
    applied: list[str] = []

    async def load_state(field_id):
        return initial_states.get(field_id, FieldState(field_id, exists=False))

    async def apply_change(command, state):
        applied.append(command.command_id)

    async def emit_event(event_type, field_id, payload):
        emitted.append((event_type, field_id, payload))

    dispatcher = CommandDispatcher(_FakeStore())
    register_field_handlers(
        dispatcher, load_state=load_state, apply_change=apply_change, emit_event=emit_event
    )
    return dispatcher, emitted, applied


def _cmd(command_type: str, field_id: str, **data):
    return Command.new(
        command_type=command_type,
        actor_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        payload={"field_id": field_id, **data},
    )


async def test_dispatch_create_succeeds_and_emits():
    dispatcher, emitted, applied = _wire({})
    res = await dispatcher.dispatch(_cmd(FieldCommandType.CREATE_FIELD.value, "f1", name="حقل"))
    assert res.status == CommandStatus.SUCCEEDED
    assert emitted == [(EventType.FIELD_CREATED.value, "f1", {"field_id": "f1", "name": "حقل"})]
    assert applied  # طُبِّق التغيير


async def test_dispatch_invariant_violation_marks_failed():
    dispatcher, emitted, _ = _wire({"f1": FieldState("f1", exists=True)})
    res = await dispatcher.dispatch(_cmd(FieldCommandType.CREATE_FIELD.value, "f1"))
    assert res.status == CommandStatus.FAILED
    assert "FieldInvariantError" in (res.error or "")
    assert emitted == []  # لا إصدار عند فشل الـinvariant


async def test_dispatch_is_idempotent_on_duplicate_command_id():
    dispatcher, emitted, _ = _wire({})
    cmd = _cmd(FieldCommandType.CREATE_FIELD.value, "f1")
    first = await dispatcher.dispatch(cmd)
    second = await dispatcher.dispatch(cmd)  # نفس command_id
    assert first.status == CommandStatus.SUCCEEDED
    assert second.was_duplicate is True
    assert len(emitted) == 1  # لم يُصدَر الحدث مرّتين


async def test_register_field_handlers_covers_all_command_types():
    dispatcher, _, _ = _wire({})
    assert set(dispatcher.registered_types()) == {ct.value for ct in FieldCommandType}
