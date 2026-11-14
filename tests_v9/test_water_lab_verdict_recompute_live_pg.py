"""Recomputing stored water lab verdicts (owner decision 2026-11-14), on live Postgres.

``scripts/ops/recompute_water_lab_verdicts.py`` recomputes ``water_lab_result_sets.analysis``
with the current FAO-29 three-tier analysis and keeps the old analysis as a v258 revision.

The live half seeds a migrated database with rows stored before the tier (the old analysis
called slight-to-moderate water ``suitable``) and runs the command's tenant function through a
NOSUPERUSER NOBYPASSRLS role, so row-level security applies. It shows that a dry run writes
nothing, ``--apply`` appends one revision per stale live set (the replaced row superseded with
its analysis and stamps intact), a re-run is a no-op, an unreviewed correction, a superseded row
and a row with invalid stored inputs are left alone, and another tenant's rows are not touched.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
SCRIPT = ROOT / "scripts" / "ops" / "recompute_water_lab_verdicts.py"
DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
_TABLES = ("lab_samples", "water_lab_result_sets", "fields")

# EC 1.2 dS/m with safe SAR/RSC: FAO-29 slight-to-moderate salinity ⇒ suitable_with_restrictions.
MODERATE = {"na": 1.0, "ca": 3.0, "mg": 3.0, "hco3": 1.0, "co3": 0.0, "ec_dsm": 1.2, "ph": 7.4}
# EC 4.0 dS/m ⇒ severe salinity ⇒ needs_treatment.
SEVERE = {**MODERATE, "ec_dsm": 4.0}


def _script():
    spec = importlib.util.spec_from_file_location("recompute_water_lab_verdicts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(sample_id: str, measurement: dict) -> dict:
    return {
        "sample_id": sample_id,
        "source": "well",
        "cl": None,
        "sampled_at": None,
        **measurement,
    }


def _pre_tier(analysis: dict) -> dict:
    """The analysis as stored before the FAO-29 tier: no restrictions, the middle tier 'suitable'."""
    old = {
        k: v
        for k, v in analysis.items()
        if k not in ("restrictions", "restriction_flags_ar", "advisories_ar")
    }
    if old["verdict"] == "suitable_with_restrictions":
        old.update(verdict="suitable", suitable_ar="صالح للريّ")
    elif old["verdict"] == "needs_treatment":
        old.update(verdict="suitable_with_restrictions")
    return old


# ─── the plan, without a database ─────────────────────────────────────────────


def _row(**kw):
    sid = kw.pop("sample_id", "w-1")
    measurement = kw.pop("measurement", MODERATE)
    payload = _payload(sid, measurement)
    return {
        "result_set_id": uuid.uuid4(),
        "sample_id": sid,
        "payload": json.dumps(payload),
        "quality_status": "approved",
        "supersedes_result_set_id": None,
        **kw,
    }


@pytest.mark.unit
def test_plan_revises_a_pre_tier_verdict_and_names_both_verdicts():
    script = _script()
    fresh = script.recompute(_payload("w-1", MODERATE), "w-1")
    step = script.plan(_row(analysis=json.dumps(_pre_tier(fresh))))
    assert step["action"] == script.REVISE
    assert (step["old"], step["new"]) == ("suitable", "suitable_with_restrictions")
    assert step["analysis"] == fresh


@pytest.mark.unit
def test_plan_leaves_a_current_analysis_and_a_recomputed_one_alone():
    script = _script()
    fresh = script.recompute(_payload("w-1", MODERATE), "w-1")
    assert script.plan(_row(analysis=fresh))["action"] == script.UNCHANGED
    stamped = {**fresh, "previous_verdict": "suitable", "recompute_reason": script.REASON}
    assert script.plan(_row(analysis=stamped))["action"] == script.UNCHANGED


@pytest.mark.unit
def test_plan_reports_an_unreviewed_correction_and_invalid_inputs_without_touching_them():
    script = _script()
    fresh = script.recompute(_payload("w-1", MODERATE), "w-1")
    correction = _row(
        analysis=_pre_tier(fresh),
        quality_status="unreviewed",
        supersedes_result_set_id=uuid.uuid4(),
    )
    assert script.plan(correction)["action"] == script.SKIP_UNREVIEWED_CORRECTION
    invalid = _row(analysis=_pre_tier(fresh), measurement={**MODERATE, "ec_dsm": -1.0})
    step = script.plan(invalid)
    assert step["action"] == script.SKIP_INVALID_INPUTS
    assert "ec_dsm:negative" in step["error"]


@pytest.mark.unit
def test_a_stored_source_outside_the_new_vocabulary_is_recomputed_as_stored():
    """The lab route once took any source text; the stored measurement is not rewritten."""
    script = _script()
    fresh = script.recompute({**_payload("w-1", MODERATE), "source": "mixed"}, "w-1")
    assert fresh["source"] == "mixed"


# ─── live Postgres ────────────────────────────────────────────────────────────


async def _probe() -> str:
    try:
        import asyncpg
    except ImportError:
        return "asyncpg not installed"
    try:
        conn = await asyncpg.connect(DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
        column = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_name='water_lab_result_sets'"
            " AND column_name='supersedes_result_set_id'"
        )
        if column is None:
            return "schema not migrated (v258 missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
live = pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}")


async def _snapshot(owner, tenant: str) -> list[tuple]:
    rows = await owner.fetch(
        """SELECT result_set_id, sample_id, quality_status, analysis::text, payload::text,
                  supersedes_result_set_id, approved_by, approved_at, published_at,
                  correction_reason, entered_by, request_digest
           FROM water_lab_result_sets WHERE tenant_id=$1::uuid ORDER BY result_set_id""",
        tenant,
    )
    return [tuple(r) for r in rows]


async def _scenario() -> dict:
    import asyncpg

    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    script = _script()
    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    owner = await asyncpg.connect(DSN)
    role = None
    if await owner.fetchval(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ):
        role = f"wr_rls_{uuid.uuid4().hex[:10]}"
        await owner.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
        )
    app = await asyncpg.connect(DSN)
    if role:
        await app.execute(f'SET ROLE "{role}"')
    out: dict = {"script": script}
    approved_at = datetime(2026, 10, 1, tzinfo=UTC)
    published_at = datetime(2026, 10, 2, tzinfo=UTC)

    async def seed(
        tenant_id,
        sample_id,
        measurement,
        *,
        status="approved",
        sample_status=None,
        supersedes=None,
        stale=True,
        approved=True,
        published=False,
        payload=None,
        field=None,
    ):
        field = field or f"wr-field-{tenant_id[:8]}"
        await owner.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid)"
            " ON CONFLICT DO NOTHING",
            field,
            tenant_id,
        )
        await owner.execute(
            """INSERT INTO lab_samples (sample_id, tenant_id, field_id, kind, latitude, longitude,
                                        source, status, created_by)
               VALUES ($1, $2::uuid, $3, 'water', 15.3, 44.2, 'well', $4, 'seed')
               ON CONFLICT DO NOTHING""",
            sample_id,
            tenant_id,
            field,
            sample_status
            or ("published" if published else "approved" if approved else "result_received"),
        )
        body = payload or _payload(sample_id, measurement)
        fresh = script.recompute(_payload(sample_id, measurement), sample_id)
        rid = uuid.uuid4()
        await owner.execute(
            """INSERT INTO water_lab_result_sets
               (result_set_id, tenant_id, sample_id, payload, analysis, quality_status, observed_at,
                approved_by, approved_at, published_at, supersedes_result_set_id, request_digest,
                entered_by)
               VALUES ($1, $2::uuid, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10, $11, $12, 'tech-1')""",
            rid,
            tenant_id,
            sample_id,
            json.dumps(body),
            json.dumps(_pre_tier(fresh) if stale else fresh),
            status,
            approved_at,
            "reviewer-1" if approved else None,
            approved_at if approved else None,
            published_at if published else None,
            supersedes,
            f"digest-{rid}",
        )
        return str(rid)

    s = lambda name: f"wr-{name}-{uuid.uuid4().hex[:6]}"  # noqa: E731
    ids = {}
    sid = {k: s(k) for k in ("pub", "pending", "current", "corr", "invalid", "other")}
    pub_field = f"wr-pub-{tenant[:8]}"
    ids["pub"] = await seed(tenant, sid["pub"], MODERATE, published=True, field=pub_field)
    ids["pending"] = await seed(tenant, sid["pending"], SEVERE, status="unreviewed", approved=False)
    ids["current"] = await seed(tenant, sid["current"], SEVERE, stale=False)
    ids["corr_parent"] = await seed(tenant, sid["corr"], MODERATE, status="superseded")
    ids["corr"] = await seed(
        tenant,
        sid["corr"],
        SEVERE,
        status="unreviewed",
        approved=False,
        sample_status="result_received",
        supersedes=uuid.UUID(ids["corr_parent"]),
    )
    ids["invalid"] = await seed(
        tenant,
        sid["invalid"],
        MODERATE,
        payload=_payload(sid["invalid"], {**MODERATE, "ec_dsm": -1.0}),
    )
    ids["other"] = await seed(other, sid["other"], MODERATE, published=True)
    out.update(ids=ids, sid=sid, tenant=tenant, other=other, pub_field=pub_field)

    try:
        before, other_before = await _snapshot(owner, tenant), await _snapshot(owner, other)
        out["dry"] = await script.recompute_tenant(app, tenant, apply=False)
        # The operator command itself, dry run (its default), as JSON.
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            out["cli_rc"] = await script.main(["--tenant", tenant, "--dsn", DSN, "--json"])
        out["cli"] = json.loads(printed.getvalue())
        out["dry_unchanged"] = await _snapshot(owner, tenant) == before

        # RLS, not only the WHERE clause: under tenant A's context the role sees none of B.
        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            out["rls_other_visible"] = await app.fetchval(
                "SELECT count(*) FROM water_lab_result_sets WHERE tenant_id=$1::uuid", other
            )

        now = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
        out["apply"] = await script.recompute_tenant(app, tenant, apply=True, now=now)
        out["after"] = {
            r["result_set_id"]: dict(r)
            for r in await owner.fetch(
                "SELECT * FROM water_lab_result_sets WHERE tenant_id=$1::uuid", tenant
            )
        }
        out["before"] = {r[0]: r for r in before}
        out["other_unchanged"] = await _snapshot(owner, other) == other_before
        after_apply = await _snapshot(owner, tenant)
        out["rerun"] = await script.recompute_tenant(app, tenant, apply=True)
        out["rerun_unchanged"] = await _snapshot(owner, tenant) == after_apply

        # The stored flows read the revision: the field's decision input and a client retry.
        from api import lab_store

        async with app.transaction():
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
            out["latest"] = await lab_store.latest_water_analysis(
                app, tenant_id=tenant, field_id=pub_field
            )
            pub = out["after"][uuid.UUID(ids["pub"])]
            out["replay"] = await lab_store.record_water_result(
                app,
                tenant_id=tenant,
                actor_id="tech-1",
                sample_id=sid["pub"],
                payload=_payload(sid["pub"], MODERATE),
                analysis={},
                observed_at=approved_at,
                request_digest=pub["request_digest"],
            )
            # A set changed after the operator read it is not revised: a stale read of a live
            # set (another analysis) and a set no longer live (already superseded).
            live = {
                str(r["result_set_id"]): r
                for r in await lab_store.live_water_sets(app, tenant_id=tenant)
            }
            current = dict(live[ids["current"]])
            stale_read = {**current, "analysis": json.dumps({"verdict": "suitable"})}
            count = await app.fetchval(
                "SELECT count(*) FROM water_lab_result_sets WHERE tenant_id=$1::uuid", tenant
            )
            out["stale_read"] = await lab_store.append_water_analysis_revision(
                app, tenant_id=tenant, seen=stale_read, analysis={"verdict": "x"}, reason="T"
            )
            old_pub = {
                **current,
                "result_set_id": uuid.UUID(ids["pub"]),
                "sample_id": sid["pub"],
                "quality_status": "approved",
                "analysis": out["before"][uuid.UUID(ids["pub"])][3],
            }
            out["not_live"] = await lab_store.append_water_analysis_revision(
                app, tenant_id=tenant, seen=old_pub, analysis={"verdict": "x"}, reason="T"
            )
            out["stale_writes"] = (
                await app.fetchval(
                    "SELECT count(*) FROM water_lab_result_sets WHERE tenant_id=$1::uuid", tenant
                )
                - count
            )
        return out
    finally:
        await app.close()
        for t in (tenant, other):
            await owner.execute(
                "UPDATE water_lab_result_sets SET supersedes_result_set_id=NULL WHERE tenant_id=$1::uuid",
                t,
            )
            await owner.execute("DELETE FROM water_lab_result_sets WHERE tenant_id=$1::uuid", t)
            await owner.execute("DELETE FROM lab_sample_custody_events WHERE tenant_id=$1::uuid", t)
            await owner.execute("DELETE FROM lab_samples WHERE tenant_id=$1::uuid", t)
            await owner.execute("DELETE FROM fields WHERE tenant_id=$1::uuid", t)
        if role:
            await owner.execute(f'DROP OWNED BY "{role}"; DROP ROLE "{role}"')
        await owner.close()


@pytest.fixture(scope="module")
def outcome():
    return asyncio.run(_scenario())


def _revision_of(outcome, key):
    parent = uuid.UUID(outcome["ids"][key])
    kids = [r for r in outcome["after"].values() if r["supersedes_result_set_id"] == parent]
    assert len(kids) == 1, kids
    return kids[0]


@pytest.mark.integration
@live
def test_dry_run_reports_and_writes_nothing(outcome):
    dry = outcome["dry"]
    assert dry["mode"] == "dry-run"
    assert dry["would_revise"] == 2
    assert dry["verdict_transitions"] == {
        "suitable -> suitable_with_restrictions": 1,
        "suitable_with_restrictions -> needs_treatment": 1,
    }
    assert outcome["dry_unchanged"] is True
    # The command line runs the same dry run by default and prints the same summary.
    assert outcome["cli_rc"] == 0
    assert outcome["cli"] == [dry]


@pytest.mark.integration
@live
def test_rls_hides_the_other_tenant_from_the_script_role(outcome):
    assert outcome["rls_other_visible"] == 0


@pytest.mark.integration
@live
def test_apply_appends_one_revision_per_stale_live_set(outcome):
    script = outcome["script"]
    applied = outcome["apply"]
    assert applied["revised"] == 2 and applied["unchanged"] == 1
    assert applied["verdict_transitions"] == outcome["dry"]["verdict_transitions"]
    assert sorted(s["reason"] for s in applied["skipped"]) == [
        script.SKIP_INVALID_INPUTS,
        script.SKIP_UNREVIEWED_CORRECTION,
    ]

    pub_id = uuid.UUID(outcome["ids"]["pub"])
    old, before = outcome["after"][pub_id], outcome["before"][pub_id]
    rev = _revision_of(outcome, "pub")
    # The replaced row is history: superseded, its analysis and stamps exactly as they were.
    assert old["quality_status"] == "superseded"
    assert json.loads(old["analysis"]) == json.loads(before[3])
    assert (old["approved_by"], old["approved_at"], old["published_at"]) == before[6:9]
    # The revision: same measurement, review state and stamps; the new verdict; the old one kept.
    analysis = json.loads(rev["analysis"])
    assert analysis["verdict"] == "suitable_with_restrictions"
    assert analysis["previous_verdict"] == "suitable"
    assert analysis["previous_result_id"] == str(pub_id)
    assert analysis["recompute_reason"] == "RECOMPUTE-FAO29-TIER"
    assert analysis["recomputed_at"] == "2026-11-14T12:00:00+00:00"
    assert rev["correction_reason"] == "RECOMPUTE-FAO29-TIER"
    assert rev["quality_status"] == "approved"
    assert json.loads(rev["payload"]) == json.loads(old["payload"])
    assert (rev["approved_by"], rev["approved_at"], rev["published_at"]) == (
        old["approved_by"],
        old["approved_at"],
        old["published_at"],
    )
    assert (rev["entered_by"], rev["request_digest"]) == (old["entered_by"], old["request_digest"])

    pending = _revision_of(outcome, "pending")
    assert pending["quality_status"] == "unreviewed" and pending["approved_at"] is None
    assert json.loads(pending["analysis"])["verdict"] == "needs_treatment"
    assert outcome["after"][uuid.UUID(outcome["ids"]["pending"])]["quality_status"] == "superseded"


@pytest.mark.integration
@live
def test_untouched_rows_stay_exactly_as_they_were(outcome):
    def children(rid):
        return [
            r["result_set_id"]
            for r in outcome["after"].values()
            if r["supersedes_result_set_id"] == rid
        ]

    for key in ("current", "corr", "corr_parent", "invalid"):
        rid = uuid.UUID(outcome["ids"][key])
        after, before = outcome["after"][rid], outcome["before"][rid]
        assert after["quality_status"] == before[2], key
        assert json.loads(after["analysis"]) == json.loads(before[3]), key
        expected = [uuid.UUID(outcome["ids"]["corr"])] if key == "corr_parent" else []
        assert children(rid) == expected, key
    assert len(outcome["after"]) == len(outcome["before"]) + 2


@pytest.mark.integration
@live
def test_rerun_is_a_no_op(outcome):
    rerun = outcome["rerun"]
    assert rerun["revised"] == 0 and rerun["verdict_transitions"] == {}
    assert rerun["unchanged"] == 3  # the two revisions and the already-current set
    assert outcome["rerun_unchanged"] is True


@pytest.mark.integration
@live
def test_another_tenants_rows_are_not_touched(outcome):
    assert outcome["other_unchanged"] is True


@pytest.mark.integration
@live
def test_stored_flows_read_the_revision(outcome):
    rev = _revision_of(outcome, "pub")
    assert outcome["latest"]["verdict"] == "suitable_with_restrictions"
    assert outcome["latest"]["previous_verdict"] == "suitable"
    # A client retry of the original measurement returns the current row, not a 409.
    assert outcome["replay"]["result_id"] == str(rev["result_set_id"])


@pytest.mark.integration
@live
def test_a_set_changed_since_it_was_read_is_not_revised(outcome):
    assert outcome["stale_read"] is None
    assert outcome["not_live"] is None
    assert outcome["stale_writes"] == 0
