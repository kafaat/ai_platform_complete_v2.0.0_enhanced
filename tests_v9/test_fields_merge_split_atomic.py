"""اختبارات وحدة (unit): دمج/انقسام الحقول ذرّيّاً — معاملة واحدة، لا فقد بيانات.

تثبت بلا قاعدة حيّة (conn مزيّف + tenant_connection / المساعِدات مُرقَّعة) أنّ نقطتَي
``POST /api/v1/fields/merge`` و``POST /api/v1/fields/split`` تُنفّذان العمليّة ذرّيّاً
داخل معاملة tenant_connection واحدة، مغلقةً خطر «البيانات الثلاثيّة» الذي كانت تُسبّبه
لاذرّيّة الواجهة (POST جديد + حلقة DELETE بلا معاملة):

  (أ) الدمج السعيد: INSERT(المدموج) ثمّ DELETE لكلّ مصدر + يصدر FIELD_CREATED
      وFIELD_DELETED (لكلّ مصدر).
  (ب) **التراجع**: فشل DELETE مصدر يتصاعد (لا يُبتلَع) ⇒ الاستثناء يصعد عبر
      tenant_connection فتتراجع المعاملة كاملةً (لا حقل مدموج يتيَّم).
  (ج) موسم نشط على مصدر ⇒ 409 بلا أيّ INSERT/DELETE.
  (د) مصدر ليس ضمن المستأجِر ⇒ 404.
  (هـ) إعادة idempotent بالمفتاح نفسه تُعيد النتيجة المخزّنة بلا إعادة تشغيل _work.

نواة بلا خدمات (لا Postgres). تُعلَّم unit. نمط التظليل يطابق
``tests_v9/test_scouting_pins_persistence.py``: conn مزيّف + monkeypatch لـ
tenant_connection والمساعِدات (الأحداث/سجلّ الهندسة/إبطال الراستر/حالة الحقل).
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

pytest.importorskip("fastapi")

# مربّعان صغيران صالحان داخل اليمن (≈١١ هكتار لكلٍّ — يمرّان guard_field_geometry
# الحقيقيّ؛ 0.1° يتجاوز سقف المساحة فنستعمل 0.003°).
_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.003, 15.0], [44.003, 15.003], [44.0, 15.003], [44.0, 15.0]]],
}
_SQUARE_B = {
    "type": "Polygon",
    "coordinates": [
        [[44.003, 15.0], [44.006, 15.0], [44.006, 15.003], [44.003, 15.003], [44.003, 15.0]]
    ],
}


class _FakeUser:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "manager"


class _FakeConn:
    """conn مزيّف يُحاكي asyncpg ويسجّل كلّ execute (لِفحص ترتيب INSERT/DELETE).

    ``fetchrow``/``fetchval`` قابلان للضبط عبر دوال side_effect (تُستدعى بالـSQL
    والوسائط) ليُحاكى «مصدر موجود/غائب» و«موسم نشط/لا». ``fail_delete_on`` يجعل
    DELETE لمعرّف بعينه يرفع — لِاختبار التراجع.
    """

    def __init__(self, *, fetchrow=None, fetchval=None, fail_delete_on=None):
        self._fetchrow = fetchrow or (lambda sql, *a: None)
        self._fetchval = fetchval or (lambda sql, *a: 0)
        self.fail_delete_on = fail_delete_on
        self.executes: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):  # noqa: ANN001
        return self._fetchrow(sql, *args)

    async def fetchval(self, sql, *args):  # noqa: ANN001
        return self._fetchval(sql, *args)

    async def execute(self, sql, *args):  # noqa: ANN001
        self.executes.append((sql, args))
        if (
            self.fail_delete_on is not None
            and sql.startswith("DELETE FROM fields")
            and args
            and args[0] == self.fail_delete_on
        ):
            raise RuntimeError("delete failed — اتّصال متقطّع")
        return "DELETE 1" if sql.startswith("DELETE") else "INSERT 0 1"


class _FakeTenantConn:
    """async context manager يُحاكي tenant_connection (معاملة): يتراجع عند الاستثناء.

    ``__aexit__`` يُرجِع False فيُعاد رفع الاستثناء — تماماً كمعاملة فعليّة تتراجع
    (لا commit) عند صعود خطأ من جسم ``async with``.
    """

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fields_mod(monkeypatch):
    import api.main  # noqa: F401, WPS433 — يحلّ الدورة (يستورد الموجِّهات في نهايته)
    import api.routers.fields as m  # noqa: WPS433

    # تظليل تأثيرات _insert_field_within_tx الجانبيّة (لا قاعدة): الأحداث + سجلّ
    # الهندسة + إبطال الراستر + حالة الحقل. نُبقي guard_field_geometry/الإدراج الحقيقيّ.
    async def _noop_emit(conn, user, name, etype, eid, payload, **kw):  # noqa: ANN001
        emitted.append((name, eid, payload))

    async def _noop_revision(conn, **kw):  # noqa: ANN001
        return 1

    async def _noop_stale(conn, **kw):  # noqa: ANN001
        return None

    async def _noop_state(conn, field_id):  # noqa: ANN001
        return {"changed": False, "state": {}}

    emitted: list = []
    monkeypatch.setattr(m, "_emit_domain_event", _noop_emit, raising=True)
    monkeypatch.setattr(m, "save_field_geometry_revision", _noop_revision, raising=True)
    monkeypatch.setattr(m, "mark_raster_cache_stale", _noop_stale, raising=True)
    import api.field_state_projection as fsp  # noqa: WPS433

    monkeypatch.setattr(fsp, "recompute_field_state", _noop_state, raising=True)
    m._test_emitted = emitted  # نكشف الأحداث المُصدَرة للاختبار
    return m


# ─── نماذج الطلب (تحقّق Pydantic) ───────────────────────────────────────────


def test_merge_request_validates_min_two_sources(fields_mod):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fields_mod.FieldMergeRequest(source_field_ids=["a"], name="م", geometry=_SQUARE)
    # حقلان صالحان ⇒ يُقبَل
    req = fields_mod.FieldMergeRequest(
        source_field_ids=["a", "b"], name="المدموج", geometry=_SQUARE
    )
    assert req.source_field_ids == ["a", "b"]


def test_merge_request_rejects_duplicate_sources(fields_mod):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fields_mod.FieldMergeRequest(source_field_ids=["a", "a"], name="م", geometry=_SQUARE)


def test_split_request_validates_children_range(fields_mod):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fields_mod.FieldSplitRequest(
            source_field_id="src",
            children=[{"name": "أ", "geometry": _SQUARE}],  # طفل واحد < 2
        )
    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQUARE}, {"name": "ب", "geometry": _SQUARE_B}],
    )
    assert len(req.children) == 2


# ─── (أ) الدمج السعيد: INSERT المدموج ثمّ DELETE لكلّ مصدر + أحداث ──────────────


async def test_merge_happy_path_inserts_then_deletes(fields_mod, monkeypatch):
    user = _FakeUser()

    def _fetchrow(sql, *a):  # noqa: ANN001
        # تحميل المصدر (ملكيّة) أو قراءته قبل الحذف ⇒ صفّ موجود.
        if "FROM fields" in sql:
            return {"field_id": a[0], "name": f"src-{a[0]}", "crop": "قمح"}
        return None

    conn = _FakeConn(fetchrow=_fetchrow, fetchval=lambda sql, *a: 0)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, **kw):
            self.tasks.append(kw)

    bg = _BG()
    req = fields_mod.FieldMergeRequest(
        source_field_ids=["a", "b"], name="المدموج", crop="قمح", geometry=_SQUARE
    )
    out = await fields_mod.merge_fields(req=req, background_tasks=bg, user=user, idem=None)

    assert out["name_ar"] == "المدموج"
    assert out["field_id"].startswith("fld_")
    # ترتيب ذرّيّ: INSERT(المدموج) قبل DELETE المصادر، وDELETE لكلّ مصدر.
    inserts = [sql for sql, _ in conn.executes if sql.startswith("INSERT INTO fields")]
    deletes = [args[0] for sql, args in conn.executes if sql.startswith("DELETE FROM fields")]
    assert len(inserts) == 1
    assert deletes == ["a", "b"]
    first_insert_idx = next(
        i for i, (sql, _) in enumerate(conn.executes) if sql.startswith("INSERT INTO fields")
    )
    first_delete_idx = next(
        i for i, (sql, _) in enumerate(conn.executes) if sql.startswith("DELETE FROM fields")
    )
    assert first_insert_idx < first_delete_idx  # create-before-delete
    # أحداث: FIELD_CREATED للمدموج + FIELD_DELETED لكلّ مصدر.
    names = [n for n, _, _ in fields_mod._test_emitted]
    assert "FIELD_CREATED" in names
    assert names.count("FIELD_DELETED") == 2
    deleted_meta = [p for n, _, p in fields_mod._test_emitted if n == "FIELD_DELETED"]
    assert all(p["merged_into"] == out["field_id"] for p in deleted_meta)
    # مهمّة خلفيّة بعد الالتزام (معالجة صور) لِلمدموج.
    assert bg.tasks and bg.tasks[0]["field_id"] == out["field_id"]


# ─── (ب) التراجع: فشل DELETE مصدر يتصاعد (لا ابتلاع) ⇒ تتراجع المعاملة ─────────


async def test_merge_source_delete_failure_propagates(fields_mod, monkeypatch):
    """فشل حذف مصدر يرفع ⇒ يصعد عبر tenant_connection فتتراجع المعاملة (لا 200).

    الجوهر: الخطأ غير مُبتلَع — لا يُرجَع نجاح جزئيّ. (المعاملة الحقيقيّة تتراجع
    تلقائيّاً؛ هنا نثبت أنّ الاستثناء يصعد فلا يُلتزَم بحقل مدموج يتيم.)
    """
    user = _FakeUser()

    def _fetchrow(sql, *a):  # noqa: ANN001
        if "FROM fields" in sql:
            return {"field_id": a[0], "name": f"src-{a[0]}", "crop": "قمح"}
        return None

    # الحذف يفشل على المصدر الثاني («b») — بعد نجاح INSERT وحذف «a».
    conn = _FakeConn(fetchrow=_fetchrow, fetchval=lambda sql, *a: 0, fail_delete_on="b")
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def add_task(self, fn, **kw):
            raise AssertionError("لا يجوز جدولة مهمّة خلفيّة عند فشل المعاملة")

    req = fields_mod.FieldMergeRequest(
        source_field_ids=["a", "b"], name="المدموج", geometry=_SQUARE
    )
    # خطأ DB غير HTTPException ⇒ يُغلَّف 503 (المعاملة تراجعت، لا يتيم مُلتزَم).
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=user, idem=None)
    assert ei.value.status_code == 503
    # الحذف الفاشل وقع بعد INSERT (الترتيب ذرّيّ) — والاستثناء منع جدولة الصور.
    assert any(sql.startswith("INSERT INTO fields") for sql, _ in conn.executes)


# ─── (ج) موسم نشط على مصدر ⇒ 409 بلا أيّ INSERT/DELETE ───────────────────────


async def test_merge_active_season_rejected_409_no_writes(fields_mod, monkeypatch):
    user = _FakeUser()

    def _fetchrow(sql, *a):  # noqa: ANN001
        if "FROM fields" in sql:
            return {"field_id": a[0], "name": f"src-{a[0]}", "crop": "قمح"}
        return None

    # موسم نشط (count>0) على أيّ مصدر.
    conn = _FakeConn(fetchrow=_fetchrow, fetchval=lambda sql, *a: 1)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def add_task(self, fn, **kw):
            raise AssertionError("لا مهمّة خلفيّة عند الرفض")

    from fastapi import HTTPException

    req = fields_mod.FieldMergeRequest(
        source_field_ids=["a", "b"], name="المدموج", geometry=_SQUARE
    )
    with pytest.raises(HTTPException) as ei:
        await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=user, idem=None)
    assert ei.value.status_code == 409
    # لا كتابة إطلاقاً (لا INSERT ولا DELETE) — الرفض قبل أيّ تعديل.
    assert conn.executes == []


# ─── (د) مصدر ليس ضمن المستأجِر ⇒ 404 ────────────────────────────────────────


async def test_merge_source_not_in_tenant_404(fields_mod, monkeypatch):
    user = _FakeUser()

    # كلّ تحميل مصدر يُرجِع None (غير موجود ضمن المستأجِر).
    conn = _FakeConn(fetchrow=lambda sql, *a: None, fetchval=lambda sql, *a: 0)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def add_task(self, fn, **kw):
            raise AssertionError("لا مهمّة خلفيّة عند 404")

    from fastapi import HTTPException

    req = fields_mod.FieldMergeRequest(
        source_field_ids=["ghost", "b"], name="المدموج", geometry=_SQUARE
    )
    with pytest.raises(HTTPException) as ei:
        await fields_mod.merge_fields(req=req, background_tasks=_BG(), user=user, idem=None)
    assert ei.value.status_code == 404
    assert conn.executes == []


# ─── (هـ) idempotency: إعادة المفتاح ⇒ نتيجة مخزّنة بلا إعادة تشغيل _work ───────


async def test_merge_idempotent_replay_skips_work(fields_mod, monkeypatch):
    """مع مفتاح idempotency: نُرقّع _idempotent ليُحاكي إعادة (نتيجة سابقة) دون _work.

    نُثبت أنّ المسار يمرّر _work إلى _idempotent ويُعيد ما يُرجِعه دون لمس conn —
    أي إعادة المفتاح لا تُكرّر الدمج (لا INSERT/DELETE ثانٍ).
    """
    user = _FakeUser()
    conn = _FakeConn(fetchrow=lambda sql, *a: None, fetchval=lambda sql, *a: 0)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )
    monkeypatch.setattr(fields_mod, "get_pool", lambda: object(), raising=True)
    monkeypatch.setattr(fields_mod, "CommandStore", lambda pool, conn=None: object(), raising=True)

    stored = {"field_id": "fld_prior000000", "name_ar": "المدموج", "geometry": _SQUARE}

    async def _fake_idem(store, command_id, do_work, **kw):  # noqa: ANN001
        # إعادة: لا نستدعي do_work — نُعيد النتيجة المخزّنة (idempotent).
        return stored

    monkeypatch.setattr(fields_mod, "_idempotent", _fake_idem, raising=True)

    class _BG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, **kw):
            self.tasks.append(kw)

    bg = _BG()
    req = fields_mod.FieldMergeRequest(
        source_field_ids=["a", "b"], name="المدموج", geometry=_SQUARE
    )
    out = await fields_mod.merge_fields(req=req, background_tasks=bg, user=user, idem="key-123")

    assert out == stored
    # do_work لم يُشغَّل ⇒ لا كتابة على conn (لا تكرار للدمج).
    assert conn.executes == []
    # المهمّة الخلفيّة تُجدوَل من النتيجة المخزّنة (post-commit) — حقل واحد.
    assert bg.tasks and bg.tasks[0]["field_id"] == "fld_prior000000"


# ─── انقسام: مسار سعيد (INSERT لكلّ وليد ثمّ DELETE الأصل) ──────────────────────


async def test_split_happy_path_inserts_children_then_deletes_source(fields_mod, monkeypatch):
    user = _FakeUser()

    def _fetchrow(sql, *a):  # noqa: ANN001
        if "FROM fields" in sql:
            return {"field_id": a[0], "name": "الأصل", "crop": "قمح"}
        return None

    conn = _FakeConn(fetchrow=_fetchrow, fetchval=lambda sql, *a: 0)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, **kw):
            self.tasks.append(kw)

    bg = _BG()
    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQUARE}, {"name": "ب", "geometry": _SQUARE_B}],
    )
    out = await fields_mod.split_field(req=req, background_tasks=bg, user=user, idem=None)

    assert isinstance(out, list) and len(out) == 2
    inserts = [sql for sql, _ in conn.executes if sql.startswith("INSERT INTO fields")]
    deletes = [args[0] for sql, args in conn.executes if sql.startswith("DELETE FROM fields")]
    assert len(inserts) == 2  # وليدان
    assert deletes == ["src"]  # حُذِف الأصل
    # كلّ INSERT قبل DELETE الأصل (create-before-delete ذرّيّ).
    last_insert_idx = max(
        i for i, (sql, _) in enumerate(conn.executes) if sql.startswith("INSERT INTO fields")
    )
    del_idx = next(
        i for i, (sql, _) in enumerate(conn.executes) if sql.startswith("DELETE FROM fields")
    )
    assert last_insert_idx < del_idx
    # FIELD_DELETED للأصل يحمل split_into بمعرّفات الأطفال.
    deleted = [p for n, _, p in fields_mod._test_emitted if n == "FIELD_DELETED"]
    assert len(deleted) == 1
    assert deleted[0]["split_into"] == [c["field_id"] for c in out]
    # مهمّة خلفيّة لكلّ وليد.
    assert len(bg.tasks) == 2


async def test_split_active_season_rejected_409(fields_mod, monkeypatch):
    user = _FakeUser()

    def _fetchrow(sql, *a):  # noqa: ANN001
        if "FROM fields" in sql:
            return {"field_id": a[0], "name": "الأصل", "crop": "قمح"}
        return None

    conn = _FakeConn(fetchrow=_fetchrow, fetchval=lambda sql, *a: 1)  # موسم نشط
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda u: _FakeTenantConn(conn), raising=True
    )

    class _BG:
        def add_task(self, fn, **kw):
            raise AssertionError("لا مهمّة خلفيّة عند الرفض")

    from fastapi import HTTPException

    req = fields_mod.FieldSplitRequest(
        source_field_id="src",
        children=[{"name": "أ", "geometry": _SQUARE}, {"name": "ب", "geometry": _SQUARE_B}],
    )
    with pytest.raises(HTTPException) as ei:
        await fields_mod.split_field(req=req, background_tasks=_BG(), user=user, idem=None)
    assert ei.value.status_code == 409
    assert conn.executes == []
