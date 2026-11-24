"""Independent owner-bridge counterexamples on the real PG/SQLite fixture.

These tests preserve the ordinary owner routes and storage. Failure injection
is explicit: one transport loses its reply after an actual receiver commit,
and two cases corrupt only that test's disposable SQLite aggregate to test
receipt validation. Neither is presented as an ordinary production operation.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest
from test_scouting_verification_bridge_live_pg import _WHY, BridgeLive, asyncpg, run

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"),
]


async def _result_counts(live):
    return tuple(
        [
            await live.admin.fetchval(
                f"SELECT count(*) FROM {table} WHERE tenant_id=$1::uuid", live.tenant
            )
            for table in ("scouting_verification_assessments", "scouting_verification_outbox")
        ]
    )


def test_read_only_farm_grant_role_can_resolve_a_link_without_write_privilege(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            # BridgeLive applies the production bootstrap's post-GRANT REVOKE.
            # Checking column privileges also prevents an UPDATE(column) grant
            # from making FOR SHARE accidentally pass while table UPDATE is false.
            assert live.grant_privileges == {
                "SELECT": True,
                "INSERT": False,
                "UPDATE": False,
                "DELETE": False,
                "TRUNCATE": False,
            }
            async with live.app_connection("reviewer") as conn:
                assert not await conn.fetchval(
                    "SELECT has_any_column_privilege(current_user,"
                    "'public.farm_access_grants','UPDATE')"
                )
                sql = (
                    "SELECT is_active FROM farm_access_grants "
                    "WHERE tenant_id=$1::uuid AND user_id=$2 AND farm_id=$3"
                )
                args = (
                    live.tenant,
                    live.users[(live.tenant, "reviewer")],
                    live.farm,
                )
                assert await conn.fetchval(sql, *args) is True
                # This real PostgreSQL failure documents why row locking must
                # not be implemented by granting FM write access to farm grants.
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with conn.transaction():
                        await conn.fetchval(sql + " FOR SHARE", *args)
                assert await conn.fetchval(sql, *args) is True
            context = await live.context()
            assert context.status_code == 200, context.text
            linked = await live.link()
            assert linked.status_code == 200, linked.text
            assert await _result_counts(live) == (0, 0)

    run(target())


def test_link_replay_cannot_change_the_anomaly_task_in_the_request_path(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            first_task = live.task_a
            linked = await live.link(task=first_task)
            assert linked.status_code == 200, linked.text
            body = dict(live.last_link_body)
            second_task = await live.make_anomaly_task()
            wrong_path = await live.link(task=second_task, body=body)
            exact_replay = await live.link(task=first_task, body=body)
            assert wrong_path.status_code == 409, wrong_path.text
            assert exact_replay.status_code == 200, exact_replay.text
            assert exact_replay.json()["replayed"] is True
            assert exact_replay.json()["link_id"] == linked.json()["link_id"]
            rows = await live.admin.fetch(
                "SELECT anomaly_task_id FROM scouting_verification_links WHERE tenant_id=$1::uuid",
                live.tenant,
            )
            assert [str(row["anomaly_task_id"]) for row in rows] == [first_task]
            assert await _result_counts(live) == (0, 0)

    run(target())


@pytest.mark.parametrize("mismatch", ["unresolved-subfield", "unmapped-season"])
def test_context_refuses_a_scope_without_the_required_owner_mapping(
    monkeypatch, tmp_path, mismatch
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            if mismatch == "unresolved-subfield":
                task = await live.make_anomaly_task(
                    geometry_ref="urn:sahool:geometry:unresolved_sector"
                )
                expected_reason = "subfield_geometry_resolver_required"
            else:
                task = await live.make_anomaly_task(season_id=str(uuid.uuid4()))
                expected_reason = "inspection_season_mismatch"
            response = await live.context(task=task)
            assert response.status_code == 409, response.text
            assert response.json()["detail"] == expected_reason
            assert (
                await live.admin.fetchval(
                    "SELECT count(*) FROM scouting_verification_links WHERE tenant_id=$1::uuid",
                    live.tenant,
                )
                == 0
            )
            assert await _result_counts(live) == (0, 0)

    run(target())


def test_completed_anomaly_and_approved_pin_are_not_a_verification_result(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            approved = await live.approve_inspection()
            assert approved["evidence_approved"] is True
            # An ordinary permitted application UPDATE reaches the existing
            # v277 trigger; this is not a disabled-gate or schema-owner control.
            async with live.app_connection("manager") as conn:
                await conn.execute(
                    "UPDATE field_tasks SET status='completed',completed_at=clock_timestamp() "
                    "WHERE tenant_id=$1::uuid AND task_id=$2::uuid",
                    live.tenant,
                    live.task_a,
                )
            assert (await live.task_record(live.task_a))["status"] == "completed"
            assert await _result_counts(live) == (0, 0)
            anomaly = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert anomaly["status"] == "verification_requested"
            assert "verification_delivery" not in anomaly["payload"]
            assert "verification_result" not in anomaly["payload"]

    run(target())


def test_assessment_requires_the_reviewer_who_approved_this_inspection(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            # A manager has inspection:review and a current farm grant, but did
            # not approve this evidence. Permission alone is not that approval.
            response = await live.assess(name="manager")
            assert response.status_code == 409, response.text
            assert response.json()["detail"] == "current_review_by_this_reviewer_required"
            assert await _result_counts(live) == (0, 0)

    run(target())


def test_site_only_assessment_cannot_confirm_the_whole_anomaly_target(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            linked = await live.link()
            assert linked.status_code == 200, linked.text
            approved = await live.approve_inspection()
            body = {
                "command_id": str(uuid.uuid4()),
                "link_revision": linked.json()["revision"],
                "expected_inspection_revision": approved["revision"],
                "evidence_version": approved["current_evidence"]["version"],
                "verification_result": "confirmed",
                "protocol": "manual-signal-field-check/v1",
                "coverage": "inspection_site_only",
                "observations": "Observation made at this point only",
                "coverage_basis": "Only this inspection site was reached",
                "limitations": "The remainder of the field was not inspected",
                "reason_codes": ["LIMITED_SITE_COVERAGE"],
            }
            refused = await live.assess(body=body)
            assert refused.status_code == 422, refused.text
            assert await _result_counts(live) == (0, 0)
            # The same stated limitation can support an explicit inconclusive
            # assessment, with a fresh command; it is not silently called healthy.
            inconclusive = await live.assess(
                body=body | {"command_id": str(uuid.uuid4()), "verification_result": "inconclusive"}
            )
            assert inconclusive.status_code == 200, inconclusive.text
            assert await _result_counts(live) == (1, 1)
            row = await live.admin.fetchrow(
                "SELECT body_text FROM scouting_verification_outbox WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert json.loads(row["body_text"])["verification_result"] == "inconclusive"

    run(target())


def test_revoked_farm_grant_blocks_dispatch_without_changing_remote_state(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            before = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            # Only the schema owner can write farm grants; this fixture models
            # an actual revocation in that table, not a mocked permission return.
            await live.admin.execute(
                "UPDATE farm_access_grants SET is_active=false,updated_at=clock_timestamp() "
                "WHERE tenant_id=$1::uuid AND user_id=$2 AND farm_id=$3",
                live.tenant,
                live.users[(live.tenant, "reviewer")],
                live.farm,
            )
            response = await live.deliver()
            assert response.status_code == 403, response.text
            assert response.json()["detail"] == "verification_farm_grant_required"
            assert live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant) == before
            row = await live.admin.fetchrow(
                "SELECT state,attempts FROM scouting_verification_outbox WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert (row["state"], row["attempts"]) == ("pending", 0)

    run(target())


def test_reassignment_after_assessment_blocks_delivery_and_preserves_its_body(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            approved = await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            before = await live.admin.fetchrow(
                "SELECT idempotency_key,body_text,body_digest FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            reassign = await live.handoff(
                live.task_b,
                "reassign",
                "manager",
                {
                    "expected_revision": approved["revision"],
                    "assigned_to": int(live.users[(live.tenant, "inspector2")]),
                    "reason": "A new inspection is required",
                },
            )
            assert reassign.status_code == 200, reassign.text
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "blocked"
            assert response.json()["last_error"] == "current_review_by_this_reviewer_required"
            after = await live.admin.fetchrow(
                "SELECT idempotency_key,body_text,body_digest FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert dict(after) == dict(before)
            assert live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)["status"] == (
                "verification_requested"
            )

    run(target())


@pytest.mark.parametrize("cancelled_task", ["anomaly", "inspection"])
def test_cancellation_after_assessment_blocks_a_new_callback(monkeypatch, tmp_path, cancelled_task):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            before = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            task_id = live.task_a if cancelled_task == "anomaly" else live.task_b
            # A real application UPDATE goes through the task owner's active
            # triggers. Cancellation does not fabricate a new inspection review.
            async with live.app_connection("manager") as conn:
                await conn.execute(
                    "UPDATE field_tasks SET status='cancelled' "
                    "WHERE tenant_id=$1::uuid AND task_id=$2::uuid",
                    live.tenant,
                    task_id,
                )
            assert (await live.task_record(task_id))["status"] == "cancelled"
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "blocked"
            reason = (
                "anomaly_scouting_task_not_eligible"
                if cancelled_task == "anomaly"
                else "current_review_by_this_reviewer_required"
            )
            assert response.json()["last_error"] == reason
            assert live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant) == before
            assert await _result_counts(live) == (1, 1)
            row = await live.admin.fetchrow(
                "SELECT receipt FROM scouting_verification_outbox WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert row["receipt"] is None

    run(target())


@pytest.mark.parametrize(
    "after_commit",
    [
        "unchanged",
        "resolved",
        "payload-corrupt",
        "version-regressed",
        "anomaly-cancelled",
        "inspection-cancelled",
    ],
)
def test_lost_reply_reconciles_a_durable_receipt_but_refuses_corruption(
    monkeypatch, tmp_path, after_commit
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fm_verification_client import VerificationRemoteError

            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            actual_complete = live.remote_client.complete
            sends = []

            async def commit_then_lose_reply(*args, **kwargs):
                sends.append((args, kwargs))
                response = await actual_complete(*args, **kwargs)
                assert response["persisted"] is True
                raise VerificationRemoteError("injected_reply_loss_after_actual_commit")

            monkeypatch.setattr(live.remote_client, "complete", commit_then_lose_reply)
            first = await live.deliver()
            assert first.status_code == 200, first.text
            assert first.json()["state"] == "delivery_unknown"
            accepted = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert (accepted["status"], accepted["aggregate_version"]) == ("confirmed", 4)
            before = await live.admin.fetchrow(
                "SELECT idempotency_key,body_text,body_digest FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )

            if after_commit == "resolved":
                live.anomaly_store.transition(
                    live.anomaly_ref,
                    "resolved",
                    expected_version=4,
                    patch={"disposition_reason_codes": ["RESOLVED_AFTER_REVIEW"]},
                    tenant_id=live.tenant,
                )
            elif after_commit.endswith("-cancelled"):
                task_id = live.task_a if after_commit == "anomaly-cancelled" else live.task_b
                async with live.app_connection("manager") as conn:
                    await conn.execute(
                        "UPDATE field_tasks SET status='cancelled' "
                        "WHERE tenant_id=$1::uuid AND task_id=$2::uuid",
                        live.tenant,
                        task_id,
                    )
            elif after_commit in {"payload-corrupt", "version-regressed"}:
                # Corruption injection into this test's isolated SQLite file;
                # not a legal lifecycle operation or a fake database response.
                with sqlite3.connect(live.anomaly_store.path) as conn:
                    if after_commit == "payload-corrupt":
                        payload = accepted["payload"] | {"verification_result": "rejected"}
                        conn.execute(
                            "UPDATE signal_anomalies SET payload_json=? "
                            "WHERE anomaly_ref=? AND tenant_id=?",
                            (json.dumps(payload), live.anomaly_ref, live.tenant),
                        )
                    else:
                        conn.execute(
                            "UPDATE signal_anomalies SET version=3 "
                            "WHERE anomaly_ref=? AND tenant_id=?",
                            (live.anomaly_ref, live.tenant),
                        )
            remote_before_reconcile = live.anomaly_store.get(
                live.anomaly_ref, tenant_id=live.tenant
            )
            second = await live.deliver()
            assert second.status_code == 200, second.text
            expected = (
                "delivery_unknown"
                if "corrupt" in after_commit or "regressed" in after_commit
                else "delivered_review_required"
                if after_commit.endswith("-cancelled")
                else "delivered"
            )
            assert second.json()["state"] == expected, second.text
            assert len(sends) == 1, "reconciliation must not post a second completion"
            assert live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant) == (
                remote_before_reconcile
            )
            after = await live.admin.fetchrow(
                "SELECT idempotency_key,body_text,body_digest FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert dict(after) == dict(before)
            if after_commit.endswith("-cancelled"):
                # The accepted callback remains a historical fact. Cancellation
                # requires review; it cannot turn an accepted receipt into a new
                # pending command or erase that remote acceptance.
                row = await live.admin.fetchrow(
                    "SELECT receipt FROM scouting_verification_outbox WHERE delivery_id=$1::uuid",
                    live.delivery_id,
                )
                receipt = (
                    json.loads(row["receipt"])
                    if isinstance(row["receipt"], str)
                    else row["receipt"]
                )
                assert (
                    receipt["anomaly"]["payload"]["verification_delivery"]
                    == (accepted["payload"]["verification_delivery"])
                )

    run(target())


def test_the_outbox_state_machine_is_enforced_by_the_database(monkeypatch, tmp_path):
    # The application role in a tenant session cannot write a delivery state that the
    # dispatcher never would: no receipt-less "delivered", no reopening a terminal row,
    # no attempt-count rewrite, no "sending" without a lease.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200

            async def refused(sql):
                with pytest.raises(asyncpg.PostgresError) as caught:
                    async with live.app_connection("reviewer") as conn:
                        await conn.execute(sql, live.delivery_id)
                return caught.value.sqlstate

            assert await refused(
                "UPDATE scouting_verification_outbox SET state='delivered' WHERE delivery_id=$1::uuid"
            ) in {"55000", "23514"}
            assert (
                await refused(
                    "UPDATE scouting_verification_outbox SET attempts=7 WHERE delivery_id=$1::uuid"
                )
                == "55000"
            )
            assert (
                await refused(
                    "UPDATE scouting_verification_outbox SET state='sending',attempts=attempts+1 "
                    "WHERE delivery_id=$1::uuid"
                )
                == "23514"
            )
            async with live.app_connection("reviewer") as conn:
                await conn.execute(
                    "UPDATE scouting_verification_outbox SET state='blocked' "
                    "WHERE delivery_id=$1::uuid",
                    live.delivery_id,
                )
            assert (
                await refused(
                    "UPDATE scouting_verification_outbox SET state='pending' WHERE delivery_id=$1::uuid"
                )
                == "55000"
            )
            row = await live.admin.fetchrow(
                "SELECT state, attempts, receipt FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert dict(row) == {"state": "blocked", "attempts": 0, "receipt": None}

    run(target())


def test_an_unconfigured_key_id_refuses_before_claiming_the_delivery(monkeypatch, tmp_path):
    # Without a key id the request cannot be signed: refuse with 503 before the claim, so the
    # row is not left in `sending` and no attempt is counted.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "")
            response = await live.deliver()
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "verification_transport_unconfigured"
            row = await live.admin.fetchrow(
                "SELECT state, attempts, lease_token FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert dict(row) == {"state": "pending", "attempts": 0, "lease_token": None}

    run(target())


def test_the_attempt_cap_ends_in_a_terminal_state_and_the_database_refuses_more(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            # Test-only setup: put the row at the cap without eight real round trips.
            await live.admin.execute("SET session_replication_role = replica")
            await live.admin.execute(
                "UPDATE scouting_verification_outbox SET state='delivery_unknown', attempts=8 "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            await live.admin.execute("SET session_replication_role = origin")
            with pytest.raises(asyncpg.PostgresError) as caught:
                async with live.app_connection("reviewer") as conn:
                    await conn.execute(
                        "UPDATE scouting_verification_outbox SET state='sending', attempts=9, "
                        "lease_token=gen_random_uuid(), lease_until=clock_timestamp()+interval '1 minute' "
                        "WHERE delivery_id=$1::uuid",
                        live.delivery_id,
                    )
            assert caught.value.sqlstate == "55000"
            before = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "delivery_exhausted"
            again = await live.deliver()
            assert again.json()["state"] == "delivery_exhausted"
            after = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert after["aggregate_version"] == before["aggregate_version"]
            row = await live.admin.fetchrow(
                "SELECT state, attempts, lease_token FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            assert dict(row) == {"state": "delivery_exhausted", "attempts": 8, "lease_token": None}

    run(target())
