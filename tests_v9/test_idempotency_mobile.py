"""idempotency لنقاط الموبايل (ب-2 من خطّة التحوّلات) — إعادات offline لا تُكرّر.

الموبايل قد يُعيد POST نفسه (شبكة ضعيفة/مزامنة batch). بمفتاح Idempotency-Key
(UUID) يُسجَّل الأمر مرّة، والإعادة الناجحة تُعيد النتيجة المخزّنة بلا إعادة تنفيذ،
وإعادة بينما الأصل قيد المعالجة ⇒ 409. هنا نثبّت منطق _idempotent النقيّ (store
مُحقَن) + تحقّق _idem_key، + تعاقُد على ربط create_activity.
"""

from __future__ import annotations

import os
import re
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
MAIN = os.path.join(CORE, "api", "main.py")
ROUTERS = os.path.join(CORE, "api", "routers")


def _handler_src(name: str) -> str:
    """مصدر معالِج بالاسم — قد يكون في main.py أو في وحدات routers بعد تفكيك
    monolith (P0). نبحث في main.py أوّلاً ثمّ في كلّ ملفّات routers، فيبقى فحص
    التعاقُد صحيحاً أينما استقرّ المعالِج."""
    sources = [MAIN]
    if os.path.isdir(ROUTERS):
        sources += [
            os.path.join(ROUTERS, f) for f in sorted(os.listdir(ROUTERS)) if f.endswith(".py")
        ]
    needle = f"async def {name}("
    for path in sources:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        start = src.find(needle)
        if start == -1:
            continue
        nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
        end = (start + 1 + nxt.start()) if nxt else len(src)
        return src[start:end]
    raise AssertionError(f"لم يُعثر على المعالِج `{name}` في main.py ولا في routers/")


@pytest.fixture(scope="module")
def m():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as main_mod

    return main_mod


class _FakeStore:
    """نظير CommandStore في الذاكرة — insert ذرّيّ على command_id، get، mark_succeeded."""

    def __init__(self):
        self.rows: dict = {}

    async def insert(self, cmd) -> bool:
        if cmd.command_id in self.rows:
            return False
        self.rows[cmd.command_id] = cmd
        return True

    async def get(self, command_id):
        return self.rows.get(command_id)

    async def mark_succeeded(self, command_id, result):
        from api.command_store import CommandStatus

        c = self.rows[command_id]
        c.status = CommandStatus.SUCCEEDED
        c.result = result


_CID = "11111111-1111-1111-1111-111111111111"
_TID = "22222222-2222-2222-2222-222222222222"


async def test_first_call_runs_and_caches(m):
    store = _FakeStore()
    calls = {"n": 0}

    async def work():
        calls["n"] += 1
        return {"activity_id": "act_x"}

    r = await m._idempotent(
        store, _CID, work, command_type="activity.create", actor_id="u1", tenant_id=_TID, payload={}
    )
    assert r == {"activity_id": "act_x"}
    assert calls["n"] == 1


async def test_replay_returns_cached_without_rerun(m):
    store = _FakeStore()
    calls = {"n": 0}

    async def work():
        calls["n"] += 1
        return {"activity_id": "act_first"}

    kw = dict(command_type="activity.create", actor_id="u1", tenant_id=_TID, payload={})
    first = await m._idempotent(store, _CID, work, **kw)
    # إعادة بنفس المفتاح ⇒ النتيجة المخزّنة، do_work لا يُنفَّذ ثانيةً
    again = await m._idempotent(store, _CID, work, **kw)
    assert first == again == {"activity_id": "act_first"}
    assert calls["n"] == 1, "أُعيد التنفيذ رغم تكرار المفتاح (idempotency مكسور)"


async def test_concurrent_processing_raises_409(m):
    from api.command_store import Command, CommandStatus
    from fastapi import HTTPException

    store = _FakeStore()
    pending = Command.new("activity.create", "u1", _TID, {}, command_id=_CID)
    pending.status = CommandStatus.PROCESSING  # الأصل لم يكتمل بعد
    store.rows[_CID] = pending

    async def work():
        return {"x": 1}

    with pytest.raises(HTTPException) as e:
        await m._idempotent(
            store,
            _CID,
            work,
            command_type="activity.create",
            actor_id="u1",
            tenant_id=_TID,
            payload={},
        )
    assert e.value.status_code == 409


def test_idem_key_validates_uuid(m):
    from fastapi import HTTPException

    assert m._idem_key(None) is None
    # فارغ/مسافات ⇒ يُعامَل كغياب (None، لا 400) — strip ثمّ فحص الفراغ
    assert m._idem_key("") is None
    assert m._idem_key("   ") is None
    good = str(uuid.uuid4())
    assert m._idem_key(good) == good
    assert m._idem_key(f"  {good}  ") == good  # يُعيد المفتاح بعد strip
    with pytest.raises(HTTPException) as e:
        m._idem_key("not-a-uuid")
    assert e.value.status_code == 400


def test_create_activity_wires_idempotency():
    body = _handler_src("create_activity")
    assert "Depends(_idem_key)" in body, "create_activity لا يقبل مفتاح idempotency"
    assert "_idempotent(" in body, "create_activity لا يستدعي _idempotent"
    assert "CommandStore(" in body


def test_update_field_wires_idempotency():
    # توحيد مسار كتابة الحقل: update_field يجب أن يقبل Idempotency-Key ويمرّ عبر
    # _idempotent (نوع أمر field.update) كنظيرَيه create_season/create_activity —
    # وإلّا كان تحديث الحقل ثغرة المسار الوحيدة بلا idempotency (إعادة الموبايل تُكرّر).
    body = _handler_src("update_field")
    assert "Depends(_idem_key)" in body, "update_field لا يقبل مفتاح idempotency"
    assert "_idempotent(" in body, "update_field لا يستدعي _idempotent"
    assert "CommandStore(" in body
    assert '"field.update"' in body or "'field.update'" in body, "نوع أمر field.update مفقود"


# توحيد مسار كتابة الكيانات: نقاط الإنشاء/الإدراج التي كانت بلا idempotency أصبحت
# تمرّ عبر _idempotent (نفس آليّة create_activity المُختبَرة) — إعادة الموبايل
# (offline) لا تُكرّر الإدراج. (handler, command_type) لكلّ نقطة.
_IDEMPOTENT_WRITE_HANDLERS = [
    ("create_farm", "farm.create"),
    ("create_equipment", "equipment.create"),
    ("log_maintenance", "equipment.maintenance.log"),
    ("create_inventory_item", "inventory.item.create"),
    ("add_inventory_batch", "inventory.batch.add"),
    ("register_document", "document.register"),
    # الدفعة الثانية — نقاط إنشاء إضافيّة
    ("register_device", "device.create"),
    ("create_harvest_lot", "harvest_lot.create"),
    ("add_custody_event", "custody.event.add"),
    ("create_master_data", "master_data.create"),
    ("submit_onboarding", "onboarding.submit"),
    # NOTE: record_recommendation_outcome moved off the local CommandStore path in
    # P4.5 (decision-service owns loop persistence). Its boundary-forwarding
    # idempotency contract is asserted separately in
    # test_recommendation_outcome_forwards_idempotency_to_decision_service.
]


@pytest.mark.parametrize("handler,command_type", _IDEMPOTENT_WRITE_HANDLERS)
def test_write_endpoint_wires_idempotency(handler, command_type):
    body = _handler_src(handler)
    assert "Depends(_idem_key)" in body, f"{handler} لا يقبل مفتاح idempotency"
    assert "_idempotent(" in body, f"{handler} لا يستدعي _idempotent"
    assert "CommandStore(" in body, f"{handler} لا يبني CommandStore"
    assert f'"{command_type}"' in body or f"'{command_type}'" in body, (
        f"{handler}: نوع أمر {command_type} مفقود"
    )


def test_recommendation_outcome_forwards_idempotency_to_decision_service():
    """P4.5: recommendation-outcome loop persistence moved to decision-service.

    The platform no longer wraps the write in a local CommandStore/_idempotent; instead
    it still intakes the Idempotency-Key header and forwards it to the decision-service
    facade, which owns loop-table idempotency semantics. This asserts the key is not
    silently dropped at the boundary.
    """
    body = _handler_src("record_recommendation_outcome")
    assert "Depends(_idem_key)" in body, "record_recommendation_outcome لا يقبل مفتاح idempotency"
    assert "_record_recommendation_outcome_via_service" in body, (
        "record_recommendation_outcome لا يفوّض الكتابة إلى decision-service"
    )
    assert '"idempotency_key": idem' in body, (
        "record_recommendation_outcome لا يمرّر مفتاح idempotency إلى decision-service"
    )
    # الكتابة المباشرة (CommandStore محلّيّ) انتقلت إلى decision-service — يجب ألّا تبقى.
    assert "CommandStore(" not in body, (
        "record_recommendation_outcome ما زال يبني CommandStore محلّيّاً بعد نقل الملكيّة"
    )


def test_create_field_path_wires_idempotency():
    # مسار إنشاء الحقل خاصّ: نقطتا الدخول (create_field/import_field) تقبلان المفتاح
    # وتمرّرانه، والمنطق المشترك _persist_field يلفّ الكتابة بـ_idempotent
    # (نوع أمر field.create) — آخر مسار إنشاء كان بلا idempotency.
    for entry in ("create_field", "import_field"):
        src = _handler_src(entry)
        assert "Depends(_idem_key)" in src, f"{entry} لا يقبل مفتاح idempotency"
        assert "idem=idem" in src, f"{entry} لا يمرّر المفتاح إلى _persist_field"
    pf = _handler_src("_persist_field")
    assert "_idempotent(" in pf, "_persist_field لا يستدعي _idempotent"
    assert "CommandStore(" in pf, "_persist_field لا يبني CommandStore"
    assert '"field.create"' in pf, "_persist_field: نوع أمر field.create مفقود"
