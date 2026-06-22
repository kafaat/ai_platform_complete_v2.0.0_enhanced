"""اختبارات وحدة (unit) لتوزيع المزامنة offline بسلطة الخادم — شريحة field.update.

تثبت منطق التوزيع/التفرّع نقيّاً بلا قاعدة حيّة (conn مزيّف يُرجِع وسم UPDATE):

  • dispatch_decision: field.update ⇒ apply؛ كلّ نوع آخر ⇒ ledger (سجلّ فقط).
  • apply_field_update (نجاح): UPDATE أصاب صفّاً ⇒ "applied".
  • apply_field_update (قديم): base_version مُمرَّر + UPDATE 0 صفّ ⇒ "conflict" (409،
    سلطة الخادم، لا كتابة فوقيّة صامتة).
  • _field_update_set_clause: allowlist صارمة (يتجاهل مفاتيح غير معرّفة) + بارامترات.
  • نوع مجهول/معروف غير field.update ⇒ ledger-only (لا تطبيق نطاقيّ هنا).

تُعلَّم unit (بوّابة CI تشغّل -m unit). نواة بلا خدمات (لا Postgres).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

pytest.importorskip("fastapi")

from api.offline_sync_db import (  # noqa: E402
    FIELD_UPDATE_KIND,
    _field_update_set_clause,
    apply_field_update,
    dispatch_decision,
)


class _FakeOp:
    """عمليّة مزيّفة تكفي للتوزيع: kind + payload (op_id/user_id غير لازمة هنا)."""

    def __init__(self, kind, payload):
        self.kind = kind
        self.payload = payload
        self.op_id = "op-1"
        self.user_id = "u-1"
        self.created_at = "2026-06-22T00:00:00"


class _FakeConn:
    """conn مزيّف: execute يُرجِع وسماً ثابتاً ويلتقط آخر (sql, args)."""

    def __init__(self, tag: str):
        self._tag = tag
        self.last_sql: str | None = None
        self.last_args: tuple | None = None

    async def execute(self, sql, *args):  # noqa: ANN001
        self.last_sql = sql
        self.last_args = args
        return self._tag


# ── dispatch_decision ───────────────────────────────────────────


def test_dispatch_field_update_applies():
    assert dispatch_decision(FIELD_UPDATE_KIND) == "apply"
    assert dispatch_decision("field.update") == "apply"


def test_dispatch_other_kinds_ledger_only():
    for kind in ("observation_create", "task_update", "harvest_lot_create", "unknown.kind"):
        assert dispatch_decision(kind) == "ledger"


def test_dispatch_accepts_enum_like_value():
    class _K:
        value = "field.update"

    assert dispatch_decision(_K()) == "apply"


# ── _field_update_set_clause (allowlist + بارامترات) ────────────


def test_set_clause_allowlist_and_params():
    # name/crop/soil_ph مسموحة؛ field_id/base_version/ضارّ تُتجاهَل (ليست أعمدة قابلة للتحديث).
    set_clause, values = _field_update_set_clause(
        {
            "field_id": "f-1",
            "base_version": 3,
            "name": "حقل أ",
            "crop": "wheat",
            "soil_ph": 7.1,
            "evil; DROP TABLE fields": 1,
        }
    )
    assert "name = $1" in set_clause
    assert "crop = $2" in set_clause
    assert "soil_ph = $3" in set_clause
    # لا حقن: المفاتيح غير المعرّفة لا تظهر في الـSQL إطلاقاً.
    assert "field_id" not in set_clause
    assert "base_version" not in set_clause
    assert "DROP TABLE" not in set_clause
    assert values == ["حقل أ", "wheat", 7.1]


def test_set_clause_empty_raises():
    with pytest.raises(ValueError):
        _field_update_set_clause({"field_id": "f-1", "base_version": 2})


# ── apply_field_update (نجاح / تعارض / حمولة فاسدة) ─────────────


async def test_apply_field_update_success():
    op = _FakeOp(FIELD_UPDATE_KIND, {"field_id": "f-1", "base_version": 5, "name": "جديد"})
    conn = _FakeConn("UPDATE 1")
    outcome = await apply_field_update(conn, op=op, tenant_id="t-1")
    assert outcome == "applied"
    # حارس التزامن التفاؤليّ مُلحق (base_version في WHERE) + رفع row_version.
    assert "row_version = row_version + 1" in conn.last_sql
    assert "AND row_version =" in conn.last_sql
    # القيمة + field_id + base_version مُمرَّرة كبارامترات (لا في نصّ الـSQL).
    assert conn.last_args == ("جديد", "f-1", 5)


async def test_apply_field_update_stale_is_conflict():
    op = _FakeOp(FIELD_UPDATE_KIND, {"field_id": "f-1", "base_version": 2, "name": "x"})
    conn = _FakeConn("UPDATE 0")  # base_version لا يطابق ⇒ 0 صفّ
    outcome = await apply_field_update(conn, op=op, tenant_id="t-1")
    assert outcome == "conflict"


async def test_apply_field_update_no_base_version_zero_rows_is_conflict():
    # بلا base_version: 0 صفّ يعني الحقل غير موجود/خارج المستأجِر ⇒ لا نخترع نجاحاً.
    op = _FakeOp(FIELD_UPDATE_KIND, {"field_id": "f-404", "name": "x"})
    conn = _FakeConn("UPDATE 0")
    outcome = await apply_field_update(conn, op=op, tenant_id="t-1")
    assert outcome == "conflict"
    assert "AND row_version =" not in conn.last_sql  # لا حارس إصدار بلا base_version


async def test_apply_field_update_missing_field_id_raises():
    op = _FakeOp(FIELD_UPDATE_KIND, {"name": "x"})  # لا field_id
    conn = _FakeConn("UPDATE 1")
    with pytest.raises(ValueError):
        await apply_field_update(conn, op=op, tenant_id="t-1")
