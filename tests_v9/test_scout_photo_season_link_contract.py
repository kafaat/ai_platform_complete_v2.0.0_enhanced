"""SCOUT-PHOTO context and explicit season links (owner phases 4-5; v262), unit contract.

No database and no object store:

* the pure rules in ``media_api`` (request refusal, idempotent-retry match, the season part of
  the context, the role sets);
* the HTTP gates that must answer **before** any database contact. ``DATABASE_URL`` is empty
  (fixture ``media`` of ``test_scout_photo_evidence_contract``), so a request that reached the
  database answers 503 ``scout_media_database_unavailable`` instead of the code tested;
* the v262 schema, its registration and the grants.

The chain itself (accepted season only, same tenant and field, predecessor fence, revocation,
idempotent and concurrent retries, RLS, immutability, the v246 task pointer) runs against a real
PostgreSQL in ``services/scout-ingest-service/tests/test_media_live.py`` (``-m integration``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from test_scout_photo_evidence_contract import (  # noqa: F401 — ``media`` is a fixture
    headers,
    media,
    path,
    read,
)

pytestmark = pytest.mark.unit

EVENT = UUID("11111111-1111-4111-8111-111111111111")
PREVIOUS = UUID("22222222-2222-4222-8222-222222222222")
SEASON = UUID("33333333-3333-4333-8333-333333333333")


def _event(**overrides):
    import media_api

    body = {"event_id": EVENT, "action": "link", "season_id": SEASON}
    body.update(overrides)
    return media_api.PhotoSeasonLinkEventIn(**body)


def _json(**overrides):
    body = {"event_id": str(EVENT), "action": "link", "season_id": str(SEASON)}
    body.update(overrides)
    return body


# ─── pure rules ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"action": "accept"}, "scout_photo_link_action_invalid"),
        ({"season_id": None}, "scout_photo_season_id_required"),
        ({"action": "revoke", "reason": "wrong season"}, "scout_photo_revoke_must_not_name_season"),
        ({"action": "revoke", "season_id": None}, "scout_photo_link_revision_reason_required"),
        ({"previous_event_id": PREVIOUS}, "scout_photo_link_revision_reason_required"),
        (
            {"previous_event_id": PREVIOUS, "reason": "   "},
            "scout_photo_link_revision_reason_required",
        ),
        ({"reason": "x" * 2001}, "scout_photo_link_reason_too_long"),
        ({"previous_event_id": EVENT, "reason": "self"}, "scout_photo_link_self_reference"),
    ],
)
def test_a_malformed_link_request_is_refused_with_a_stable_code(overrides, code):
    import media_api

    assert media_api.season_link_refusal(_event(**overrides)) == (code, None)


def test_a_valid_request_passes_with_its_reason_trimmed():
    import media_api

    assert media_api.season_link_refusal(_event()) == (None, None)
    revision = _event(previous_event_id=PREVIOUS, reason="  corrected season  ")
    assert media_api.season_link_refusal(revision) == (None, "corrected season")
    revoke = _event(action="revoke", season_id=None, previous_event_id=PREVIOUS, reason="wrong")
    assert media_api.season_link_refusal(revoke) == (None, "wrong")


def test_a_retry_matches_only_when_every_immutable_field_agrees():
    import media_api

    data = _event(previous_event_id=PREVIOUS, reason="corrected")
    row = {
        "action": "link",
        "actor_id": "person-a",
        "season_id": SEASON,
        "previous_event_id": PREVIOUS,
        "reason": "corrected",
    }
    assert media_api.season_event_matches(row, data, "corrected", "person-a")
    for key, other in (
        ("action", "revoke"),
        ("actor_id", "person-b"),
        ("season_id", uuid4()),
        ("previous_event_id", None),
        ("reason", "other"),
    ):
        assert not media_api.season_event_matches(
            {**row, key: other}, data, "corrected", "person-a"
        )


def test_the_season_context_names_authority_only_for_a_human_accepted_season():
    import media_api

    now = datetime.now(UTC)
    link = {
        "event_id": EVENT,
        "action": "link",
        "season_id": SEASON,
        "trust_status": "accepted",
        "accepted_by": "reviewer",
        "accepted_at": now,
    }
    assert media_api.season_context(None) == {"state": "explicit_link_required", "season_id": None}
    assert media_api.season_context(link) == {
        "state": "linked_accepted",
        "season_id": str(SEASON),
        "link_event_id": str(EVENT),
        "link_proof": "scout_photo_season_link_events:v262",
    }
    for change in ({"trust_status": "quarantined"}, {"accepted_by": None}, {"accepted_at": None}):
        ctx = media_api.season_context({**link, **change})
        assert ctx["state"] == "linked_not_accepted" and "link_proof" not in ctx
    revoked = media_api.season_context({**link, "action": "revoke", "season_id": None})
    assert revoked == {"state": "revoked", "season_id": None, "link_event_id": str(EVENT)}


def test_role_sets_are_narrower_than_upload():
    import media_api

    assert media_api.CONTEXT_ROLES == media_api.WRITE_ROLES - {"worker"}
    assert media_api.SEASON_LINK_ROLES == {"owner", "admin", "manager", "agronomist", "expert"}
    assert media_api.SEASON_LINK_ROLES < media_api.CONTEXT_ROLES < media_api.READ_ROLES
    assert "viewer" not in media_api.CONTEXT_ROLES


def test_the_season_link_flag_is_off_by_default(monkeypatch):
    import media_api

    monkeypatch.delenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", raising=False)
    assert media_api.season_bridge_enabled() is False
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "true")
    assert media_api.season_bridge_enabled() is True


# ─── HTTP gates before any database contact ─────────────────────────────────


def test_season_link_routes_are_404_while_the_flag_is_off(media, monkeypatch):
    client, uploads, _ = media
    monkeypatch.delenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", raising=False)
    url = path() + "/season-link-events"
    assert client.post(url, json=_json(), headers=headers(role="expert")).status_code == 404
    assert client.get(url, headers=headers(role="expert")).status_code == 404
    assert not uploads


@pytest.mark.parametrize("role", ["farmer", "worker", "viewer", "platform_admin"])
def test_roles_outside_the_link_set_cannot_link_or_read_the_chain(media, monkeypatch, role):
    client, _, _ = media
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    url = path() + "/season-link-events"
    assert client.post(url, json=_json(), headers=headers(role=role)).status_code == 403
    assert client.get(url, headers=headers(role=role)).status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin", "manager", "agronomist", "expert"])
def test_link_roles_pass_the_gates_and_reach_the_database(media, monkeypatch, role):
    client, _, _ = media
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    res = client.post(path() + "/season-link-events", json=_json(), headers=headers(role=role))
    assert res.status_code == 503, res.text
    assert res.json()["detail"] == "scout_media_database_unavailable"


def test_a_malformed_link_is_422_before_the_database(media, monkeypatch):
    client, _, _ = media
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    url = path() + "/season-link-events"
    expert = headers(role="expert")
    for body in (_json(action="accept"), _json(season_id=None), _json(event_id="not-a-uuid")):
        assert client.post(url, json=body, headers=expert).status_code == 422
    assert (
        client.post(
            path(pin="bad:pin") + "/season-link-events", json=_json(), headers=expert
        ).status_code
        == 422
    )


@pytest.mark.parametrize("role", ["worker", "viewer", "platform_admin"])
def test_the_context_is_not_for_workers_or_viewers(media, role):
    client, _, _ = media
    assert client.get(path() + "/context", headers=headers(role=role)).status_code == 403


def test_the_context_reaches_the_database_for_context_roles(media):
    client, _, _ = media
    for role in ("owner", "admin", "manager", "agronomist", "expert", "farmer"):
        res = client.get(path() + "/context", headers=headers(role=role))
        assert res.status_code == 503 and res.json()["detail"] == "scout_media_database_unavailable"


def test_an_upload_ref_from_another_bucket_or_key_is_never_committed(media, monkeypatch):
    """Owner phase 4: a store adapter answering with another ref must not reach the row."""
    import hashlib

    from test_scout_photo_evidence_contract import picture

    client, _, mod = media
    reached_db: list = []

    async def read_row(*args):
        return None

    async def insert_row(*args):
        reached_db.append(args)
        raise AssertionError("the immutable row must not be written")

    monkeypatch.setattr(mod, "_read_row", read_row)
    monkeypatch.setattr(mod, "_insert_row", insert_row)
    monkeypatch.setattr(
        mod.blob_store, "upload_bytes", lambda key, data, ctype: f"s3://other-bucket/{key}"
    )
    data = picture()
    res = client.post(
        path(),
        content=data,
        headers={
            **headers(),
            "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
            "Content-Type": "image/jpeg",
        },
    )
    assert res.status_code == 503 and res.json()["detail"] == "scout_media_store_unavailable"
    assert not reached_db


# ─── schema, registration, grants ───────────────────────────────────────────


def test_v262_schema_is_fenced_append_only_and_tenant_bound():
    sql = read("migrations/v262_scout_photo_season_link_events.sql")
    assert (
        "FOREIGN KEY (tenant_id, field_id, pin_id)\n        REFERENCES scout_photo_evidence" in sql
    )
    assert "FOREIGN KEY (season_id, tenant_id, field_id)\n        REFERENCES season_records" in sql
    assert "CONSTRAINT scout_photo_season_event_successor_uq UNIQUE (previous_event_id)" in sql
    assert "WHERE previous_event_id IS NULL" in sql  # one root per photo
    assert "BEFORE UPDATE OR DELETE ON scout_photo_season_link_events" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.current_tenant', true)" in sql


def test_v262_is_registered_after_v260_and_before_v240_v206():
    manifest = [
        line.strip()
        for line in read("migrations/MANIFEST.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    at = manifest.index("v262_scout_photo_season_link_events.sql")
    assert manifest.index("v260_scout_photo_evidence.sql") < at
    assert manifest.index("v201_season_records.sql") < at
    assert (
        at
        < manifest.index("v240_converge_first_pass_schema.sql")
        < manifest.index("v206_rls_final_hardening.sql")
    )
    runner = re.findall(r"^\\i migrations/(\S+)$", read("scripts_v9/run_migrations.sql"), re.M)
    assert (
        runner.index("v262_scout_photo_season_link_events.sql")
        == runner.index("v260_scout_photo_evidence.sql") + 1
    )


@pytest.mark.parametrize(
    "script", ["migrations/bootstrap_postgres.sh", "migrations/apply_in_compose.sh"]
)
def test_ingest_gets_insert_only_links_and_column_select_on_field_tasks(script):
    src = read(script)
    assert "GRANT SELECT, INSERT ON scout_photo_season_link_events TO sahool_ingest;" in src
    assert (
        "REVOKE UPDATE, DELETE, TRUNCATE ON scout_photo_season_link_events FROM sahool_ingest;"
        in src
    )
    assert (
        "GRANT SELECT (tenant_id, field_id, source_scouting_pin_id, task_id, status)\n"
        "      ON field_tasks TO sahool_ingest;"
    ) in src
    assert not re.search(
        r"GRANT [A-Z, ]*(INSERT|UPDATE|DELETE)[A-Z, ]* ON field_tasks TO sahool_ingest", src
    )


def test_ownership_and_flag_wiring():
    import yaml

    tables = yaml.safe_load(read("docs/architecture/db_ownership.yml"))["tables"]
    links = tables["scout_photo_season_link_events"]
    assert links["owner"] == "scout-ingest-service" and links["writers"] == ["scout-ingest-service"]
    assert "scout-ingest-service" in tables["field_tasks"]["readers"]
    assert tables["field_tasks"]["owner"] == "field-management-service"
    assert "SCOUT_MEDIA_SEASON_LINK_ENABLED=0" in read(".env.example")
    assert "SCOUT_MEDIA_SEASON_LINK_ENABLED: ${SCOUT_MEDIA_SEASON_LINK_ENABLED:-0}" in read(
        "docker-compose.v9.yml"
    )
