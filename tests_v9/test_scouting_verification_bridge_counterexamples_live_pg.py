"""Independent owner-bridge counterexamples on the real PG/SQLite fixture.

These tests preserve the ordinary owner routes and storage. Failure injection
is explicit: one transport loses its reply after an actual receiver commit,
and two cases corrupt only that test's disposable SQLite aggregate to test
receipt validation. Neither is presented as an ordinary production operation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from test_scouting_verification_bridge_live_pg import _WHY, ROOT, BridgeLive, asyncpg, run

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


def test_the_assessment_is_written_by_the_assignee_after_someone_else_approved(
    monkeypatch, tmp_path
):
    # Owner decision 1 (2026-11-24): the inspection's current assignee writes the assessment,
    # on the exact evidence version another person approved. The approver, a manager and a
    # different field user each hold a farm grant, and none of them may write it.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            for name in ("reviewer", "manager", "inspector2"):
                response = await live.assess(name=name)
                assert response.status_code == 409, (name, response.text)
                assert response.json()["detail"] == (
                    "current_approved_inspection_by_its_assignee_required"
                )
            assert await _result_counts(live) == (0, 0)
            accepted = await live.assess(name="inspector")
            assert accepted.status_code == 200, accepted.text
            assert await _result_counts(live) == (1, 1)
            row = await live.admin.fetchrow(
                "SELECT reviewer, reviewer_role FROM scouting_verification_assessments "
                "WHERE assessment_id=$1::uuid",
                live.assessment_id,
            )
            assert (row["reviewer"], row["reviewer_role"]) == (
                live.users[(live.tenant, "inspector")],
                "worker",
            )
            # The delivery belongs to the assessor too; the approver cannot send it.
            refused = await live.deliver(name="reviewer")
            assert refused.status_code == 403, refused.text
            assert refused.json()["detail"] == "delivery_requires_the_original_assessor"

    run(target())


def test_the_assignee_reads_what_they_need_and_nothing_of_anyone_else(monkeypatch, tmp_path):
    # Under owner decision 1 the writer may be a worker without inspection:review. They read the
    # context of their own inspection (with the link id the assessment path needs), their own
    # assessment and its delivery; another field user with a farm grant reads none of these.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            context = await live.context(name="inspector")
            assert context.status_code == 200, context.text
            assert context.json()["link_id"] == live.link_id
            refused = "verification_context_requires_the_inspection_assignee"
            other = await live.context(name="inspector2")
            assert other.status_code == 403, other.text
            assert other.json()["detail"] == refused
            # Hospital SF-C: being assigned to B does not open the context of an anomaly task
            # that is not linked to B. The owner is not even called for it.
            unlinked = await live.make_anomaly_task()
            calls = []
            original = live.remote_client.context

            async def counted(*args, **kwargs):
                calls.append(args)
                return await original(*args, **kwargs)

            live.mp.setattr(live.remote_client, "context", counted)
            cross = await live.context(task=unlinked, name="inspector")
            assert cross.status_code == 403, cross.text
            assert cross.json()["detail"] == refused
            assert calls == []
            live.mp.setattr(live.remote_client, "context", original)
            assert (await live.assess()).status_code == 200
            base = f"/internal/field-tasks/fields/{live.field}"
            paths = (
                f"{base}/verification-assessments/{live.assessment_id}",
                f"{base}/verification-deliveries/{live.delivery_id}",
            )
            for path in paths:
                for name, status in (("inspector", 200), ("reviewer", 200), ("inspector2", 404)):
                    response = await live.fm.get(path, headers=live.headers(name))
                    assert response.status_code == status, (path, name, response.text)
            # A cancelled inspection opens no context, even while still assigned.
            async with live.app_connection("manager") as conn:
                await conn.execute(
                    "UPDATE field_tasks SET status='cancelled' "
                    "WHERE tenant_id=$1::uuid AND task_id=$2::uuid",
                    live.tenant,
                    live.task_b,
                )
            cancelled = await live.context(name="inspector")
            assert cancelled.status_code == 403, cancelled.text

    run(target())


def test_the_database_refuses_an_assessment_written_by_the_approver(monkeypatch, tmp_path):
    # The same rule holds below the application: the v289 trigger refuses an assessment row
    # whose writer is the approver rather than the inspection's assignee.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            assert (await live.link()).status_code == 200
            await live.approve_inspection()
            assert (await live.assess()).status_code == 200
            row = await live.admin.fetchrow(
                "SELECT * FROM scouting_verification_assessments WHERE assessment_id=$1::uuid",
                live.assessment_id,
            )
            approver = live.users[(live.tenant, "reviewer")]
            columns = [c for c in row.keys() if c not in {"assessment_id", "command_id"}]
            forged = {"reviewer": approver, "reviewer_role": "agronomist"}
            values = [forged.get(c, row[c]) for c in columns]
            with pytest.raises(asyncpg.PostgresError) as caught:
                async with live.app_connection("reviewer") as conn:
                    await conn.execute(
                        "INSERT INTO scouting_verification_assessments "
                        f"(assessment_id,command_id,{','.join(columns)}) VALUES "
                        f"(gen_random_uuid(),gen_random_uuid(),"
                        f"{','.join(f'${i + 1}' for i in range(len(columns)))})",
                        *values,
                    )
            assert caught.value.sqlstate == "23514"
            assert "verification_assessment_requires_current_reviewed_evidence" in str(caught.value)

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
                live.users[(live.tenant, "inspector")],
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
            assert response.json()["last_error"] == (
                "current_approved_inspection_by_its_assignee_required"
            )
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
                else "current_approved_inspection_by_its_assignee_required"
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
            if "corrupt" in after_commit or "regressed" in after_commit:
                # The owner refuses to vouch for a corrupted record. That read now happens before
                # the claim, so it answers 503 and the row stays delivery_unknown, untouched: no
                # attempt is used and nothing is sent.
                assert second.status_code == 503, second.text
                assert second.json()["detail"] == (
                    "verification_context_unavailable:"
                    "verification_remote_status:503:verification_delivery_receipt_inconsistent"
                )
                row = await live.admin.fetchrow(
                    "SELECT state, attempts FROM scouting_verification_outbox "
                    "WHERE delivery_id=$1::uuid",
                    live.delivery_id,
                )
                assert (row["state"], row["attempts"]) == ("delivery_unknown", 1)
            else:
                assert second.status_code == 200, second.text
                expected = (
                    "delivered_review_required"
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
            # An unsent delivery is blocked only when its link revision was superseded.
            assert (
                await refused(
                    "UPDATE scouting_verification_outbox SET state='blocked' WHERE delivery_id=$1::uuid"
                )
                == "55000"
            )
            # Test-only setup: a terminal row, then no reopening it.
            await live.admin.execute("SET session_replication_role = replica")
            await live.admin.execute(
                "UPDATE scouting_verification_outbox SET state='blocked' WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            await live.admin.execute("SET session_replication_role = origin")
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


async def _ready(live):
    assert (await live.link()).status_code == 200
    await live.approve_inspection()
    assert (await live.assess()).status_code == 200


async def _row(live):
    return dict(
        await live.admin.fetchrow(
            "SELECT state, attempts, lease_token, last_error FROM scouting_verification_outbox "
            "WHERE delivery_id=$1::uuid",
            live.delivery_id,
        )
    )


def test_a_malformed_key_id_refuses_before_claiming_the_delivery(monkeypatch, tmp_path):
    # S1: a key id the assertion cannot carry (':' is its field separator) used to pass the
    # pre-claim check, then failed while signing after the claim had committed, leaving the
    # row in `sending` until its lease expired and burning attempts with nothing sent.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            monkeypatch.setenv("VEGETATION_VERIFICATION_TENANT_ASSERTION_KEY_ID", "a:b")
            response = await live.deliver()
            assert response.status_code == 503, response.text
            assert response.json()["detail"] == "verification_transport_unconfigured"
            row = await _row(live)
            assert (row["state"], row["attempts"], row["lease_token"]) == ("pending", 0, None)

    run(target())


def test_an_unexpected_error_after_the_claim_settles_the_row_instead_of_stranding_it(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)

            async def broken(*_args, **_kwargs):
                raise RuntimeError("injected failure after the claim")

            # The context read now happens before the claim; the send is what follows it.
            monkeypatch.setattr(live.remote_client, "complete", broken)
            response = await live.deliver()
            assert response.status_code == 200, response.text
            row = await _row(live)
            assert row == {
                "state": "delivery_unknown",
                "attempts": 1,
                "lease_token": None,
                "last_error": "verification_dispatch_failed:RuntimeError",
            }

    run(target())


def test_a_receiver_switched_off_is_refused_without_using_up_attempts(monkeypatch, tmp_path):
    # S2: one rollout mistake (sender on, receiver off) must not exhaust the delivery into a
    # dead end. The refusal applied nothing, so its attempt is refunded and the row stays open.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "0")
            for _ in range(10):
                response = await live.deliver()
                assert response.status_code == 200, response.text
                assert response.json()["state"] == "refused"
            row = await _row(live)
            assert (row["state"], row["attempts"], row["lease_token"]) == ("refused", 0, None)
            assert (
                row["last_error"] == "verification_remote_status:404:verification_bridge_disabled"
            )
            before = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert before["status"] != "confirmed"
            monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "1")
            response = await live.deliver()
            assert response.json()["state"] == "delivered", response.text
            assert (await _row(live))["attempts"] == 1

    run(target())


def test_an_owner_conflict_is_a_terminal_rejection_with_its_reason(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            actual_complete = live.remote_client.complete
            sends = []

            async def owner_moves_between_read_and_write(*args, **kwargs):
                # Failure injection into this test's isolated SQLite file: the anomaly's version
                # moves after the dispatcher's context read, so the real receiver's
                # compare-and-set answers 409.
                with sqlite3.connect(live.anomaly_store.path) as conn:
                    conn.execute(
                        "UPDATE signal_anomalies SET version=version+1 "
                        "WHERE anomaly_ref=? AND tenant_id=?",
                        (live.anomaly_ref, live.tenant),
                    )
                sends.append(1)
                return await actual_complete(*args, **kwargs)

            monkeypatch.setattr(live.remote_client, "complete", owner_moves_between_read_and_write)
            response = await live.deliver()
            assert response.status_code == 200, response.text
            row = await _row(live)
            assert (row["state"], row["attempts"], row["lease_token"]) == ("rejected", 1, None)
            assert row["last_error"].startswith("verification_remote_status:409:"), row
            again = await live.deliver()
            assert again.json()["state"] == "rejected"
            assert len(sends) == 1, "a rejected delivery is never sent again"

    run(target())


def test_an_exhausted_delivery_reconciles_a_receipt_without_sending_again(monkeypatch, tmp_path):
    # The operator path out of delivery_exhausted: a read-only check against the owner.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fm_verification_client import VerificationRemoteError

            await _ready(live)
            actual_complete = live.remote_client.complete
            sends = []

            async def commit_then_lose_reply(*args, **kwargs):
                sends.append(1)
                await actual_complete(*args, **kwargs)
                raise VerificationRemoteError("injected_reply_loss_after_actual_commit")

            monkeypatch.setattr(live.remote_client, "complete", commit_then_lose_reply)
            assert (await live.deliver()).json()["state"] == "delivery_unknown"
            # Test-only setup: the row reached the cap through unknown outcomes.
            await live.admin.execute("SET session_replication_role = replica")
            await live.admin.execute(
                "UPDATE scouting_verification_outbox SET state='delivery_exhausted', attempts=8 "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )
            await live.admin.execute("SET session_replication_role = origin")
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "delivered", response.text
            assert len(sends) == 1, "reconciling an exhausted delivery must not post again"
            row = await _row(live)
            assert (row["attempts"], row["lease_token"]) == (8, None)

    run(target())


def test_the_database_fences_the_lease_and_binds_the_receipt_to_the_row(monkeypatch, tmp_path):
    # N1: leaving `sending` needs the transaction to name the live lease, and "delivered" needs a
    # receipt carrying this row's idempotency key and request digest. This checks the lease and
    # the binding, not the writer's identity (any session of the tenant can read the token).
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            lease = str(uuid.uuid4())
            async with live.app_connection("reviewer") as conn:
                await conn.execute(
                    "UPDATE scouting_verification_outbox SET state='sending',attempts=attempts+1,"
                    "lease_token=$2::uuid,lease_until=clock_timestamp()+interval '2 minutes' "
                    "WHERE delivery_id=$1::uuid",
                    live.delivery_id,
                    lease,
                )
            key, digest = await live.admin.fetchrow(
                "SELECT idempotency_key, btrim(body_digest) FROM scouting_verification_outbox "
                "WHERE delivery_id=$1::uuid",
                live.delivery_id,
            )

            async def settle(state, *, with_lease, receipt=None):
                async with live.app_connection("reviewer") as conn:
                    if with_lease:
                        await conn.execute(
                            "SELECT set_config('app.verification_lease', $1, true)", with_lease
                        )
                    await conn.execute(
                        "UPDATE scouting_verification_outbox SET state=$2,receipt=$3::jsonb,"
                        "lease_token=NULL,lease_until=NULL WHERE delivery_id=$1::uuid",
                        live.delivery_id,
                        state,
                        json.dumps(receipt) if receipt is not None else None,
                    )

            async def sqlstate(*args, **kwargs):
                with pytest.raises(asyncpg.PostgresError) as caught:
                    await settle(*args, **kwargs)
                return caught.value.sqlstate

            bound = {"verification_delivery": {"idempotency_key": key, "request_digest": digest}}
            forged = {
                "verification_delivery": {"idempotency_key": "other", "request_digest": digest}
            }
            assert await sqlstate("delivery_unknown", with_lease=None) == "55000"
            assert await sqlstate("delivered", with_lease=None, receipt=bound) == "55000"
            assert (
                await sqlstate("delivered", with_lease=str(uuid.uuid4()), receipt=bound) == "55000"
            )
            assert await sqlstate("delivered", with_lease=lease, receipt=forged) == "23514"
            assert await sqlstate("delivered", with_lease=lease, receipt={"x": 1}) == "23514"
            await settle("delivered", with_lease=lease, receipt=bound)
            assert (await _row(live))["state"] == "delivered"

    run(target())


def _fail_once(live, monkeypatch, state, exc):
    """Make the first attempt to record ``state`` fail, as a storage blip would."""
    actual = live.fm_verification.finish_delivery
    failed = []

    async def finish(caller, field_id, delivery, lease, wanted, **kwargs):
        if wanted == state and not failed:
            failed.append(wanted)
            raise exc
        return await actual(caller, field_id, delivery, lease, wanted, **kwargs)

    monkeypatch.setattr(live.fm_verification, "finish_delivery", finish)
    return failed


def test_a_storage_blip_while_recording_an_accepted_delivery_is_never_blocked(
    monkeypatch, tmp_path
):
    # SF-2: the owner accepted the result; failing to record that locally must leave the
    # outcome unknown (reconcilable), never terminal `blocked` (which would allow relinking).
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fastapi import HTTPException

            await _ready(live)
            failed = _fail_once(
                live,
                monkeypatch,
                "delivered",
                HTTPException(503, "field task database unavailable"),
            )
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert failed == ["delivered"]
            row = await _row(live)
            assert (row["state"], row["lease_token"]) == ("delivery_unknown", None)
            assert row["last_error"] == "verification_settle_failed:delivered:HTTPException"
            accepted = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert accepted["status"] == "confirmed"
            again = await live.deliver()
            assert again.json()["state"] == "delivered", again.text

    run(target())


def test_local_storage_unavailable_before_the_post_is_unknown_not_blocked(monkeypatch, tmp_path):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fastapi import HTTPException

            await _ready(live)

            async def storage_down(*_args, **_kwargs):
                raise HTTPException(503, "field task database unavailable")

            monkeypatch.setattr(live.fm_verification, "revalidate_delivery", storage_down)
            response = await live.deliver()
            assert response.status_code == 200, response.text
            row = await _row(live)
            assert row["state"] == "delivery_unknown", row
            assert row["last_error"] == "verification_local_storage:field task database unavailable"

    run(target())


def test_a_failure_while_recording_a_refusal_still_settles_the_row(monkeypatch, tmp_path):
    # SF-1: every outcome is recorded through one settle step with a delivery_unknown fallback.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "0")
            _fail_once(live, monkeypatch, "refused", RuntimeError("injected"))
            response = await live.deliver()
            assert response.status_code == 200, response.text
            row = await _row(live)
            assert row == {
                "state": "delivery_unknown",
                "attempts": 1,
                "lease_token": None,
                "last_error": "verification_settle_failed:refused:RuntimeError",
            }

    run(target())


def test_failed_context_reads_never_use_up_the_delivery(monkeypatch, tmp_path):
    # Devin on #1598: each dispatch counted an attempt before reading the owner's context, so
    # eight read timeouts exhausted a row that was never sent; reconcile never sends and
    # relinking refuses an exhausted row, so it stayed stuck after the owner recovered.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fm_verification_client import VerificationRemoteError

            await _ready(live)
            original = live.remote_client.context

            async def owner_down(*_args, **_kwargs):
                raise VerificationRemoteError("verification_remote_unreachable")

            monkeypatch.setattr(live.remote_client, "context", owner_down)
            for _ in range(10):
                response = await live.deliver()
                assert response.status_code == 503, response.text
                assert response.json()["detail"] == (
                    "verification_context_unavailable:verification_remote_unreachable"
                )
            row = await _row(live)
            assert (row["state"], row["attempts"], row["lease_token"]) == ("pending", 0, None)
            monkeypatch.setattr(live.remote_client, "context", original)
            response = await live.deliver()
            assert response.status_code == 200, response.text
            assert response.json()["state"] == "delivered", response.text
            assert (await _row(live))["attempts"] == 1
            accepted = live.anomaly_store.get(live.anomaly_ref, tenant_id=live.tenant)
            assert accepted["status"] == "confirmed"

    run(target())


_INITIAL_DELIVERY_STATE = {
    "state": "pending",
    "attempts": 0,
    "lease_token": None,
    "lease_until": None,
    "last_error": None,
    "receipt": None,
}
_INITIAL_DELIVERY_LEASE = {"lease_token": uuid.UUID(int=1), "lease_until": "future"}
_V289_INSERT_WITNESSES = {
    "delivered_without_an_attempt": {"state": "delivered", "receipt": "{}"},
    "exhausted_without_an_attempt": {"state": "delivery_exhausted"},
    "sending_beyond_the_attempt_cap": {
        "state": "sending",
        "attempts": 9,
        **_INITIAL_DELIVERY_LEASE,
    },
}


async def _initial_delivery_source(live):
    """Retain a real reviewed assessment for isolated INSERT boundary checks.

    The API creates assessment and outbox atomically. Only this fixture's schema
    owner removes its outbox afterward; this is deliberate test setup, not a
    claim that an API caller can leave an assessment without its delivery.
    """
    await _ready(live)
    source = dict(
        await live.admin.fetchrow(
            "SELECT delivery_id,tenant_id,field_id,assessment_id,idempotency_key,"
            "body_text,body_digest FROM scouting_verification_outbox "
            "WHERE tenant_id=$1::uuid AND delivery_id=$2::uuid",
            live.tenant,
            live.delivery_id,
        )
    )
    # SET LOCAL restores origin before any measured application INSERT, even if
    # the narrowly scoped fixture deletion fails and its transaction rolls back.
    async with live.admin.transaction():
        await live.admin.execute("SET LOCAL session_replication_role=replica")
        assert (
            await live.admin.execute(
                "DELETE FROM scouting_verification_outbox "
                "WHERE tenant_id=$1::uuid AND delivery_id=$2::uuid",
                live.tenant,
                live.delivery_id,
            )
            == "DELETE 1"
        )
    assert await live.admin.fetchval("SHOW session_replication_role") == "origin"
    assert await _result_counts(live) == (1, 0)
    return source


async def _insert_initial_delivery(conn, source, initial=None):
    # Check the effective database identity for every measured INSERT, including
    # the negative control's SET LOCAL ROLE inside the DDL transaction.
    flags = await conn.fetchrow(
        "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
    )
    assert tuple(flags) == (False, False)
    assert await conn.fetchval("SHOW session_replication_role") == "origin"
    args = tuple(
        source[column]
        for column in (
            "delivery_id",
            "tenant_id",
            "field_id",
            "assessment_id",
            "idempotency_key",
            "body_text",
            "body_digest",
        )
    )
    sql = (
        "INSERT INTO scouting_verification_outbox "
        "(delivery_id,tenant_id,field_id,assessment_id,idempotency_key,body_text,body_digest"
    )
    if initial is None:
        # These are precisely the seven columns supplied by the ordinary writer.
        sql += ") VALUES ($1,$2,$3,$4,$5,$6,$7)"
    else:
        values = _INITIAL_DELIVERY_STATE | initial
        if values["lease_until"] == "future":
            values["lease_until"] = datetime.now(UTC) + timedelta(minutes=2)
        sql += (
            ",state,attempts,lease_token,lease_until,last_error,receipt) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)"
        )
        args += tuple(values[column] for column in _INITIAL_DELIVERY_STATE)
    return dict(
        await conn.fetchrow(
            sql + " RETURNING state,attempts,lease_token,lease_until,last_error,receipt::text",
            *args,
        )
    )


@pytest.mark.parametrize("initial", [None, {}], ids=["writer_defaults", "explicit_pending"])
def test_initial_delivery_accepts_only_the_clean_pending_row(monkeypatch, tmp_path, initial):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            source = await _initial_delivery_source(live)
            async with live.app_connection("inspector") as conn:
                assert (
                    await _insert_initial_delivery(conn, source, initial) == _INITIAL_DELIVERY_STATE
                )
            assert await _result_counts(live) == (1, 1)
            delivered = await live.deliver()
            assert delivered.status_code == 200, delivered.text
            assert delivered.json()["state"] == "delivered", delivered.text
            assert (await _row(live))["attempts"] == 1

    run(target())


def test_a_refused_read_after_an_unknown_send_keeps_the_uncertainty(monkeypatch, tmp_path):
    # A refusal on the read may not overwrite delivery_unknown: an earlier POST may have been
    # applied, and `refused` would let relinking block it. The row is left exactly as it was.
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            from fm_verification_client import VerificationRemoteError

            await _ready(live)
            actual_complete = live.remote_client.complete

            async def lose_reply(*args, **kwargs):
                raise VerificationRemoteError("injected_reply_loss_before_commit")

            monkeypatch.setattr(live.remote_client, "complete", lose_reply)
            assert (await live.deliver()).json()["state"] == "delivery_unknown"
            before = await _row(live)
            monkeypatch.setattr(live.remote_client, "complete", actual_complete)
            monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "0")
            response = await live.deliver()
            assert response.status_code == 503, response.text
            assert response.json()["detail"].startswith("verification_context_unavailable:")
            assert await _row(live) == before
            monkeypatch.setenv("VEGETATION_VERIFICATION_BRIDGE_ENABLED", "1")
            response = await live.deliver()
            assert response.json()["state"] == "delivered", response.text
            assert (await _row(live))["attempts"] == 2

    run(target())


@pytest.mark.parametrize(
    "initial",
    [
        *(pytest.param(value, id=name) for name, value in _V289_INSERT_WITNESSES.items()),
        pytest.param({"state": "sending", "attempts": 1, **_INITIAL_DELIVERY_LEASE}, id="sending"),
        pytest.param({"state": "delivery_unknown"}, id="delivery_unknown"),
        pytest.param({"state": "blocked"}, id="blocked"),
        pytest.param({"state": "delivered_review_required", "receipt": "{}"}, id="review_required"),
        pytest.param({"state": "refused"}, id="refused"),
        pytest.param({"state": "rejected"}, id="rejected"),
        pytest.param({"state": None}, id="null_state"),
        pytest.param({"attempts": 1}, id="pending_with_attempt"),
        pytest.param({"attempts": None}, id="null_attempts"),
        pytest.param({"lease_token": uuid.UUID(int=1)}, id="pending_with_lease_token"),
        pytest.param({"lease_until": "future"}, id="pending_with_lease_until"),
        pytest.param(_INITIAL_DELIVERY_LEASE, id="pending_with_both_lease_fields"),
        pytest.param({"receipt": "{}"}, id="pending_with_receipt"),
        pytest.param({"receipt": "null"}, id="json_null_is_not_sql_null"),
        pytest.param({"last_error": ""}, id="empty_error_is_not_null"),
        pytest.param({"last_error": "prior_attempt"}, id="pending_with_error"),
    ],
)
def test_initial_delivery_rejects_a_preclaimed_or_precompleted_row(monkeypatch, tmp_path, initial):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            source = await _initial_delivery_source(live)
            with pytest.raises(asyncpg.CheckViolationError) as caught:
                async with live.app_connection("inspector") as conn:
                    await _insert_initial_delivery(conn, source, initial)
            assert caught.value.sqlstate == "23514"
            assert caught.value.message == "verification_delivery_initial_state_invalid"
            assert await _result_counts(live) == (1, 0)
            # Same identity, assessment and body: only the lifecycle fields
            # change. This rules out an unrelated FK/RLS/content rejection.
            async with live.app_connection("inspector") as conn:
                assert await _insert_initial_delivery(conn, source, {}) == _INITIAL_DELIVERY_STATE
            assert await _result_counts(live) == (1, 1)

    run(target())


@pytest.mark.parametrize("change", ["other_tenant", "assessment_body", "evidence_binding"])
def test_initial_delivery_keeps_the_tenant_and_reviewed_content_guards(
    monkeypatch, tmp_path, change
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            source = await _initial_delivery_source(live)
            invalid = dict(source)
            if change != "other_tenant":
                body = json.loads(source["body_text"])
                if change == "assessment_body":
                    body["expected_version"] += 1
                else:
                    body["evidence"][0]["content_hash"] = "0" * 64
                invalid["body_text"] = json.dumps(body)
                invalid["body_digest"] = hashlib.sha256(invalid["body_text"].encode()).hexdigest()
            with pytest.raises(asyncpg.CheckViolationError) as caught:
                async with live.app_connection("inspector") as conn:
                    if change == "other_tenant":
                        await conn.execute(
                            "SELECT set_config('app.current_tenant',$1,true)", live.other_tenant
                        )
                        assert (
                            await conn.fetchval(
                                "SELECT count(*) FROM scouting_verification_assessments "
                                "WHERE assessment_id=$1",
                                source["assessment_id"],
                            )
                            == 0
                        )
                    await _insert_initial_delivery(conn, invalid, {})
            assert caught.value.sqlstate == "23514"
            # With another tenant's context the existing INSERT trigger cannot
            # see the reviewed assessment. It refuses before the RLS WITH CHECK.
            expected = (
                "verification_delivery_evidence_binding_invalid"
                if change == "evidence_binding"
                else "verification_delivery_does_not_match_reviewed_assessment"
            )
            assert caught.value.message == expected
            assert await _result_counts(live) == (1, 0)
            async with live.app_connection("inspector") as conn:
                assert await _insert_initial_delivery(conn, source, {}) == _INITIAL_DELIVERY_STATE

    run(target())


async def _outbox_guard_definitions(conn):
    rows = await conn.fetch(
        "SELECT tgname,pg_get_triggerdef(oid),tgenabled,pg_get_functiondef(tgfoid) "
        "FROM pg_trigger WHERE tgrelid='public.scouting_verification_outbox'::regclass "
        "AND NOT tgisinternal"
    )
    return {row[0]: tuple(row[1:]) for row in rows}


def test_initial_delivery_guard_alone_refuses_the_three_v289_insert_witnesses(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            source = await _initial_delivery_source(live)
            guard = "scouting_verification_delivery_initial_guard"
            before = await _outbox_guard_definitions(live.admin)
            assert guard in before
            role = (await live._app_role()).replace('"', '""')
            transaction = live.admin.transaction()
            await transaction.start()
            try:
                await live.admin.execute(
                    "DROP TRIGGER scouting_verification_delivery_initial_guard "
                    "ON public.scouting_verification_outbox"
                )
                assert await _outbox_guard_definitions(live.admin) == {
                    name: definition for name, definition in before.items() if name != guard
                }
                # DROP TRIGGER holds a table lock until rollback. Using the
                # actual restricted role in this transaction avoids a blocked
                # second connection; no measured INSERT runs as the owner.
                await live.admin.execute(f'SET LOCAL ROLE "{role}"')
                await live.admin.execute(
                    "SELECT set_config('app.current_tenant',$1,true)", live.tenant
                )
                for initial in _V289_INSERT_WITNESSES.values():
                    savepoint = live.admin.transaction()
                    await savepoint.start()
                    try:
                        row = await _insert_initial_delivery(live.admin, source, initial)
                        assert row["state"] == initial["state"]
                        assert row["attempts"] == initial.get("attempts", 0)
                        assert row["receipt"] == initial.get("receipt")
                        assert (
                            await live.admin.fetchval(
                                "SELECT count(*) FROM scouting_verification_outbox "
                                "WHERE delivery_id=$1",
                                source["delivery_id"],
                            )
                            == 1
                        )
                    finally:
                        await savepoint.rollback()
            finally:
                await transaction.rollback()
            assert await _outbox_guard_definitions(live.admin) == before
            assert await _result_counts(live) == (1, 0)
            for initial in _V289_INSERT_WITNESSES.values():
                with pytest.raises(asyncpg.CheckViolationError) as caught:
                    async with live.app_connection("inspector") as conn:
                        await _insert_initial_delivery(conn, source, initial)
                assert caught.value.sqlstate == "23514"
                assert caught.value.message == "verification_delivery_initial_state_invalid"
            assert await _result_counts(live) == (1, 0)

    run(target())


def test_dispatch_reveals_a_finished_delivery_only_to_its_assessor(monkeypatch, tmp_path):
    # Devin on #1598: dispatch returned a terminal delivery before checking the caller wrote the
    # assessment, so another field user saw the state, receipt and error that GET hides (404).
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            done = await live.deliver()
            assert done.json()["state"] == "delivered", done.text
            calls = []
            original = live.remote_client.context

            async def counted(*args, **kwargs):
                calls.append(args)
                return await original(*args, **kwargs)

            monkeypatch.setattr(live.remote_client, "context", counted)
            for name in ("inspector2", "reviewer"):
                other = await live.deliver(name=name)
                assert other.status_code == 403, (name, other.text)
                assert other.json() == {"detail": "delivery_requires_the_original_assessor"}
            assert calls == []
            own = await live.deliver()
            assert own.status_code == 200 and own.json()["state"] == "delivered", own.text

    run(target())


def test_initial_delivery_migration_reapplies_and_rolls_back_without_rewriting_delivered_rows(
    monkeypatch, tmp_path
):
    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            delivered = await live.deliver()
            assert delivered.status_code == 200, delivered.text
            assert delivered.json()["state"] == "delivered", delivered.text
            snapshot_sql = (
                "SELECT to_jsonb(o)::text FROM scouting_verification_outbox o "
                "WHERE tenant_id=$1::uuid AND delivery_id=$2::uuid"
            )
            before = await live.admin.fetchval(snapshot_sql, live.tenant, live.delivery_id)
            guard = "scouting_verification_delivery_initial_guard"
            definitions = await _outbox_guard_definitions(live.admin)
            assert guard in definitions
            assert {
                "scouting_verification_delivery_guard",
                "scouting_verification_delivery_insert_guard",
                "scouting_verification_delivery_delete_guard",
            } <= definitions.keys()
            up = (ROOT / "migrations/v290_scouting_verification_initial_state.sql").read_text(
                encoding="utf-8"
            )
            down = (
                ROOT / "migrations/v290_scouting_verification_initial_state.down.sql"
            ).read_text(encoding="utf-8")
            previous = (ROOT / "migrations/v289_scouting_verification_bridge.sql").read_text(
                encoding="utf-8"
            )
            try:
                for migration, present in (
                    (up, True),
                    (up, True),
                    (previous, True),
                    (down, False),
                    (down, False),
                    (up, True),
                ):
                    await live.admin.execute(migration)
                    expected = (
                        definitions
                        if present
                        else {
                            name: definition
                            for name, definition in definitions.items()
                            if name != guard
                        }
                    )
                    assert await _outbox_guard_definitions(live.admin) == expected
                    function = await live.admin.fetchval(
                        "SELECT to_regprocedure('public.scouting_verification_delivery_initial_guard()')"
                    )
                    assert (function is not None) == present
                    assert (
                        await live.admin.fetchval(snapshot_sql, live.tenant, live.delivery_id)
                        == before
                    )
            finally:
                # A failed rollback assertion must not leave later tests without
                # the guard. Neither direction may normalize existing rows.
                if live.admin.is_in_transaction():
                    await live.admin.execute("ROLLBACK")
                await live.admin.execute(up)

    run(target())


def test_the_platform_refuses_deleting_a_verified_field_with_409_through_the_real_delete(
    monkeypatch, tmp_path
):
    # Lab 1611-v1: the platform's 409 tests call protected_reference_conflict directly. Here the
    # platform's own field-row DELETE meets v289's RESTRICT reference on a live database.
    import importlib.util

    from fastapi import HTTPException

    path = ROOT / "services" / "sahool-platform" / "api" / "field_context.py"
    spec = importlib.util.spec_from_file_location("sahool_platform_field_context_live", path)
    field_context = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(field_context)

    async def target():
        async with BridgeLive(monkeypatch, tmp_path) as live:
            await _ready(live)
            with pytest.raises(HTTPException) as caught:
                async with live.admin.transaction():
                    await field_context.delete_field_row(live.admin, live.field, "حذف الحقل")
            assert caught.value.status_code == 409, caught.value.detail
            assert "scouting_verification" in caught.value.detail, caught.value.detail
            remaining = await live.admin.fetchval(
                "SELECT count(*) FROM fields WHERE tenant_id=$1::uuid AND field_id=$2",
                live.tenant,
                live.field,
            )
            assert remaining == 1

    run(target())
