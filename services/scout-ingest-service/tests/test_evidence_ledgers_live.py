"""Live PostgreSQL proof for scout photo phases 7-11 (v264-v272), all owned by scout-ingest.

Drives the real routers on a database with the full MANIFEST applied: the media routes run as
the NOBYPASSRLS ``sahool_ingest`` role (grants copied from bootstrap_postgres.sh by the
``test_media_live`` fixture), the admin API as ``sahool_scout_grant_admin`` provisioned by
``migrations/helpers/provision_scout_photo_grant_admin.psql`` (run with psql, as the bootstrap does).

  ①  admin API: tenant-owner gate (role claim, live users.role, self-issue), audit-first idempotency,
      90-day lease, target-role compatibility, revoke; the issued grant opens the media route and the
      revocation closes it
  ②  detection link: same image SHA-256, attested provenance, same field; context; revoke
  ③  lab link: eligible soil/water sample of the same field only
  ④  credentials (owner attests, never self) and human review (credential + grant required in SQL)
  ⑤  plant tissue sample with its collection event in one transaction; custody transitions
  ⑥  treatment plan: two-person rule, credential and live review basis
  ⑦  retention: minimum never lowered, hold/release, no disposition before the minimum
  ⑧  FORCE RLS and append-only on every new table under the NOBYPASSRLS role

``-m integration`` only; skips without TEST_ADMIN_URL unless CI_INTEGRATION_REQUIRED=1.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from test_media_live import (  # noqa: F401 — ``live`` is a fixture
    _A,
    _B,
    _FIELD,
    ADMIN_URL,
    USERS,
    _as,
    _client,
    _hdr,
    _path,
    _picture,
    _skip_or_fail,
    grant,
    live,
)

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.integration

_PIN_LEDGER = "pin-a-ledger"
_ADMIN_PW = "grant-admin-test-pw"  # noqa: S105 — test value
_HELPER = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "migrations",
        "helpers",
        "provision_scout_photo_grant_admin.psql",
    )
)
_FLAGS = (
    "SCOUT_MEDIA_GRANTS_ADMIN_ENABLED",
    "SCOUT_MEDIA_GOVERNANCE_ADMIN_ENABLED",
    "SCOUT_MEDIA_DETECTION_LINK_ENABLED",
    "SCOUT_MEDIA_LAB_LINK_ENABLED",
    "SCOUT_MEDIA_HUMAN_REVIEW_ENABLED",
    "SCOUT_MEDIA_TISSUE_SAMPLE_ENABLED",
    "SCOUT_MEDIA_CREDENTIAL_ENFORCEMENT_ENABLED",
    "SCOUT_MEDIA_TREATMENT_REVIEW_ENABLED",
    "SCOUT_MEDIA_RETENTION_ENABLED",
)
_NEW_TABLES = (
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


def _provision_admin_role() -> str:
    psql = shutil.which("psql")
    if not psql:
        _skip_or_fail("psql not on PATH (the admin role is provisioned by the .psql helper)")
    result = subprocess.run(  # noqa: S603 — fixed argv, test database
        [
            psql,
            ADMIN_URL,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            "admin_enabled=true",
            "-v",
            "app_role=sahool_app",
            "-v",
            "jobs_role=sahool_jobs",
            "-v",
            "dbname=" + ADMIN_URL.rsplit("/", 1)[1],
            "-f",
            _HELPER,
        ],
        env={**os.environ, "SCOUT_GRANT_ADMIN_DB_PASSWORD": _ADMIN_PW},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return f"postgresql://sahool_scout_grant_admin:{_ADMIN_PW}@" + ADMIN_URL.split("@", 1)[1]


@pytest.fixture
async def ledgers(live, monkeypatch):
    app, s3, ingest_url = live
    admin_url = _provision_admin_role()
    monkeypatch.setenv("SCOUT_GRANT_ADMIN_DATABASE_URL", admin_url)
    for flag in _FLAGS:
        monkeypatch.setenv(flag, "1")
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        await admin.execute(
            "INSERT INTO scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category) "
            "VALUES ($1, $2::uuid, $3, 15.3, 44.2, 'pest') ON CONFLICT DO NOTHING",
            _PIN_LEDGER,
            _A,
            _FIELD,
        )
        await admin.execute(
            "INSERT INTO field_boundaries (field_id, field_name, tenant_id) VALUES ($1, $1, "
            "$2::uuid) ON CONFLICT (field_id) DO NOTHING",
            _FIELD,
            _A,
        )
        for scope in (
            "photo.detection_link",
            "photo.lab_link",
            "photo.diagnosis_review",
            "photo.tissue_sample",
            "photo.treatment_review",
        ):
            await grant(admin, "expert", scope)
        for scope in ("photo.diagnosis_review", "photo.treatment_review", "photo.upload"):
            await grant(admin, "expert2", scope)
        await grant(admin, "worker", "photo.tissue_sample")
    finally:
        await admin.close()
    import detection_link_api
    import evidence_retention_api
    import grants_admin_api
    import human_review_api
    import lab_link_api
    import tissue_samples_api
    import treatment_review_api

    for module in (
        detection_link_api,
        lab_link_api,
        human_review_api,
        tissue_samples_api,
        treatment_review_api,
        evidence_retention_api,
        grants_admin_api,
    ):
        app.include_router(module.router)
    async with await _client(app) as c:
        data = _picture(color=(33, 99, 160))
        res = await c.post(_path(_PIN_LEDGER), content=data, headers=_hdr(data=data))
        assert res.status_code == 200, res.text
    return app, s3, ingest_url, hashlib.sha256(data).hexdigest()


def _json(user="expert", tenant=None):
    return {
        k: v
        for k, v in _hdr(user=user, tenant=tenant).items()
        if k not in ("Content-Type", "X-Content-SHA256")
    }


def _admin(path: str) -> str:
    return "/internal/scouting-media/admin" + path


def _ev(name: str) -> str:
    return _path(_PIN_LEDGER) + "/" + name


def _lease(days=30) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


async def _attest(c, subject: str, discipline: str, previous=None, action="attest_registry_check"):
    body = {
        "event_id": str(uuid.uuid4()),
        "subject_user_id": USERS[subject]["id"],
        "discipline": discipline,
        "action": action,
        "previous_event_id": previous,
        "reason": "manual registry check of the national license list",
    }
    if action == "attest_registry_check":
        body |= {
            "issuer_code": "YE-MAI",
            "jurisdiction": "YE",
            "license_sha256": hashlib.sha256(subject.encode()).hexdigest(),
            "registry_check_ref": "registry-page-2026-11-13",
            "expires_at": _lease(365),
        }
    return await c.post(_admin("/credential-events"), json=body, headers=_json("owner"))


async def test_admin_api_is_tenant_owner_scoped_audited_and_closes_the_media_route(ledgers):
    app, *_ = ledgers
    issue = {
        "event_id": str(uuid.uuid4()),
        "user_id": USERS["nogrant"]["id"],
        "scope": "photo.read",
        "expires_at": _lease(),
        "reason": "field visit this month",
    }
    url = _admin(f"/fields/{_FIELD}/grants")
    async with await _client(app) as c:
        assert (await c.get(_path(_PIN_LEDGER), headers=_hdr(user="nogrant"))).status_code == 403
        for user in ("manager", "expert", "inspector"):  # not a tenant-owner alias
            res = await c.post(url, json=issue, headers=_json(user))
            assert res.status_code == 403 and res.json()["detail"] == (
                "scout_photo_grants_owner_required"
            )
        # The trusted claim 'admin' for a user whose live users.role is 'owner': refused.
        forged = await c.post(url, json=issue, headers={**_json("owner"), "X-User-Role": "admin"})
        assert forged.status_code == 403
        assert forged.json()["detail"] == "scout_photo_grants_owner_inactive_or_changed"
        assert (
            await c.post(url, json=issue, headers={**_json("owner"), "X-Scout-Media-Token": "x"})
        ).status_code == 401
        self_issue = {**issue, "user_id": USERS["owner"]["id"], "event_id": str(uuid.uuid4())}
        assert (await c.post(url, json=self_issue, headers=_json("owner"))).status_code == 403
        too_long = {**issue, "expires_at": _lease(91), "event_id": str(uuid.uuid4())}
        assert (await c.post(url, json=too_long, headers=_json("owner"))).status_code == 422
        wrong_role = {**issue, "scope": "photo.diagnosis_review", "event_id": str(uuid.uuid4())}
        res = await c.post(url, json=wrong_role, headers=_json("owner"))
        assert res.status_code == 403 and res.json()["detail"] == (
            "scout_photo_grants_target_role_incompatible"
        )
        first = await c.post(url, json=issue, headers=_json("owner"))
        assert first.status_code == 201, first.text
        assert first.json()["idempotent"] is False
        replay = await c.post(url, json=issue, headers=_json("owner"))
        assert replay.status_code == 201 and replay.json()["idempotent"] is True
        assert replay.json()["grant_id"] == first.json()["grant_id"]
        reused = await c.post(
            url, json={**issue, "reason": "another reason here"}, headers=_json("owner")
        )
        assert reused.status_code == 409
        # 'admin' is the other tenant-owner alias: it may administer too.
        listing = await c.get(url, headers=_json("admin"))
        assert listing.status_code == 200
        assert first.json()["grant_id"] in {g["grant_id"] for g in listing.json()["grants"]}
        assert {e["action"] for e in listing.json()["events"]} >= {"issue"}
        assert (await c.get(_path(_PIN_LEDGER), headers=_hdr(user="nogrant"))).status_code == 200

        revoke = {"event_id": str(uuid.uuid4()), "reason": "visit finished early"}
        rurl = f"{url}/{first.json()['grant_id']}/revoke"
        assert (await c.post(rurl, json=revoke, headers=_json("owner"))).json()[
            "idempotent"
        ] is False
        assert (await c.post(rurl, json=revoke, headers=_json("owner"))).json()[
            "idempotent"
        ] is True
        assert (await c.get(_path(_PIN_LEDGER), headers=_hdr(user="nogrant"))).status_code == 403
        # Another tenant's owner cannot see or touch tenant A's field.
        assert (await c.get(url, headers=_json("owner_b"))).status_code == 404
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        role = await admin.fetchrow(
            "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
            "WHERE rolname='sahool_scout_grant_admin'"
        )
        assert (role["rolsuper"], role["rolbypassrls"], role["rolcanlogin"]) == (False, False, True)
        audited = await admin.fetchval(
            "SELECT count(*) FROM scout_photo_grant_audit_events WHERE target_user_id=$1",
            USERS["nogrant"]["id"],
        )
        assert audited == 2  # one issue, one revoke
    finally:
        await admin.close()


async def test_admin_api_is_off_by_default(ledgers, monkeypatch):
    app, *_ = ledgers
    monkeypatch.setenv("SCOUT_MEDIA_GRANTS_ADMIN_ENABLED", "0")
    async with await _client(app) as c:
        res = await c.get(_admin(f"/fields/{_FIELD}/grants"), headers=_json("owner"))
    assert res.status_code == 404


async def test_detection_link_needs_the_same_image_digest_and_attested_provenance(ledgers):
    app, _, _, sha = ledgers
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        result_id = await admin.fetchval(
            "INSERT INTO edge_results (field_id, tenant_id, result_type, result_data) "
            "VALUES ($1, $2::uuid, 'pest_detect', '{}'::jsonb) RETURNING id",
            _FIELD,
            _A,
        )
        provenance = {}
        for key, digest, attestation in (
            ("match", sha, "attested"),
            ("other", "c" * 64, "attested"),
        ):
            provenance[key] = await admin.fetchval(
                "INSERT INTO detection_provenance (tenant_id, edge_result_id, detection_index, "
                "score, threshold, model_id, model_version, artifact_sha256, input_sha256, "
                "attestation) VALUES ($1::uuid, $2, $3, 0.9, 0.5, 'leaf-net', '1.0', $4, $5, $6) "
                "RETURNING id",
                _A,
                result_id,
                len(provenance),
                "d" * 64,
                digest,
                attestation,
            )
    finally:
        await admin.close()
    url = _ev("detection-link-events")
    async with await _client(app) as c:
        wrong = await c.post(
            url,
            json={
                "event_id": str(uuid.uuid4()),
                "action": "link",
                "detection_provenance_id": provenance["other"],
            },
            headers=_json(),
        )
        assert wrong.status_code == 422 and wrong.json()["detail"] == (
            "scout_photo_detection_image_proof_missing"
        )
        link = {
            "event_id": str(uuid.uuid4()),
            "action": "link",
            "detection_provenance_id": provenance["match"],
        }
        res = await c.post(url, json=link, headers=_json())
        assert res.status_code == 200, res.text
        current = res.json()["current"]
        assert current["state"] == "linked_model_provenance_unreviewed"
        assert current["input_sha256"] == sha and current["human_diagnosis_approved"] is False
        assert (await c.post(url, json=link, headers=_json())).json()["idempotent"] is True
        ctx = (await c.get(_path(_PIN_LEDGER) + "/context", headers=_json())).json()
        assert ctx["detection"]["link_event_id"] == link["event_id"]
        assert ctx["consistency"]["relational_snapshot"] == "repeatable_read"
        assert (await c.get(url, headers=_json("inspector"))).status_code == 403  # role gate
        revoke = {
            "event_id": str(uuid.uuid4()),
            "action": "revoke",
            "previous_event_id": link["event_id"],
            "reason": "wrong leaf",
        }
        assert (await c.post(url, json=revoke, headers=_json())).json()["current"][
            "state"
        ] == "revoked"
        history = (await c.get(url, headers=_json())).json()
        assert [e["action"] for e in history["events"]] == ["link", "revoke"]


async def test_lab_link_accepts_only_an_eligible_sample_of_the_same_field(ledgers):
    app, *_ = ledgers
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        for sample, status, field, tenant in (
            ("lab-live-ok", "sampled", _FIELD, _A),
            ("lab-live-requested", "requested", _FIELD, _A),
            ("lab-live-other-field", "sampled", "field-other", _A),
        ):
            await admin.execute(
                "INSERT INTO lab_samples (sample_id, tenant_id, field_id, kind, latitude, "
                "longitude, status, created_by) VALUES ($1, $2::uuid, $3, 'water', 15.3, 44.2, "
                "$4, 'live') ON CONFLICT (sample_id) DO NOTHING",
                sample,
                tenant,
                field,
                status,
            )
    finally:
        await admin.close()
    url = _ev("lab-link-events")
    async with await _client(app) as c:
        for sample in ("lab-live-requested", "lab-live-other-field", "lab-live-missing"):
            res = await c.post(
                url,
                json={"event_id": str(uuid.uuid4()), "action": "link", "sample_id": sample},
                headers=_json(),
            )
            assert res.status_code == 422, (sample, res.text)
        link = {"event_id": str(uuid.uuid4()), "action": "link", "sample_id": "lab-live-ok"}
        res = await c.post(url, json=link, headers=_json())
        assert res.status_code == 200, res.text
        assert res.json()["current"]["state"] == "linked_contextual_soil_water"
        assert res.json()["current"]["plant_tissue_sample"] is False
        ctx = (await c.get(_path(_PIN_LEDGER) + "/context", headers=_json())).json()
        assert ctx["lab_sample"]["sample_id"] == "lab-live-ok"


async def test_credentials_gate_the_human_review_in_sql_and_in_the_api(ledgers):
    app, _, _, sha = ledgers
    url = _ev("human-review-events")
    review = {
        "event_id": str(uuid.uuid4()),
        "action": "review",
        "assessment": "suspected",
        "diagnosis_code": "fungal.leaf_spot",
        "review_method": "photo_review",
        "reason": "concentric brown lesions on older leaves",
    }
    async with await _client(app) as c:
        # Without a current owner-attested credential the review is refused.
        res = await c.post(url, json=review, headers=_json())
        assert res.status_code == 403, res.text
        # The owner attests; a specialist may not attest themselves, a manager may not attest.
        assert (await _attest(c, "expert", "plant_pathology")).status_code == 200
        self_body = {
            "event_id": str(uuid.uuid4()),
            "subject_user_id": USERS["owner"]["id"],
            "discipline": "agronomy",
            "action": "attest_registry_check",
            "issuer_code": "YE-MAI",
            "jurisdiction": "YE",
            "license_sha256": "a" * 64,
            "registry_check_ref": "registry-page-2026-11-13",
            "expires_at": _lease(365),
            "reason": "manual registry check of the national license list",
        }
        assert (
            await c.post(_admin("/credential-events"), json=self_body, headers=_json("owner"))
        ).status_code == 403
        assert (
            await c.post(_admin("/credential-events"), json=self_body, headers=_json("manager"))
        ).status_code == 403
        res = await c.post(url, json=review, headers=_json())
        assert res.status_code == 200, res.text
        current = res.json()["current"]
        assert current["state"] == "human_assessment_recorded"
        assert current["image_sha256"] == sha and current["human_diagnosis_approved"] is False
        assert (await c.post(url, json=review, headers=_json())).json()["idempotent"] is True
        ctx = (await c.get(_path(_PIN_LEDGER) + "/context", headers=_json())).json()
        assert ctx["human_review"]["credential"]["state"] == "owner_attested_current"
        assert ctx["human_review"]["credential"]["issuer_connection_verified"] is False
        # expert2 (agronomist) holds the grant but no credential: refused.
        retract_by_other = {
            "event_id": str(uuid.uuid4()),
            "action": "review",
            "assessment": "inconclusive",
            "review_method": "photo_review",
            "previous_event_id": review["event_id"],
            "reason": "second opinion without a credential",
        }
        assert (
            await c.post(url, json=retract_by_other, headers=_json("expert2"))
        ).status_code == 403


async def _review_and_credentials(c) -> str:
    for user in ("expert", "expert2"):
        assert (await _attest(c, user, "crop_protection")).status_code == 200
    assert (await _attest(c, "expert", "plant_pathology")).status_code == 200
    review = {
        "event_id": str(uuid.uuid4()),
        "action": "review",
        "assessment": "suspected",
        "diagnosis_code": "fungal.rust",
        "review_method": "field_exam",
        "reason": "orange pustules seen on the field visit",
    }
    res = await c.post(_ev("human-review-events"), json=review, headers=_json())
    assert res.status_code == 200, res.text
    return review["event_id"]


async def test_treatment_plan_review_is_two_person_and_never_a_spray_permit(ledgers):
    app, *_ = ledgers
    url = _ev("treatment-review-events")
    async with await _client(app) as c:
        source = await _review_and_credentials(c)
        proposal = {
            "event_id": str(uuid.uuid4()),
            "action": "propose",
            "plan_sha256": "e" * 64,
            "source_review_event_id": source,
            "reason": "plan drafted from the confirmed field suspicion",
        }
        res = await c.post(url, json=proposal, headers=_json())
        assert res.status_code == 200, res.text
        assert res.json()["pesticide_application_authorized"] is False
        own = {
            "event_id": str(uuid.uuid4()),
            "action": "review",
            "previous_event_id": proposal["event_id"],
            "reason": "the proposer reviewing their own plan",
        }
        res = await c.post(url, json=own, headers=_json())
        assert res.status_code == 403 and res.json()["detail"] == "scout_treatment_two_person_rule"
        second = {**own, "event_id": str(uuid.uuid4()), "reason": "second specialist read the plan"}
        res = await c.post(url, json=second, headers=_json("expert2"))
        assert res.status_code == 200, res.text
        assert res.json()["current"]["state"] == "reviewed_for_manual_consideration"
        ctx = (await c.get(_path(_PIN_LEDGER) + "/context", headers=_json())).json()
        assert ctx["treatment_review"]["all_signers_credential_current"] is True
        assert ctx["automatic_pesticide_action_authorized"] is False


async def test_tissue_sample_and_custody_chain(ledgers):
    app, *_ = ledgers
    url = _ev("tissue-samples")
    sample = {
        "sample_id": str(uuid.uuid4()),
        "collection_event_id": str(uuid.uuid4()),
        "barcode": "LEAF-" + uuid.uuid4().hex[:8].upper(),
        "specimen_type": "leaf",
        "collected_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "collection_note": "two symptomatic leaves bagged",
    }
    async with await _client(app) as c:
        assert (await c.post(url, json=sample, headers=_json("inspector"))).status_code == 403
        res = await c.post(url, json=sample, headers=_json("worker"))
        assert res.status_code == 201, res.text
        assert res.json()["idempotent"] is False
        again = await c.post(url, json=sample, headers=_json("worker"))
        assert again.status_code == 201 and again.json()["idempotent"] is True
        custody = f"{url}/{sample['sample_id']}/custody-events"
        received_first = {
            "event_id": str(uuid.uuid4()),
            "action": "received",
            "previous_event_id": sample["collection_event_id"],
            "recipient_ref": "lab-sanaa",
            "note": "lab received the bag directly",
        }
        res = await c.post(custody, json=received_first, headers=_json("worker"))
        assert res.status_code == 409 and res.json()["detail"] == (
            "scout_tissue_illegal_custody_transition"
        )
        handed = {
            **received_first,
            "event_id": str(uuid.uuid4()),
            "action": "handed_over",
            "note": "handed to the courier",
        }
        assert (await c.post(custody, json=handed, headers=_json("worker"))).status_code == 200
        received = {
            **received_first,
            "event_id": str(uuid.uuid4()),
            "previous_event_id": handed["event_id"],
        }
        assert (await c.post(custody, json=received, headers=_json("expert"))).status_code == 200
        listing = (await c.get(url, headers=_json("worker"))).json()
        assert listing["samples"][0]["custody_state"] == "received"
        assert listing["laboratory_result_approved"] is False


async def test_retention_minimum_holds_and_no_early_disposition(ledgers):
    app, *_ = ledgers
    events = _admin(f"/fields/{_FIELD}/pins/{_PIN_LEDGER}/retention-events")
    reason = "statutory evidence retention for plant protection"
    async with await _client(app) as c:
        policy = {"event_id": str(uuid.uuid4()), "min_retention_days": 730, "reason": reason}
        res = await c.post(_admin("/retention-policy-events"), json=policy, headers=_json("owner"))
        assert res.status_code == 200, res.text
        lower = {
            "event_id": str(uuid.uuid4()),
            "previous_event_id": policy["event_id"],
            "min_retention_days": 365,
            "reason": reason,
        }
        res = await c.post(_admin("/retention-policy-events"), json=lower, headers=_json("owner"))
        assert (
            res.status_code == 422
            and res.json()["detail"] == "scout_retention_minimum_cannot_decrease"
        )
        early = {"event_id": str(uuid.uuid4()), "action": "request_disposition", "reason": reason}
        res = await c.post(events, json=early, headers=_json("owner"))
        assert (
            res.status_code == 409
            and res.json()["detail"] == "scout_retention_minimum_not_satisfied"
        )
        hold = {"event_id": str(uuid.uuid4()), "action": "legal_hold", "reason": reason}
        assert (await c.post(events, json=hold, headers=_json("owner"))).status_code == 200
        release = {
            "event_id": str(uuid.uuid4()),
            "action": "release_hold",
            "previous_event_id": hold["event_id"],
            "reason": reason,
        }
        assert (await c.post(events, json=release, headers=_json("owner"))).status_code == 200
        assert (await c.post(events, json=hold, headers=_json("manager"))).status_code == 403
        view = (await c.get(_path(_PIN_LEDGER) + "/retention", headers=_json())).json()
        assert view["min_retention_days"] == 730 and view["legal_hold"] is False
        assert view["delete_authorized"] is False and view["physical_deletion_supported"] is False


async def test_new_tables_are_forced_rls_and_append_only_under_nobypassrls(ledgers):
    app, _, ingest_url, _ = ledgers
    async with await _client(app) as c:
        await _review_and_credentials(c)
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        for table in _NEW_TABLES:
            forced = await admin.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
                table,
            )
            assert (forced["relrowsecurity"], forced["relforcerowsecurity"]) == (True, True), table
        # Even the migration owner cannot rewrite a ledger row (the guards refuse, 55000).
        for table in ("scout_photo_human_review_events", "scout_specialist_credential_events"):
            with pytest.raises(asyncpg.PostgresError) as exc:
                await admin.execute(f"UPDATE {table} SET reason=reason")  # noqa: S608
            assert exc.value.sqlstate == "55000"
    finally:
        await admin.close()
    a = await _as(ingest_url, _A)
    try:
        assert await a.fetchval("SELECT count(*) FROM scout_photo_human_review_events") >= 1
        for table in _NEW_TABLES:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await a.execute(f"DELETE FROM {table}")  # noqa: S608
        for table in ("scout_specialist_credential_events", "scout_photo_retention_policy_events"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):  # admin API only
                await a.execute(
                    f"INSERT INTO {table} (event_id) VALUES (gen_random_uuid())"  # noqa: S608
                )
    finally:
        await a.close()
    b = await _as(ingest_url, _B)
    try:
        for table in _NEW_TABLES[2:]:
            if table != "scout_photo_grant_audit_events":
                count = await b.fetchval(  # noqa: S608
                    f"SELECT count(*) FROM {table} WHERE tenant_id=$1::uuid", _A
                )
                assert count == 0, table
    finally:
        await b.close()
