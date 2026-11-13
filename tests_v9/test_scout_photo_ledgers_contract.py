"""SCOUT-PHOTO owner phases 6-11 (v263-v272), unit contract: pure rules and pre-DB gates.

No database: the refusal rules, projections and role/scope tables of the scout-ingest modules,
the tenant-owner admin identity, the HTTP gates that answer before any database contact
(``DATABASE_URL`` empty, so reaching the database answers 503), the schema/registration text and
the staging gates' refusal. The SQL guards, RLS and grants run live in
services/scout-ingest-service/tests/test_media_live.py and test_evidence_ledgers_live.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services" / "scout-ingest-service"
for folder in (str(ROOT), str(SERVICE)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

TENANT = "00000000-0000-0000-0000-0000000000aa"
TOKEN = "ledger-test-token"  # noqa: S105 — test value
EVENT = UUID("11111111-1111-4111-8111-111111111111")
PREVIOUS = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
FLAGS = (
    "SCOUT_MEDIA_DETECTION_LINK_ENABLED",
    "SCOUT_MEDIA_LAB_LINK_ENABLED",
    "SCOUT_MEDIA_HUMAN_REVIEW_ENABLED",
    "SCOUT_MEDIA_TISSUE_SAMPLE_ENABLED",
    "SCOUT_MEDIA_CREDENTIAL_ENFORCEMENT_ENABLED",
    "SCOUT_MEDIA_TREATMENT_REVIEW_ENABLED",
    "SCOUT_MEDIA_RETENTION_ENABLED",
    "SCOUT_MEDIA_GRANTS_ADMIN_ENABLED",
    "SCOUT_MEDIA_GOVERNANCE_ADMIN_ENABLED",
)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ─── the shared chain protocol ──────────────────────────────────────────────


class _Codes:
    def __init__(self):
        import evidence_chain

        self.codes = evidence_chain.ChainCodes(
            "reused", "predecessor", "concurrent", "unverified", "ambiguous"
        )


async def _append(
    *, stored=None, matches=True, head=None, after=None, inserted=1, head_required=False
):
    """Drive ``append_event`` with plain callables (no database object involved)."""
    import evidence_chain

    state = {"stored": stored, "heads": [head, after]}

    async def load_existing():
        return state["stored"]

    async def read_head():
        return state["heads"].pop(0) if len(state["heads"]) > 1 else state["heads"][0]

    async def insert():
        return inserted

    return await evidence_chain.append_event(
        event_id=EVENT,
        previous_event_id=None if head is None else PREVIOUS,
        load_existing=load_existing,
        matches=lambda row: matches,
        read_head=read_head,
        insert=insert,
        codes=_Codes().codes,
        head_required=head_required,
    )


async def test_a_replay_of_the_same_event_is_idempotent_and_another_payload_is_409():
    idem, _ = await _append(stored={"event_id": EVENT}, head={"event_id": EVENT})
    assert idem is True
    with pytest.raises(HTTPException) as exc:
        await _append(stored={"event_id": EVENT}, matches=False)
    assert (exc.value.status_code, exc.value.detail) == (409, "reused")


async def test_a_new_event_must_name_the_head_and_is_verified_after_insert():
    idem, head = await _append(head=None, after={"event_id": EVENT})
    assert idem is False and head["event_id"] == EVENT
    with pytest.raises(HTTPException) as exc:
        await _append(head=None, after={"event_id": uuid4()})
    assert (exc.value.status_code, exc.value.detail) == (503, "unverified")
    with pytest.raises(HTTPException) as exc:
        await _append(head=None, after=None, head_required=True)
    assert exc.value.detail == "predecessor"


async def test_a_lost_insert_without_an_identical_event_is_a_concurrent_conflict():
    with pytest.raises(HTTPException) as exc:
        await _append(inserted=None)
    assert (exc.value.status_code, exc.value.detail) == (409, "concurrent")


def test_single_head_never_picks_one_of_two():
    import evidence_chain

    with pytest.raises(HTTPException) as exc:
        evidence_chain.single_head([1, 2], _Codes().codes)
    assert (exc.value.status_code, exc.value.detail) == (503, "ambiguous")
    assert evidence_chain.single_head([], _Codes().codes) is None


@pytest.mark.parametrize("actor", ["0", "-3", "07", "abc", "1.5", ""])
def test_the_trusted_user_id_must_be_a_canonical_positive_integer(actor):
    import evidence_chain

    with pytest.raises(HTTPException) as exc:
        evidence_chain.positive_user_id(actor, "bad")
    assert exc.value.status_code == 403
    assert evidence_chain.positive_user_id("42", "bad") == 42


def test_only_a_named_guard_refusal_maps_to_403():
    import evidence_chain

    class Refusal(Exception):
        sqlstate = "42501"

    assert evidence_chain.guard_refusal(Refusal("scout_tissue_actor_not_authorized"))
    assert not evidence_chain.guard_refusal(Refusal("permission denied for table scout_x"))


# ─── request rules per ledger ───────────────────────────────────────────────


def test_detection_link_rules():
    import detection_link_api as d

    def ev(**kw):
        return d.DetectionLinkEventIn(
            **({"event_id": EVENT, "action": "link", "detection_provenance_id": 7} | kw)
        )

    assert d.detection_refusal(ev()) == (None, None)
    assert (
        d.detection_refusal(ev(detection_provenance_id=None))[0]
        == "scout_photo_detection_provenance_id_required"
    )
    assert (
        d.detection_refusal(ev(action="revoke"))[0]
        == "scout_photo_detection_revoke_must_not_name_result"
    )
    assert (
        d.detection_refusal(ev(previous_event_id=PREVIOUS))[0]
        == "scout_photo_detection_revision_reason_required"
    )
    assert (
        d.detection_refusal(ev(previous_event_id=EVENT, reason="x"))[0]
        == "scout_photo_detection_link_self_reference"
    )


def test_detection_projection_refuses_a_broken_proof():
    import detection_link_api as d

    row = {
        "event_id": EVENT,
        "action": "link",
        "detection_provenance_id": 7,
        "edge_result_id": 3,
        "attestation": "attested",
        "model_id": "m",
        "model_version": "1",
        "input_sha256": "a" * 64,
        "content_sha256": "a" * 64,
    }
    out = d.public_detection(row)
    assert (
        out["state"] == "linked_model_provenance_unreviewed"
        and out["human_diagnosis_approved"] is False
    )
    for change in (
        {"attestation": "unattested_legacy"},
        {"input_sha256": "b" * 64},
        {"input_sha256": None},
    ):
        with pytest.raises(HTTPException) as exc:
            d.public_detection(row | change)
        assert exc.value.status_code == 503


def test_lab_link_rules_and_projection():
    import lab_link_api as lab

    def ev(**kw):
        return lab.LabLinkEventIn(
            **({"event_id": EVENT, "action": "link", "sample_id": "S-1"} | kw)
        )

    assert lab.lab_refusal(ev()) == (None, None)
    assert lab.lab_refusal(ev(sample_id=" S-1"))[0] == "scout_photo_lab_sample_id_required"
    assert (
        lab.lab_refusal(ev(previous_event_id=PREVIOUS, reason="short"))[0]
        == "scout_photo_lab_revision_reason_required"
    )
    row = {
        "event_id": EVENT,
        "action": "link",
        "sample_id": "S-1",
        "sample_kind": "soil",
        "sample_status": "rejected",
    }
    assert lab.public_lab(row)["state"] == "sample_inactive"
    assert lab.public_lab(row | {"sample_status": "in_lab"})["plant_tissue_sample"] is False
    with pytest.raises(HTTPException):
        lab.public_lab(row | {"sample_kind": None})


def test_human_review_rules_and_projection():
    import human_review_api as h

    def ev(**kw):
        base = {
            "event_id": EVENT,
            "action": "review",
            "assessment": "ruled_out",
            "review_method": "photo_review",
            "reason": "x" * 25,
        }
        return h.HumanReviewEventIn(**(base | kw))

    assert h.review_refusal(ev())[0] is None
    assert (
        h.review_refusal(ev(assessment="suspected"))[0]
        == "scout_photo_human_suspicion_code_mismatch"
    )
    assert (
        h.review_refusal(ev(diagnosis_code="fungal.rust"))[0]
        == "scout_photo_human_suspicion_code_mismatch"
    )
    assert h.review_refusal(ev(action="retract"))[0] == "scout_photo_human_retraction_invalid"
    with pytest.raises(ValueError):
        ev(assessment="confirmed")  # no 'confirmed' diagnosis exists
    row = {
        "event_id": EVENT,
        "action": "review",
        "assessment": "suspected",
        "diagnosis_code": "fungal.rust",
        "review_method": "photo_review",
        "image_sha256": "a" * 64,
        "content_sha256": "a" * 64,
        "reviewer_user_id": 9,
        "reviewer_active": True,
        "reviewer_role": "expert",
        "reviewer_grant_active": True,
    }
    assert h.public_review(row)["state"] == "human_assessment_recorded"
    assert (
        h.public_review(row | {"reviewer_grant_active": False})["state"]
        == "reviewer_no_longer_authorized"
    )
    with pytest.raises(HTTPException):
        h.public_review(row | {"image_sha256": "b" * 64})


def test_tissue_rules():
    import tissue_samples_api as t

    sample = {
        "sample_id": uuid4(),
        "collection_event_id": uuid4(),
        "barcode": "LEAF-001",
        "specimen_type": "leaf",
        "collected_at": NOW - timedelta(hours=2),
        "collection_note": "two leaves bagged",
    }
    assert t.collection_refusal(t.TissueSampleIn(**sample), NOW)[0] is None
    naive = sample | {"collected_at": datetime(2026, 11, 13, 10, 0)}
    assert (
        t.collection_refusal(t.TissueSampleIn(**naive), NOW)[0]
        == "scout_tissue_collection_timezone_required"
    )
    old = sample | {"collected_at": NOW - timedelta(days=400)}
    assert (
        t.collection_refusal(t.TissueSampleIn(**old), NOW)[0]
        == "scout_tissue_collection_time_out_of_range"
    )
    same = sample | {"collection_event_id": sample["sample_id"]}
    assert t.collection_refusal(t.TissueSampleIn(**same), NOW)[0] == "scout_tissue_ids_must_differ"
    assert (
        t.custody_transition_refusal("collected", "received")
        == "scout_tissue_illegal_custody_transition"
    )
    assert t.custody_transition_refusal("handed_over", "received") is None
    assert t.custody_transition_refusal("disposed", "handed_over") is not None
    custody = t.CustodyEventIn(
        event_id=uuid4(), action="handed_over", previous_event_id=uuid4(), note="to the courier"
    )
    assert t.custody_refusal(custody)[0] == "scout_tissue_recipient_mismatch"


def test_treatment_rules():
    import treatment_review_api as tr

    def ev(**kw):
        base = {
            "event_id": EVENT,
            "action": "propose",
            "plan_sha256": "e" * 64,
            "source_review_event_id": uuid4(),
            "reason": "x" * 25,
        }
        return tr.TreatmentEventIn(**(base | kw))

    assert tr.treatment_refusal(ev())[0] is None
    assert (
        tr.treatment_refusal(ev(previous_event_id=PREVIOUS))[0]
        == "scout_treatment_proposal_proof_required"
    )
    review = ev(
        action="review", plan_sha256=None, source_review_event_id=None, previous_event_id=PREVIOUS
    )
    assert tr.treatment_refusal(review)[0] is None
    assert tr.treatment_head_refusal({"action": "propose", "actor_user_id": 5}, "review", 5) == (
        "scout_treatment_two_person_rule"
    )
    assert tr.treatment_head_refusal({"action": "review", "actor_user_id": 5}, "reject", 6) == (
        "scout_treatment_already_reviewed"
    )
    assert tr.public_treatment(None)["pesticide_application_authorized"] is False


def test_credential_state_needs_every_party_current():
    import credential_status as cs

    row = {
        "event_id": EVENT,
        "action": "attest_registry_check",
        "subject_active": True,
        "subject_role": "expert",
        "attester_active": True,
        "attester_role": "owner",
    }
    assert cs.credential_state(row, unexpired=True)["state"] == "owner_attested_current"
    assert (
        cs.credential_state(row | {"attester_role": "admin"}, unexpired=True)["state"]
        == "owner_attested_current"
    )
    for change in (
        {"attester_role": "manager"},
        {"subject_role": "farmer"},
        {"action": "revoke"},
        {"attester_active": False},
    ):
        assert cs.credential_state(row | change, unexpired=True)["state"] == "not_current"
    assert cs.credential_state(row, unexpired=False)["state"] == "not_current"
    assert cs.credential_state(row, unexpired=True)["issuer_connection_verified"] is False


def test_retention_view_never_authorises_deletion():
    import evidence_retention_api as r

    out = r.retention_view(
        {"event_id": EVENT, "min_retention_days": 365}, {"action": "legal_hold"}, NOW
    )
    assert out["legal_hold"] is True and out["delete_authorized"] is False
    assert out["earliest_disposition_review_at"] == (NOW + timedelta(days=365)).isoformat()
    assert r.retention_view(None, None, NOW)["state"] == "policy_missing_fail_closed"


# ─── the admin API (owner decision: re-homed into scout-ingest) ─────────────


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("SCOUT_MEDIA_GRANTS_ADMIN_ENABLED", "1")
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", TOKEN)
    monkeypatch.delenv("SCOUT_GRANT_ADMIN_DATABASE_URL", raising=False)


def test_admin_identity_is_tenant_owner_only(admin_env, monkeypatch):
    import grants_admin_api as g

    assert g.admin_identity(TOKEN, TENANT, "17", "Owner") == (TENANT, 17, "owner")
    assert g.admin_identity(TOKEN, TENANT, "17", "admin")[2] == "admin"
    for role in ("manager", "platform_admin", "expert", "", None):
        with pytest.raises(HTTPException) as exc:
            g.admin_identity(TOKEN, TENANT, "17", role)
        assert (exc.value.status_code, exc.value.detail) == (
            403,
            "scout_photo_grants_owner_required",
        )
    with pytest.raises(HTTPException) as exc:
        g.admin_identity("wrong", TENANT, "17", "owner")
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        g.admin_identity(TOKEN, TENANT, "user-17", "owner")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        g.admin_identity(TOKEN, TENANT, "17", "owner", governance=True)
    assert (exc.value.status_code, exc.value.detail) == (404, "scout_governance_admin_disabled")
    monkeypatch.setenv("SCOUT_MEDIA_GRANTS_ADMIN_ENABLED", "0")
    with pytest.raises(HTTPException) as exc:
        g.admin_identity(TOKEN, TENANT, "17", "owner")
    assert exc.value.status_code == 404


def test_a_grant_lease_is_finite_aware_and_at_most_90_days():
    import grants_admin_api as g

    assert g.lease_expiry(NOW + timedelta(days=90), NOW) == (NOW + timedelta(days=90)).isoformat()
    for value, code in (
        (NOW + timedelta(days=90, seconds=1), "scout_photo_grant_expiry_must_be_within_90_days"),
        (NOW, "scout_photo_grant_expiry_must_be_within_90_days"),
        (datetime(2026, 12, 1), "scout_photo_grant_expiry_requires_timezone"),
    ):
        with pytest.raises(HTTPException) as exc:
            g.lease_expiry(value, NOW)
        assert exc.value.detail == code


def test_credential_attestation_rules():
    import grants_admin_api as g

    base = {
        "event_id": EVENT,
        "subject_user_id": 9,
        "discipline": "agronomy",
        "action": "attest_registry_check",
        "issuer_code": "YE-MAI",
        "jurisdiction": "YE",
        "license_sha256": "a" * 64,
        "registry_check_ref": "registry-page-2026",
        "expires_at": NOW + timedelta(days=365),
        "reason": "x" * 25,
    }
    assert g.credential_refusal(g.CredentialIn(**base), NOW)[0] is None
    too_long = base | {"expires_at": NOW + timedelta(days=1096)}
    assert (
        g.credential_refusal(g.CredentialIn(**too_long), NOW)[0]
        == "scout_credentials_expiry_out_of_range"
    )
    revoke = {
        "event_id": EVENT,
        "subject_user_id": 9,
        "discipline": "agronomy",
        "action": "revoke",
        "reason": "x" * 25,
    }
    assert (
        g.credential_refusal(g.CredentialIn(**revoke), NOW)[0] == "scout_credentials_invalid_revoke"
    )
    assert g.credential_refusal(
        g.CredentialIn(**revoke | {"previous_event_id": PREVIOUS}), NOW
    ) == (None, None)


def test_scopes_agree_with_the_migrations_and_target_roles():
    import grants_admin_api as g

    assert set(g.SCOPE_TARGET_ROLES) == set(g.SCOPES)
    last = read("migrations/v271_scout_treatment_review_events.sql")
    checked = set(re.findall(r"'(photo\.[a-z_]+)'", last.split("CREATE TABLE")[0]))
    assert checked == set(g.SCOPES)
    assert g.SCOPE_TARGET_ROLES["photo.diagnosis_review"] == {"expert", "agronomist"}
    assert "viewer" not in g.SCOPE_TARGET_ROLES["photo.context"]
    assert "worker" not in g.SCOPE_TARGET_ROLES["photo.context"]  # farmer only (owner decision)


def test_admin_routes_answer_before_the_database(admin_env):
    import grants_admin_api as g

    app = FastAPI()
    app.include_router(g.router)
    client = TestClient(app)
    base = "/internal/scouting-media/admin"
    hdr = {
        "X-Scout-Media-Token": TOKEN,
        "X-Tenant-Id": TENANT,
        "X-User-Id": "17",
        "X-User-Role": "owner",
    }
    issue = {
        "event_id": str(uuid4()),
        "user_id": 18,
        "scope": "photo.read",
        "expires_at": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        "reason": "field visit",
    }
    assert (
        client.post(
            f"{base}/fields/f1/grants", json=issue, headers=hdr | {"X-User-Role": "manager"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/fields/f1/grants", json=issue | {"user_id": 17}, headers=hdr
        ).status_code
        == 403
    )
    res = client.post(f"{base}/fields/f1/grants", json=issue, headers=hdr)
    # Every gate passed: without the dedicated admin DSN the request stops, never falls back.
    assert (
        res.status_code == 503
        and res.json()["detail"] == "scout_photo_grants_admin_db_unconfigured"
    )
    assert client.post(f"{base}/credential-events", json={}, headers=hdr).status_code in (404, 422)


# ─── media routes: flags and role gates before the database ─────────────────


@pytest.fixture
def media(monkeypatch):
    import media_api
    import season_api

    monkeypatch.setattr(season_api, "DATABASE_URL", "")
    monkeypatch.setenv("SCOUT_MEDIA_ENABLED", "1")
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(media_api.blob_store, "S3_BUCKET", "sahool-scout-ingest")
    monkeypatch.setattr(media_api.blob_store, "S3_ENDPOINT", "https://objects.example.org")
    import detection_link_api
    import evidence_retention_api
    import human_review_api
    import lab_link_api
    import tissue_samples_api
    import treatment_review_api

    app = FastAPI()
    for module in (
        media_api,
        detection_link_api,
        lab_link_api,
        human_review_api,
        tissue_samples_api,
        treatment_review_api,
        evidence_retention_api,
    ):
        app.include_router(module.router)
    return TestClient(app)


def _h(role="expert", uid="17"):
    return {
        "X-Scout-Media-Token": TOKEN,
        "X-Tenant-Id": TENANT,
        "X-User-Id": uid,
        "X-User-Role": role,
    }


_PHOTO = "/internal/scouting-media/fields/f1/pins/p1/photo"
_ROUTES = (
    ("SCOUT_MEDIA_DETECTION_LINK_ENABLED", "/detection-link-events", "worker"),
    ("SCOUT_MEDIA_LAB_LINK_ENABLED", "/lab-link-events", "farmer"),
    ("SCOUT_MEDIA_HUMAN_REVIEW_ENABLED", "/human-review-events", "manager"),
    ("SCOUT_MEDIA_TISSUE_SAMPLE_ENABLED", "/tissue-samples", "farmer"),
    ("SCOUT_MEDIA_TREATMENT_REVIEW_ENABLED", "/treatment-review-events", "owner"),
    ("SCOUT_MEDIA_RETENTION_ENABLED", "/retention", "farmer"),
)


@pytest.mark.parametrize(("flag", "suffix", "denied_role"), _ROUTES)
def test_each_ledger_is_404_while_off_and_role_gated_when_on(
    media, monkeypatch, flag, suffix, denied_role
):
    for name in FLAGS:
        monkeypatch.delenv(name, raising=False)
    assert media.get(_PHOTO + suffix, headers=_h()).status_code == 404
    monkeypatch.setenv(flag, "1")
    assert media.get(_PHOTO + suffix, headers=_h(denied_role)).status_code == 403


def test_every_feature_flag_defaults_off():
    env = read(".env.example")
    compose = read("docker-compose.v9.yml")
    for flag in FLAGS:
        assert f"{flag}=0" in env, flag
        assert f"{flag}: ${{{flag}:-0}}" in compose, flag


def test_the_photo_routes_check_the_field_grant_with_the_live_role():
    import media_api

    sql = media_api._FIELD_SCOPE_SQL
    assert "lower(u.role::text)=$5" in sql and "u.active IS TRUE" in sql
    assert (
        "g.revoked_at IS NULL" in sql and "g.expires_at <= g.granted_at + interval '90 days'" in sql
    )
    source = read("services/scout-ingest-service/media_api.py")
    for scope in ("photo.upload", "photo.read", "photo.context", "photo.season_link"):
        assert f'"{scope}"' in source, scope


# ─── schema, ownership, registration, staging gates ─────────────────────────


def test_v272_guard_branches_per_table():
    sql = read("migrations/v272_scout_photo_retention_governance.sql")
    body = sql[sql.index("CREATE OR REPLACE FUNCTION scout_retention_guard") :]
    assert "IF TG_TABLE_NAME='scout_photo_retention_policy_events' THEN" in body
    assert "TG_TABLE_NAME='scout_photo_retention_events' AND NEW.action" not in body
    assert "DROP POLICY IF EXISTS %I ON %I" in sql


def test_every_new_table_is_owned_by_scout_ingest_and_registered():
    import yaml

    tables = yaml.safe_load(read("docs/architecture/db_ownership.yml"))["tables"]
    new = (
        "scout_photo_field_access_grants",
        "scout_photo_grant_audit_events",
        "scout_photo_detection_link_events",
        "scout_photo_lab_link_events",
        "scout_photo_human_review_events",
        "scout_plant_tissue_samples",
        "scout_tissue_custody_events",
        "scout_specialist_credential_events",
        "scout_treatment_review_events",
        "scout_photo_retention_policy_events",
        "scout_photo_retention_events",
    )
    for table in new:
        assert tables[table]["owner"] == "scout-ingest-service", table
        assert tables[table]["writers"] == ["scout-ingest-service"], table
        assert "sahool-platform" not in tables[table]["readers"], table
    manifest = [
        line.strip()
        for line in read("migrations/MANIFEST.txt").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    chain = [f for f in manifest if re.match(r"v2(6[2-9]|7[0-2])_", f)]
    assert [int(f[1:4]) for f in chain] == list(range(262, 273))
    assert manifest.index(chain[-1]) < manifest.index("v240_converge_first_pass_schema.sql")


def test_no_platform_route_or_router_was_added_for_the_photo_admin():
    routers = ROOT / "services" / "sahool-platform" / "api" / "routers"
    assert not (routers / "scout_photo_grants.py").exists()
    assert not (routers / "scout_photo_governance.py").exists()
    nginx = read("nginx/nginx.v9.conf")
    assert "location ^~ /api/v1/scouting-media/ {" in nginx
    assert "proxy_pass http://scout_ingest_backend/internal/scouting-media/;" in nginx


@pytest.mark.parametrize("stage", ["8_catalog", "9_catalog", "10_tenant_rls", "11_catalog"])
def test_staging_gates_refuse_anything_but_an_explicit_staging_run(stage, monkeypatch):
    script = ROOT / "scripts" / "staging" / f"run_scout_photo_stage{stage}_gate.sh"
    assert script.exists()
    assert (
        "password"
        not in script.read_text(encoding="utf-8").split("psql", 1)[-1].lower().split("\n")[0]
    )
    for value in (None, "production"):
        env = {"PATH": "/usr/bin:/bin"}
        if value:
            env["SCOUT_ACCEPTANCE_ENV"] = value
        result = subprocess.run(  # noqa: S603, S607
            ["bash", str(script)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == 64, result.stderr
        assert "REFUSED" in result.stderr


async def test_an_identical_concurrent_request_that_became_the_head_is_a_replay_not_409():
    """The delivery answered 409 here: request B read request A's event as the new head."""
    import evidence_chain

    reads = {"n": 0}

    async def load_existing():  # absent on the first read, A's identical event afterwards
        reads["n"] += 1
        return None if reads["n"] == 1 else {"event_id": EVENT}

    async def read_head():
        return {"event_id": EVENT}

    async def insert():
        raise AssertionError("nothing may be inserted for a replay")

    idem, head = await evidence_chain.append_event(
        event_id=EVENT,
        previous_event_id=None,
        load_existing=load_existing,
        matches=lambda row: True,
        read_head=read_head,
        insert=insert,
        codes=_Codes().codes,
    )
    assert idem is True and head["event_id"] == EVENT
