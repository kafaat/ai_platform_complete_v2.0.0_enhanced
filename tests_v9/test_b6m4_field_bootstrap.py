"""M4: سجلُّ تهيئةٍ قابل للاستئناف — نواةٌ نقيّة بلا خدمات.

مصدرُه حزمةُ استئناف B6/M4 المُسلَّمة من المالك؛ نُقِل إلى المستودع كي **يحجب الدمج**
بدل أن يبقى في حزمةٍ خارجيّة لا يُشغّلها أحد. أُعيد توجيه مسارات المصدر إلى مواضعها
بعد التطبيق: الشظايا التي كانت في `append/` صارت داخل ملفّات الخدمات نفسها.
"""

import asyncio
import copy
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from shared.field_bootstrap import (
    HISTORY,
    MAX_FAILURES,
    MAX_POLLS,
    OWNERS,
    STEPS,
    BootstrapError,
    ClaimedJob,
    LeaseLost,
    advance,
    new_journal,
    request_key,
    validate_journal,
    validate_receipt,
)

pytestmark = pytest.mark.unit
TENANT = "00000000-0000-0000-0000-000000000201"
OTHER = "00000000-0000-0000-0000-000000000202"
FIELD = "field-bootstrap-test"
GEOMETRY = {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]}
NOW = datetime(2026, 9, 16, 0, 0, tzinfo=UTC)


def journal(now=NOW):
    return new_journal(tenant_id=TENANT, field_id=FIELD, geometry=GEOMETRY, created_at=now)


def receipt(j, step, status="completed", ready=False):
    result = {
        "step": step,
        "scope_key": j["scope_key"],
        "request_key": request_key(j, step),
        "source_authority": OWNERS[step],
        "status": status,
    }
    if status == "pending":
        result["remote_reference"] = "durable-owner-job-1"
    else:
        result["evidence_id"] = "owner-evidence-" + step
        if step in HISTORY:
            result["coverage"] = {
                "start_date": j["scope"]["start_date"],
                "end_date": j["scope"]["end_date"],
                "complete": status == "completed",
                "gaps": [] if status == "completed" else ["gap"],
                "sample_count": 24 if status == "completed" else 2,
            }
        if step == "soil":
            result["evidence_class"] = "modelled"
        if step == "canonical_refresh":
            result.update(agronomy_ready=ready, state_digest="a" * 64)
    return result


class Store:
    def __init__(self, initial, fail_checkpoint=None):
        self.latest = copy.deepcopy(initial)
        self.snapshots = []
        self.finishes = []
        self.fail_checkpoint = fail_checkpoint
        self.calls = 0

    async def checkpoint(self, job_id, token, j):
        self.calls += 1
        if self.fail_checkpoint == self.calls:
            raise LeaseLost("replaced_worker_token")
        validate_journal(j)
        self.latest = copy.deepcopy(j)
        self.snapshots.append(copy.deepcopy(j))

    async def finish(self, job_id, token, j):
        validate_journal(j)
        self.latest = copy.deepcopy(j)
        self.finishes.append(copy.deepcopy(j))


def handlers(j, **overrides):
    result = {step: AsyncMock(return_value=receipt(j, step)) for step in STEPS}
    result.update(overrides)
    return result


async def run(j, h, *, store=None, now=NOW, geometry_loader=None, timeout=30):
    store = store or Store(j)
    loader = geometry_loader or AsyncMock(return_value=j["scope"]["geometry_digest"])
    return await advance(
        ClaimedJob(1, "worker-token", j),
        store=store,
        handlers=h,
        load_geometry_digest=loader,
        clock=lambda: now,
        timeout=timeout,
    ), store


@pytest.mark.parametrize(
    "created,start,end",
    [
        (NOW, "2024-09-16", "2026-09-15"),
        (datetime(2024, 2, 29, tzinfo=UTC), "2022-02-28", "2024-02-28"),
        (datetime(2026, 3, 1, tzinfo=UTC), "2024-03-01", "2026-02-28"),
    ],
)
def test_exact_calendar_window_is_frozen(created, start, end):
    j = journal(created)
    assert (j["scope"]["start_date"], j["scope"]["end_date"]) == (start, end)
    validate_journal(j)


def test_idempotency_binds_tenant_field_geometry_window_and_step():
    j = journal()
    keys = {request_key(j, step) for step in STEPS}
    assert len(keys) == len(STEPS)
    assert request_key(copy.deepcopy(j), "soil") == request_key(j, "soil")
    other = new_journal(tenant_id=OTHER, field_id=FIELD, geometry=GEOMETRY, created_at=NOW)
    assert j["scope_key"] != other["scope_key"]
    assert request_key(j, "soil") != request_key(other, "soil")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tenant_id": "someone"},
        {"field_id": ""},
        {"field_id": "f" * 51},
        {"geometry": {}},
        {"created_at": NOW.replace(tzinfo=None)},
    ],
)
def test_missing_trusted_inputs_are_rejected(kwargs):
    values = {"tenant_id": TENANT, "field_id": FIELD, "geometry": GEOMETRY, "created_at": NOW}
    values.update(kwargs)
    with pytest.raises(BootstrapError):
        new_journal(**values)


@pytest.mark.parametrize(
    "edit",
    [
        lambda j: j.update(schema_version="other"),
        lambda j: j["scope"].update(field_id="other"),
        lambda j: j["steps"].pop("soil"),
        lambda j: j["steps"]["soil"].update(attempts=True),
        lambda j: j["steps"]["soil"].update(failures=99),
        lambda j: j["steps"]["soil"].update(next_attempt_at="2026-09-16"),
        lambda j: j["steps"]["soil"].update(status="completed"),
        lambda j: j.update(status="completed"),
        lambda j: j.update(agronomy_ready=True),
    ],
)
def test_corrupt_or_fabricated_journals_are_rejected(edit):
    j = journal()
    edit(j)
    with pytest.raises(BootstrapError):
        validate_journal(j)


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(scope_key="b" * 64),
        lambda r: r.update(request_key="b" * 64),
        lambda r: r.update(source_authority="untrusted"),
        lambda r: r.update(status="success"),
        lambda r: r.update(fake=1),
        lambda r: r.update(evidence_id=""),
        lambda r: r.update(evidence_class="lab_guess"),
    ],
)
def test_bad_receipts_never_qualify_soil(edit):
    j = journal()
    r = receipt(j, "soil")
    edit(r)
    with pytest.raises(BootstrapError):
        validate_receipt(r, j, "soil")


@pytest.mark.parametrize(
    "edit",
    [
        lambda c: c.update(complete=False),
        lambda c: c.update(gaps=["missing"]),
        lambda c: c.update(sample_count=0),
        lambda c: c.update(sample_count=True),
        lambda c: c.update(start_date="2026-09-15"),
        lambda c: c.update(end_date="2026-09-16"),
        lambda c: c.update(extra="invented"),
    ],
)
def test_http_success_without_full_history_receipt_is_not_completion(edit):
    j = journal()
    r = receipt(j, "imagery_history")
    edit(r["coverage"])
    with pytest.raises(BootstrapError, match="history_completion_not_proven"):
        validate_receipt(r, j, "imagery_history")


def test_pending_needs_durable_reference_and_large_receipts_are_rejected():
    j = journal()
    r = receipt(j, "imagery_history", "pending")
    r.pop("remote_reference")
    with pytest.raises(BootstrapError, match="pending_remote_reference"):
        validate_receipt(r, j, "imagery_history")
    r = receipt(j, "soil")
    r["evidence_id"] = "x" * 20000
    with pytest.raises(BootstrapError, match="receipt_too_large"):
        validate_receipt(r, j, "soil")


@pytest.mark.asyncio
async def test_workflow_completion_does_not_fabricate_agronomy_readiness():
    j = journal()
    out, store = await run(j, handlers(j))
    assert out["status"] == "completed" and out["agronomy_ready"] is False
    assert len(store.snapshots) == 10 and len(store.finishes) == 1
    assert j["steps"]["soil"]["attempts"] == 0  # input snapshot is not mutated


@pytest.mark.asyncio
async def test_only_owner_final_readiness_declaration_sets_ready():
    j = journal()
    h = handlers(j)
    h["canonical_refresh"] = AsyncMock(return_value=receipt(j, "canonical_refresh", ready=True))
    out, _ = await run(j, h)
    assert out["agronomy_ready"] is True


@pytest.mark.asyncio
async def test_intent_is_durable_before_each_provider_call():
    j = journal()
    store = Store(j)
    h = {}
    for step in STEPS:

        async def call(request, previous, name=step):
            assert store.latest["steps"][name]["status"] == "running"
            assert store.latest["steps"][name]["attempts"] == 1
            assert request["request_key"] == request_key(j, name)
            return receipt(j, name)

        h[step] = call
    await run(j, h, store=store)


@pytest.mark.asyncio
async def test_lost_lease_before_intent_commit_prevents_provider_io():
    j = journal()
    h = handlers(j)
    store = Store(j, fail_checkpoint=1)
    with pytest.raises(LeaseLost):
        await run(j, h, store=store)
    assert all(call.await_count == 0 for call in h.values())
    assert store.finishes == []


@pytest.mark.asyncio
async def test_late_result_cannot_finish_after_losing_lease():
    j = journal()
    h = handlers(j)
    store = Store(j, fail_checkpoint=2)
    with pytest.raises(LeaseLost):
        await run(j, h, store=store)
    assert store.latest["steps"]["soil"]["status"] == "running"
    assert h["soil"].await_count == 1 and store.finishes == []


@pytest.mark.asyncio
async def test_restart_resumes_only_unfinished_stages():
    j = journal()
    h = handlers(j)
    h["soil"] = AsyncMock(side_effect=RuntimeError("UNSAFE_PROVIDER_TRACE"))
    out, _ = await run(j, h)
    assert out["status"] == "pending" and out["steps"]["soil"]["failures"] == 1
    assert "UNSAFE_PROVIDER_TRACE" not in str(out)
    assert out["steps"]["weather_history"]["status"] == "completed"
    next_handlers = handlers(j)
    resumed, _ = await run(out, next_handlers, now=NOW + timedelta(minutes=2))
    assert resumed["status"] == "completed"
    for step in ("weather_subscription", "weather_history", "imagery_history"):
        next_handlers[step].assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_remote_reference_and_key_are_reused_after_pending_poll():
    j = journal()
    h = handlers(j)
    pending = receipt(j, "imagery_history", "pending")
    h["imagery_history"] = AsyncMock(return_value=pending)
    out, _ = await run(j, h)
    resumed = handlers(j)
    done, _ = await run(out, resumed, now=NOW + timedelta(minutes=6))
    args = resumed["imagery_history"].await_args.args
    assert args[0]["request_key"] == request_key(j, "imagery_history") and args[1] == pending
    assert done["status"] == "completed"


@pytest.mark.asyncio
async def test_more_than_five_valid_polls_do_not_spend_error_budget():
    j = journal()
    h = handlers(j)
    h["imagery_history"] = AsyncMock(return_value=receipt(j, "imagery_history", "pending"))
    for n in range(10):
        j, _ = await run(j, h, now=NOW + timedelta(minutes=6 * n))
    stage = j["steps"]["imagery_history"]
    assert stage["polls"] == 10 and stage["attempts"] == 10 and stage["failures"] == 0
    assert j["status"] == "pending"


@pytest.mark.asyncio
async def test_poll_deadline_is_separate_and_bounded():
    j = journal()
    h = handlers(j)
    h["imagery_history"] = AsyncMock(return_value=receipt(j, "imagery_history", "pending"))
    out, _ = await run(j, h)
    out, _ = await run(out, h, now=NOW + timedelta(days=7))
    assert out["steps"]["imagery_history"]["reason"] == "stage_deadline_reached"
    assert out["status"] == "blocked" and h["imagery_history"].await_count == 1


@pytest.mark.asyncio
async def test_actual_failures_are_bounded_and_other_sources_still_progress():
    j = journal()
    h = handlers(j)
    h["soil"] = AsyncMock(side_effect=TimeoutError())
    for n in range(MAX_FAILURES):
        j, _ = await run(j, h, now=NOW + timedelta(hours=n))
    assert j["steps"]["soil"]["failures"] == MAX_FAILURES
    assert j["steps"]["soil"]["status"] == "blocked"
    assert j["status"] == "blocked" and j["steps"]["weather_history"]["status"] == "completed"
    assert h["soil"].await_count == MAX_FAILURES and h["canonical_refresh"].await_count == 0


@pytest.mark.asyncio
async def test_due_time_prevents_busy_retry_without_sleeping():
    j = journal()
    h = handlers(j)
    h["soil"] = AsyncMock(side_effect=TimeoutError())
    out, _ = await run(j, h)
    resumed = handlers(j)
    again, _ = await run(out, resumed, now=NOW + timedelta(seconds=20))
    resumed["soil"].assert_not_awaited()
    assert again["steps"]["soil"]["attempts"] == 1
    assert again["next_attempt_at"] == (NOW + timedelta(seconds=60)).isoformat()


@pytest.mark.asyncio
async def test_missing_adapter_is_visible_and_consumes_no_attempt():
    j = journal()
    out, _ = await run(j, {})
    assert out["status"] == "pending" and out["agronomy_ready"] is False
    for step in STEPS[:-1]:
        assert out["steps"][step]["reason"] == "owner_adapter_not_configured"
        assert out["steps"][step]["attempts"] == 0
    assert out["next_attempt_at"] == (NOW + timedelta(minutes=5)).isoformat()


@pytest.mark.asyncio
async def test_partial_history_not_promoted_and_blocks_final_refresh():
    j = journal()
    h = handlers(j)
    h["weather_history"] = AsyncMock(return_value=receipt(j, "weather_history", "partial"))
    out, _ = await run(j, h)
    assert out["steps"]["weather_history"]["status"] == "partial"
    assert out["status"] == "pending" and out["agronomy_ready"] is False
    h["canonical_refresh"].assert_not_awaited()


@pytest.mark.asyncio
async def test_geometry_change_before_first_call_cancels_old_scope():
    j = journal()
    h = handlers(j)
    out, store = await run(j, h, geometry_loader=AsyncMock(return_value="b" * 64))
    assert out["status"] == "superseded" and len(store.finishes) == 1
    assert all(call.await_count == 0 for call in h.values())


@pytest.mark.asyncio
async def test_geometry_change_during_last_call_cannot_set_ready():
    j = journal()
    current = [j["scope"]["geometry_digest"]]
    h = handlers(j)

    async def geometry():
        return current[0]

    async def last(request, previous):
        current[0] = "b" * 64
        return receipt(j, "canonical_refresh", ready=True)

    h["canonical_refresh"] = last
    out, _ = await run(j, h, geometry_loader=geometry)
    assert out["status"] == "superseded" and out["agronomy_ready"] is False


@pytest.mark.asyncio
async def test_cancelled_worker_preserves_intent_and_restart_uses_same_key():
    j = journal()
    store = Store(j)
    h = handlers(j)
    h["soil"] = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await run(j, h, store=store)
    assert store.latest["steps"]["soil"]["status"] == "running"
    recovery = handlers(j)
    out, _ = await run(store.latest, recovery, now=NOW + timedelta(minutes=3))
    assert out["steps"]["soil"]["failures"] == 1
    assert (
        recovery["soil"].await_args.args[0]["request_key"]
        == h["soil"].await_args.args[0]["request_key"]
    )


@pytest.mark.asyncio
async def test_handler_timeout_is_bounded_and_does_not_block_independent_sources():
    j = journal()
    h = handlers(j)

    async def slow(request, previous):
        await asyncio.sleep(30)

    h["soil"] = slow
    out, _ = await run(j, h, timeout=0.001)
    assert out["steps"]["soil"]["reason"] == "owner_call_failed"
    assert out["steps"]["weather_history"]["status"] == "completed"


@pytest.mark.parametrize("timeout", [0, -1, 31, True, float("nan")])
@pytest.mark.asyncio
async def test_bad_time_budget_rejected(timeout):
    j = journal()
    with pytest.raises(BootstrapError, match="timeout_out"):
        await run(j, {}, timeout=timeout)
