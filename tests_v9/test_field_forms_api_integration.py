"""اختبارات تكامل API حيّة (TestClient/ASGI) — GAP-FIELD-FORMS-01 / P1.

تشغّل field_forms_api عبر TestClient حقيقيّ (طلب/استجابة HTTP كاملان) فوق قاعدة
زائفة في الذاكرة (FakeDB تحاكي asyncpg) — تغطّي القرار الكامل لمسار §12.1 دون PG حيّ:
accepted · no_active_assignment · form_version_unknown · stale_proven ·
invalid_sync_proof (بما فيه غياب X-Device-Id) · withdrawn · form_validation_failed ·
dedup idempotent · بوّابات الراية/التوكن (404/503/401).

تتخطّى كاملًا إن غاب fastapi (وظيفة Integration في CI تثبّت تبعيّات دنيا).
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="integration job installs minimal deps (no fastapi)")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "scout-ingest-service"))

import fastapi  # noqa: E402
import fastapi.testclient  # noqa: E402

os.environ.setdefault("FIELD_FORMS_SYNC_HMAC_KEY", "it-secret")
os.environ.setdefault("FIELD_FORMS_SYNC_HMAC_KEY_ID", "k1")

import field_forms_api as api  # noqa: E402

from shared.contracts.forms.sync_token import issue_token  # noqa: E402

TENANT = str(uuid.uuid4())
SECRET = "it-secret"

SCHEMA = {
    "fields": [
        {
            "key": "crop",
            "field_type": "select",
            "options": ["wheat", "barley"],
            "required": True,
        },
        {"key": "severity", "field_type": "number", "validation_rules": {"min": 0, "max": 5}},
        {"key": "notes", "field_type": "text", "validation_rules": {"max_length": 50}},
    ]
}
SCHEMA_HASH = (
    __import__("hashlib")
    .sha256(json.dumps(SCHEMA, sort_keys=True, separators=(",", ":")).encode())
    .hexdigest()
)


# ══ قاعدة زائفة في الذاكرة — تحاكي سطح asyncpg الذي يستخدمه field_forms_api ══
class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeDB:
    def __init__(self):
        self.definitions = {}  # code -> {"id", ...}
        self.versions = {}  # id -> row dict
        self.assignments = {}  # id -> row dict
        self.envelopes = {}  # idempotency_key -> {"id", "content_hash"}
        self.envelope_by_id = {}
        self.field_submissions = {}  # id -> row

    # -- connection surface -------------------------------------------------
    def transaction(self):
        return _Txn()

    async def execute(self, query, *args):
        if "set_config" in query:
            return
        if "UPDATE field_form_versions SET status = 'retired'" in query and "superseded" in query:
            # تقاعد المنشورة الحاليّة (superseded) عند النشر — args: def_id, vid, actor
            for v in self.versions.values():
                if v["form_definition_id"] == args[0] and v["status"] == "published":
                    v["status"] = "retired"
                    v["retirement_mode"] = "superseded"
            return
        if "UPDATE field_form_versions SET status = 'published'" in query:
            v = self.versions[args[0]]
            v["status"] = "published"
            v["published_by"] = args[1]
            return
        if "UPDATE field_form_versions SET status = 'retired'" in query:
            v = self.versions[args[0]]
            v["status"] = "retired"
            v["retirement_mode"] = args[3]
            return
        raise AssertionError(f"execute غير متوقّع: {query[:80]}")

    async def fetchval(self, query, *args):
        if "SELECT id FROM field_form_definitions WHERE code" in query:
            row = self.definitions.get(args[0])
            return row["id"] if row else None
        if "INSERT INTO field_form_definitions" in query:
            did = str(uuid.uuid4())
            self.definitions[args[1]] = {"id": did, "tenant_id": args[0], "code": args[1]}
            return did
        if "INSERT INTO field_form_versions" in query:
            vid = str(uuid.uuid4())
            def_id = args[1]
            num = 1 + max(
                (
                    v["version_number"]
                    for v in self.versions.values()
                    if v["form_definition_id"] == def_id
                ),
                default=0,
            )
            self.versions[vid] = {
                "id": vid,
                "tenant_id": args[0],
                "form_definition_id": def_id,
                "version_number": num,
                "status": "draft",
                "retirement_mode": None,
                "schema_json": json.loads(args[2]),
                "logic_json": json.loads(args[3]) if args[3] else None,
                "schema_hash": args[6],
                "published_by": None,
            }
            return vid
        if "INSERT INTO field_form_assignments" in query:
            aid = str(uuid.uuid4())
            self.assignments[aid] = {
                "id": aid,
                "tenant_id": args[0],
                "form_version_id": args[1],
                "field_id": args[2],
                "revision": 1,
            }
            return aid
        if "INSERT INTO external_submissions" in query:
            eid = len(self.envelope_by_id) + 1
            self.envelopes[args[7]] = {"id": eid, "content_hash": args[6]}
            self.envelope_by_id[eid] = {"id": eid, "trust_status": args[13]}
            return eid
        if "INSERT INTO field_submissions" in query:
            fsid = str(uuid.uuid4())
            self.field_submissions[fsid] = {
                "id": fsid,
                "envelope_id": args[4],
                "form_validation_status": args[6],
                "version_resolution_status": args[7],
                "stale_version": args[8],
                "assignment_id": args[2],
            }
            return fsid
        raise AssertionError(f"fetchval غير متوقّع: {query[:80]}")

    async def fetchrow(self, query, *args):
        if "SELECT form_definition_id, status FROM field_form_versions WHERE id" in query:
            return self.versions.get(args[0])
        if "SELECT id, form_definition_id, status, retirement_mode" in query:
            return self.versions.get(args[0])
        if "SELECT id, content_hash FROM external_submissions" in query:
            return self.envelopes.get(args[1])
        if "FROM field_submissions WHERE envelope_id" in query:
            for row in self.field_submissions.values():
                if row["envelope_id"] == args[0]:
                    return row
            return None
        if "SELECT field_id FROM field_form_assignments WHERE tenant_id" in query:
            row = self.assignments.get(args[1])
            return {"field_id": row["field_id"]} if row else None
        raise AssertionError(f"fetchrow غير متوقّع: {query[:80]}")

    async def fetch(self, query, *args):
        if "FROM field_form_assignments a" in query and "a.field_id = $1" in query:
            # مسار التنزيل: field_id فقط
            return [
                {
                    "assignment_id": a["id"],
                    "revision": a["revision"],
                    "version_id": v["id"],
                    "version_number": v["version_number"],
                    "schema_json": v["schema_json"],
                    "logic_json": v["logic_json"],
                    "schema_hash": v["schema_hash"],
                    "form_definition_id": v["form_definition_id"],
                }
                for a in self.assignments.values()
                for v in [self.versions[a["form_version_id"]]]
                if a["field_id"] == args[0] and v["status"] == "published"
            ]
        if "SELECT a.id FROM field_form_assignments a" in query:
            # _resolve_active_assignment(tenant, field_id, form_definition_id)
            return [
                {"id": a["id"]}
                for a in self.assignments.values()
                for v in [self.versions[a["form_version_id"]]]
                if a["field_id"] == args[1]
                and v["form_definition_id"] == args[2]
                and v["status"] == "published"
            ]
        raise AssertionError(f"fetch غير متوقّع: {query[:80]}")

    async def close(self):
        return


# ══ تركيب التطبيق + العميل ══
@pytest.fixture()
def client(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(api, "_tenant_conn", lambda tenant: _return(db))
    monkeypatch.setenv("FIELD_FORMS_ENABLED", "1")
    monkeypatch.setenv("FIELD_FORMS_SERVICE_TOKEN", "svc-token")
    monkeypatch.setenv("FIELD_FORMS_SYNC_HMAC_KEY", SECRET)
    monkeypatch.setenv("FIELD_FORMS_SYNC_HMAC_KEY_ID", "k1")
    app = fastapi.FastAPI()
    app.include_router(api.router)
    tc = fastapi.testclient.TestClient(app)
    tc.db = db  # وصول الاختبار للحالة
    return tc


async def _return(value):
    return value


H = {"X-Field-Forms-Token": "svc-token", "X-Tenant-Id": TENANT}


def _mk_published(tc, field_id="field-1", assign=True):
    """ينشئ تعريفًا + مسودّة + نشر + (إسناد) عبر الـAPI نفسه — يعيد (def_code, version_id)."""
    code = f"form-{uuid.uuid4().hex[:8]}"
    r = tc.post("/internal/field-forms/definitions", headers=H, json={"code": code, "title": "T"})
    assert r.status_code == 201, r.text
    r = tc.post(
        f"/internal/field-forms/definitions/{code}/versions",
        headers=H,
        json={"schema_json": SCHEMA},
    )
    assert r.status_code == 201, r.text
    vid = r.json()["version_id"]
    assert r.json()["schema_hash"] == SCHEMA_HASH
    r = tc.post(f"/internal/field-forms/versions/{vid}/publish", headers=H)
    assert r.status_code == 200, r.text
    if assign:
        r = tc.post(
            "/internal/field-forms/assignments",
            headers=H,
            json={"form_version_id": vid, "field_id": field_id},
        )
        assert r.status_code == 201, r.text
    return code, vid


def _submission(vid, instance=None, field_id="field-1", **over):
    body = {
        "provider": "odk",
        "server": "odk.example",
        "instance_id": instance or f"uuid:{uuid.uuid4()}",
        "submitted_at": "2026-07-21T10:00:00Z",
        "field_id": field_id,
        "form_version_id": vid,
        "schema_hash": SCHEMA_HASH,
        "answers": {"crop": "wheat", "severity": 3},
    }
    body.update(over)
    return body


# ══ البوّابات ══
def test_disabled_flag_returns_404(client, monkeypatch):
    monkeypatch.setenv("FIELD_FORMS_ENABLED", "0")
    r = client.post(
        "/internal/field-forms/definitions", headers=H, json={"code": "x", "title": "t"}
    )
    assert r.status_code == 404


def test_wrong_service_token_returns_401(client):
    r = client.post(
        "/internal/field-forms/definitions",
        headers={"X-Field-Forms-Token": "wrong", "X-Tenant-Id": TENANT},
        json={"code": "x", "title": "t"},
    )
    assert r.status_code == 401


def test_missing_token_config_returns_503(client, monkeypatch):
    monkeypatch.setenv("FIELD_FORMS_SERVICE_TOKEN", "")
    r = client.post(
        "/internal/field-forms/definitions", headers=H, json={"code": "x", "title": "t"}
    )
    assert r.status_code == 503


# ══ دورة الحياة الكاملة + قبول ══
def test_full_lifecycle_accepted_current(client):
    _code, vid = _mk_published(client)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(vid),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trust_status"] == "accepted"
    assert body["version_resolution_status"] == "current"
    assert body["stale_version"] is False
    assert body["field_submission_id"]
    # assignment حُفظ فعليًّا (P0-3)
    row = next(iter(client.db.field_submissions.values()))
    assert row["assignment_id"] is not None


def test_schema_invalid_rejected_at_version_creation(client):
    tc_post = client.post(
        "/internal/field-forms/definitions",
        headers=H,
        json={"code": f"f-{uuid.uuid4().hex[:6]}", "title": "t"},
    )
    code = tc_post.json()["definition_id"]
    r = client.post(
        f"/internal/field-forms/definitions/{code}/versions",
        headers=H,
        json={"schema_json": {"fields": [{"key": "x", "field_type": "flutter_widget"}]}},
    )
    assert r.status_code == 422


# ══ P0-3: current بلا إسناد ⇒ حجر ══
def test_current_without_assignment_quarantined(client):
    _code, vid = _mk_published(client, assign=False)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "s", "X-Device-Id": "d"},
        json=_submission(vid),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trust_status"] == "quarantined"
    assert body["quarantine_reason"] == "no_active_assignment"


# ══ إصدار مجهول ⇒ حجر خامّ ══
def test_unknown_version_quarantined_no_row(client):
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "s", "X-Device-Id": "d"},
        json=_submission(str(uuid.uuid4())),
    )
    body = r.json()
    assert body["trust_status"] == "quarantined"
    assert body["quarantine_reason"] == "form_version_unknown"
    assert client.db.field_submissions == {}  # لا صفّ لإصدار مجهول (§12.1)


# ══ P0-2: superseded يتطلّب إثباتًا كاملًا ══
def _supersede(client, vid):
    """يتقاعد النسخة بنمط superseded (كأنّ نسخة أحدث نُشرت)."""
    client.db.versions[vid]["status"] = "retired"
    client.db.versions[vid]["retirement_mode"] = "superseded"


def _valid_token(vid, assignment_id, revision=1, actor="scout-1", device="dev-1"):
    return issue_token(
        {
            "token_version": 1,
            "key_id": "k1",
            "tenant_id": TENANT,
            "actor_id": actor,
            "device_id": device,
            "assignment_id": assignment_id,
            "revision": revision,
            "form_version_id": vid,
            "schema_hash": SCHEMA_HASH,
            "issued_at": time.time(),
        },
        secret=SECRET,
        key_id="k1",
    )


def test_superseded_with_full_proof_accepted_stale(client):
    _code, vid = _mk_published(client)
    aid = next(iter(client.db.assignments))
    _supersede(client, vid)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(vid, assignment_revision=1, definition_sync_token=_valid_token(vid, aid)),
    )
    body = r.json()
    assert body["trust_status"] == "accepted", body
    assert body["version_resolution_status"] == "stale_proven"
    assert body["stale_version"] is True


def test_superseded_missing_device_header_fails(client):
    """P0-2: حذف X-Device-Id كان يُلغي المقارنة سابقًا — الآن يفشل الإثبات."""
    _code, vid = _mk_published(client)
    aid = next(iter(client.db.assignments))
    _supersede(client, vid)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1"},  # بلا X-Device-Id
        json=_submission(vid, assignment_revision=1, definition_sync_token=_valid_token(vid, aid)),
    )
    body = r.json()
    assert body["trust_status"] == "quarantined"
    assert body["quarantine_reason"] == "invalid_sync_proof"


def test_superseded_missing_revision_fails(client):
    _code, vid = _mk_published(client)
    aid = next(iter(client.db.assignments))
    _supersede(client, vid)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(vid, definition_sync_token=_valid_token(vid, aid)),
    )
    assert r.json()["quarantine_reason"] == "invalid_sync_proof"


def test_superseded_assignment_not_in_db_fails(client):
    """مطالبة assignment صحيحة التوقيع لكنّها غير موجودة في PostgreSQL ⇒ مرفوضة."""
    _code, vid = _mk_published(client)
    _supersede(client, vid)
    ghost = str(uuid.uuid4())  # assignment غير موجود
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(
            vid, assignment_revision=1, definition_sync_token=_valid_token(vid, ghost)
        ),
    )
    assert r.json()["quarantine_reason"] == "invalid_sync_proof"


# ══ withdrawn يُحجَر مهما كان التوكن ══
def test_withdrawn_quarantined_even_with_valid_token(client):
    _code, vid = _mk_published(client)
    aid = next(iter(client.db.assignments))
    client.db.versions[vid]["status"] = "retired"
    client.db.versions[vid]["retirement_mode"] = "withdrawn"
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(vid, assignment_revision=1, definition_sync_token=_valid_token(vid, aid)),
    )
    body = r.json()
    assert body["trust_status"] == "quarantined"
    assert body["quarantine_reason"] == "form_version_withdrawn"


# ══ فشل تحقّق الإجابات ══
def test_invalid_answers_quarantined(client):
    _code, vid = _mk_published(client)
    r = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "s", "X-Device-Id": "d"},
        json=_submission(vid, answers={"crop": "wheat", "severity": 99}),  # فوق max=5
    )
    body = r.json()
    assert body["trust_status"] == "quarantined"
    assert body["quarantine_reason"] == "form_validation_failed"
    assert any("above_max" in e for e in body["validation_errors"])


# ══ dedup: إعادة إرسال متماثلة ⇒ idempotent ══
def test_idempotent_replay_returns_same_envelope(client):
    _code, vid = _mk_published(client)
    body = _submission(vid, instance="uuid:fixed-1")
    hdrs = {**H, "X-Actor-Id": "s", "X-Device-Id": "d"}
    r1 = client.post("/internal/field-forms/submissions", headers=hdrs, json=body)
    r2 = client.post("/internal/field-forms/submissions", headers=hdrs, json=body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r2.json()["idempotent"] is True
    assert r2.json()["envelope_id"] == r1.json()["envelope_id"]


# ══ التنزيل يصدر توكنًا قابلًا للاستعمال ══
def test_download_issues_usable_sync_token(client):
    _code, vid = _mk_published(client)
    r = client.get(
        "/internal/field-forms/download",
        headers=H,
        params={"field_id": "field-1", "actor_id": "scout-1", "device_id": "dev-1"},
    )
    assert r.status_code == 200, r.text
    forms = r.json()["forms"]
    assert len(forms) == 1 and forms[0]["schema_hash"] == SCHEMA_HASH
    token = forms[0]["definition_sync_token"]
    # نفس التوكن يقبل stale_proven بعد التقاعد
    _supersede(client, vid)
    r2 = client.post(
        "/internal/field-forms/submissions",
        headers={**H, "X-Actor-Id": "scout-1", "X-Device-Id": "dev-1"},
        json=_submission(
            vid,
            assignment_revision=forms[0]["revision"],
            definition_sync_token=token,
        ),
    )
    assert r2.json()["version_resolution_status"] == "stale_proven"
