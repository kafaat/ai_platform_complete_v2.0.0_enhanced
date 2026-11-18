"""W1-03 (owner decision 2026-11-16): one canonical soil-lab store, proved on live PG.

``soil_lab_results`` (v156/v160, written through ``/api/v1/lab/*``) is the single canonical
soil-lab store; the legacy ``soil_lab_tests`` table is frozen and read only as a labelled
fallback. Over HTTP into the platform app, on a migrated Postgres, through a NOBYPASSRLS role:

- an approved v156 EC result reaches ``/data-completeness`` and the canonical field state
  (``/state``): salinity, execution mode, and the source with its ``result_id``;
- it wins over an older legacy row of the same field; a field with only a legacy row still
  answers, labelled ``legacy_soil_lab_tests``; a field with neither is unavailable (no EC, no
  zero);
- the legacy write routes answer 410 Gone and write nothing;
- an approved EC that is not a saturated-paste ECe (here EC 1:5) never reaches the salinity
  signal: no ``ec_dsm``, no older ECe fallback, the reading labelled in ``ec_other_extract``;
- a sample registered without ``sampled_on`` (the lab API allows it) still reaches
  ``/data-completeness`` and ``/state``, dated by its registration and labelled so.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
_TABLES = ("lab_samples", "soil_lab_results", "soil_lab_tests", "fields", "field_state")


async def _probe() -> str:
    try:
        conn = await asyncpg.connect(ADMIN_DSN, timeout=5)
    except Exception as exc:  # noqa: BLE001 - any failure means "no database here"
        return f"{type(exc).__name__}: {exc}"
    try:
        for table in _TABLES:
            if await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is None:
                return f"schema not migrated ({table} missing)"
    finally:
        await conn.close()
    return ""


_WHY = asyncio.run(_probe())
pytestmark.append(pytest.mark.skipif(bool(_WHY), reason=f"declared skip (not a pass): {_WHY}"))


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import api.main as main

    return main


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:8]
    canonical, legacy_only, empty, ec15, nodate = (
        f"w103-{k}-{tag}" for k in ("canon", "legacy", "empty", "ec15", "nodate")
    )
    admin = await asyncpg.connect(ADMIN_DSN)
    role = None
    if (
        await admin.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        and DSN == ADMIN_DSN
    ):
        role = f"w103_rls_{uuid.uuid4().hex[:10]}"
        await admin.execute(
            f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS;'
            f'GRANT USAGE ON SCHEMA public TO "{role}";'
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}";'
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}";'
            f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO "{role}";'
        )

    async def setup(conn):
        if role:
            await conn.execute(f'SET ROLE "{role}"')

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4, setup=setup)
    monkeypatch.setattr(main, "_DB_POOL", pool)
    for field in (canonical, legacy_only, empty, ec15, nodate):
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, lat, lon) "
            "VALUES ($1, $1, $2::uuid, 15.3, 44.2)",
            field,
            tenant,
        )
    # Legacy history, written before the freeze: an older low-EC row on the canonical field
    # and the only lab evidence of the legacy-only field.
    for field, days, ec in (
        (canonical, 30, 1.0),
        (legacy_only, 10, 9.5),
        (ec15, 30, 1.0),
    ):
        await admin.execute(
            "INSERT INTO soil_lab_tests (test_id, tenant_id, field_id, status, sampled_on, result)"
            " VALUES ($1, $2::uuid, $3, 'published', $4, $5::jsonb)",
            f"soil_{uuid.uuid4().hex[:12]}",
            tenant,
            field,
            date.today() - timedelta(days=days),
            f'{{"ec": {ec}, "ph": 7.4}}',
        )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {"tenant": tenant}

    def as_user(actor: str, role_: UserRole = UserRole.MANAGER) -> None:
        acting["user"] = UserSchema(user_id=actor, tenant_id=tenant, role=role_, name_ar="مختبر")

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=120,
        ) as client:
            as_user("lab-tech")
            created = await client.post(
                "/api/v1/lab/samples",
                json={
                    "field_id": canonical,
                    "kind": "soil",
                    "latitude": 15.3,
                    "longitude": 44.2,
                    "depth_cm_from": 0,
                    "depth_cm_to": 30,
                    "sampled_on": (date.today() - timedelta(days=2)).isoformat(),
                },
            )
            assert created.status_code == 200, created.text
            sid = created.json()["sample_id"]
            entered = await client.post(
                "/api/v1/lab/soil-results",
                json={
                    "sample_id": sid,
                    "ec_dsm": 10.0,
                    "ec_extraction_method": "saturated_paste",
                    "ph": 7.9,
                },
            )
            assert entered.status_code == 200, entered.text
            # Before approval the v156 result is not decision input: the older legacy row is.
            out["before"] = (await client.get(f"/api/v1/fields/{canonical}/state")).json()
            out["computed_before"] = await admin.fetchval(
                "SELECT computed_at FROM field_state WHERE field_id=$1", canonical
            )
            as_user("reviewer", UserRole.AGRONOMIST)
            approved = await client.post(
                f"/api/v1/lab/samples/{sid}/transition",
                json={"target_status": "approved"},
            )
            assert approved.status_code == 200, approved.text
            as_user("lab-tech")
            nutrient_url = "/api/v1/nutrients/4r-plan"
            stored = await client.post(nutrient_url, params={"field_id": canonical})
            assert stored.status_code == 200, stored.text
            plan = stored.json()
            assert (plan["status"], plan["sample_id"], plan["field_id"]) == (
                "available",
                sid,
                canonical,
            )
            ph_id = await admin.fetchval(
                "SELECT result_id FROM soil_lab_results WHERE sample_id=$1 AND analyte='ph'",
                sid,
            )
            assert plan["evidence_ids"]["ph"] == str(ph_id)
            missing = await client.post(nutrient_url, params={"field_id": f"missing-{tag}"})
            assert missing.status_code == 404, missing.text
            as_user("reviewer", UserRole.AGRONOMIST)
            out["ec_result_id"] = str(
                await admin.fetchval(
                    "SELECT result_id FROM soil_lab_results WHERE sample_id=$1 AND analyte='ec_dsm'",
                    sid,
                )
            )
            out["persisted_after_approval"] = await admin.fetchrow(
                "SELECT validity, execution_mode, computed_at FROM field_state WHERE field_id=$1",
                canonical,
            )
            out["state_events"] = await admin.fetch(
                "SELECT payload->>'trigger' AS trigger FROM events"
                " WHERE entity_type='field' AND entity_id=$1 AND event_type='field.state_changed'",
                canonical,
            )
            out["sample_events"] = await admin.fetchval(
                "SELECT count(*) FROM events WHERE entity_type='sample' AND entity_id=$1"
                " AND event_type='soil.sample.recorded'",
                sid,
            )
            # Two more approved v156 analyses: an EC 1:5 (not an ECe) and a sample without a
            # collection date.
            for field, sampled_on, results in (
                (
                    ec15,
                    (date.today() - timedelta(days=3)).isoformat(),
                    {
                        "ec_dsm": 2.0,
                        "ec_extraction_method": "soil_water_1_5",
                        "ph": 8.1,
                    },
                ),
                (
                    nodate,
                    None,
                    {"ec_dsm": 3.0, "ec_extraction_method": "saturated_paste"},
                ),
            ):
                as_user("lab-tech")
                body = {
                    "field_id": field,
                    "kind": "soil",
                    "latitude": 15.3,
                    "longitude": 44.2,
                    "depth_cm_from": 0,
                    "depth_cm_to": 30,
                }
                if sampled_on:
                    body["sampled_on"] = sampled_on
                made = await client.post("/api/v1/lab/samples", json=body)
                assert made.status_code == 200, made.text
                other = made.json()["sample_id"]
                put = await client.post(
                    "/api/v1/lab/soil-results", json={"sample_id": other, **results}
                )
                assert put.status_code == 200, put.text
                as_user("reviewer", UserRole.AGRONOMIST)
                ok = await client.post(
                    f"/api/v1/lab/samples/{other}/transition",
                    json={"target_status": "approved"},
                )
                assert ok.status_code == 200, ok.text
                out[f"{field}_ec_result_id"] = str(
                    await admin.fetchval(
                        "SELECT result_id FROM soil_lab_results"
                        " WHERE sample_id=$1 AND analyte='ec_dsm'",
                        other,
                    )
                )
            out["ec15_field"], out["nodate_field"] = ec15, nodate
            as_user("viewer")
            for name, field in (
                ("canon", canonical),
                ("legacy", legacy_only),
                ("empty", empty),
                ("ec15", ec15),
                ("nodate", nodate),
            ):
                out[f"{name}_state"] = (await client.get(f"/api/v1/fields/{field}/state")).json()
                out[f"{name}_completeness"] = (
                    await client.get(f"/api/v1/fields/{field}/data-completeness")
                ).json()
            before = await admin.fetchval(
                "SELECT count(*) FROM soil_lab_tests WHERE tenant_id=$1::uuid", tenant
            )
            as_user("lab-tech")
            out["legacy_post"] = await client.post(
                f"/api/v1/fields/{canonical}/soil-lab-tests",
                json={
                    "lab_name": "old",
                    "sampled_on": date.today().isoformat(),
                    "result": {"ec": 2},
                },
            )
            out["legacy_patch"] = await client.patch(
                f"/api/v1/fields/{legacy_only}/soil-lab-tests/anything",
                json={"status": "published"},
            )
            out["legacy_rows"] = (
                before,
                await admin.fetchval(
                    "SELECT count(*) FROM soil_lab_tests WHERE tenant_id=$1::uuid",
                    tenant,
                ),
            )
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        await pool.close()
        await admin.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def test_unapproved_v156_result_is_not_decision_input(scenario):
    soil = scenario["before"]["soil_lab"]
    assert soil["source"] == "legacy_soil_lab_tests", f"pending result leaked: {soil}"
    assert soil["ec_dsm"] == 1.0, f"the older legacy EC is the only approved input: {soil}"


def test_approved_v156_result_reaches_field_state(scenario):
    state = scenario["canon_state"]
    soil = state["soil_lab"]
    assert soil["source"] == "soil_lab_results", f"canonical store not used: {soil}"
    assert soil["ec_dsm"] == 10.0, f"approved v156 EC must win over the older legacy row: {soil}"
    assert soil["ec_result_id"] == scenario["ec_result_id"], "EC must cite its v156 result_id"
    truths = state["agronomic"]["operational_truths"]
    assert truths.get("salinity_class") == "critical", f"salinity not escalated: {truths}"
    assert state["execution_mode"] == "human_review", "critical salinity must escalate"
    persisted = scenario["persisted_after_approval"]
    assert persisted["computed_at"] > scenario["computed_before"], (
        "approval must refresh the persisted field_state projection in its transaction"
    )
    assert persisted["execution_mode"] == "human_review", f"projection not escalated: {persisted}"
    # FIELD_STATE_CHANGED follows the projection's own rule: validity or mode changed.
    before = scenario["before"]
    changed = (before["validity"], before["execution_mode"]) != (
        persisted["validity"],
        persisted["execution_mode"],
    )
    triggers = [r["trigger"] for r in scenario["state_events"]]
    assert ("soil_lab.approved" in triggers) == changed, (
        f"FIELD_STATE_CHANGED must be emitted exactly when the state changed: {triggers}"
    )


def test_soil_sample_recorded_has_its_canonical_producer(scenario):
    assert scenario["sample_events"] == 1, "creating a soil lab sample emits SOIL_SAMPLE_RECORDED"


def test_approved_v156_result_reaches_field_completeness(scenario):
    done = scenario["canon_completeness"]
    assert "has_soil_lab" in done["present"], f"approved analysis not counted: {done}"
    assert done["soil_lab"]["source"] == "soil_lab_results", done["soil_lab"]
    assert done["soil_lab"]["result_ids"]["ec_dsm"] == scenario["ec_result_id"], done["soil_lab"]


def test_legacy_only_field_is_labelled_fallback(scenario):
    soil = scenario["legacy_state"]["soil_lab"]
    assert soil["source"] == "legacy_soil_lab_tests", f"fallback not labelled: {soil}"
    assert soil["ec_dsm"] == 9.5 and soil["ec_result_id"] is None, soil
    done = scenario["legacy_completeness"]
    assert done["soil_lab"]["source"] == "legacy_soil_lab_tests", done["soil_lab"]
    assert done["soil_lab"]["result_ids"] == {}, "a legacy row has no v156 result ids"


def test_field_without_lab_evidence_is_unavailable_not_zero(scenario):
    soil = scenario["empty_state"]["soil_lab"]
    assert soil == {
        "available": False,
        "source": None,
        "ec_dsm": None,
        "ec_source": None,
        "ec_result_id": None,
        "ec_evidence_ref": None,
        "ec_sampled_on": None,
        "ec_other_extract": None,
        "ec_prior_ece": None,
        "ece_unknown_prior_critical": False,
        "sampled_on_source": None,
    }, f"missing lab evidence must be unavailable, never zero: {soil}"
    done = scenario["empty_completeness"]
    assert "has_soil_lab" in done["missing"], done
    assert done["soil_lab"] == {
        "available": False,
        "reason": "no_approved_soil_lab_result",
    }, done


def test_legacy_soil_lab_writes_are_frozen(scenario):
    for name in ("legacy_post", "legacy_patch"):
        response = scenario[name]
        assert response.status_code == 410, f"{name}: {response.status_code} {response.text}"
        detail = response.json()["detail"]
        assert detail["code"] == "legacy_soil_lab_tests_frozen", detail
        assert "POST /api/v1/lab/soil-results" in detail["use"], "410 must point to /api/v1/lab/*"
    before, after = scenario["legacy_rows"]
    assert before == after == 3, f"a frozen route wrote soil_lab_tests: {before} -> {after}"


def test_ec_other_than_saturated_paste_never_feeds_salinity(scenario):
    """An EC 1:5 of 2.0 is roughly an ECe of 12 or more: read as ECe it would be 'low'."""
    state = scenario["ec15_state"]
    soil = state["soil_lab"]
    assert soil["source"] == "soil_lab_results", f"the approved v156 analysis is the head: {soil}"
    assert soil["ec_dsm"] is None, f"EC 1:5 must not be handed over as ECe: {soil}"
    other = soil["ec_other_extract"]
    assert other is not None, f"the non-ECe reading must stay visible, labelled: {soil}"
    assert other["extraction_method"] == "soil_water_1_5" and other["value_dsm"] == 2.0, other
    assert other["ece"] is False, other
    assert other["result_id"] == scenario[f"{scenario['ec15_field']}_ec_result_id"], other
    # No ECe (and no NDVI): the agronomic block is absent or carries no soil_ec signal.
    agronomic = state.get("agronomic") or {}
    truths = agronomic.get("operational_truths") or {}
    assert truths.get("salinity_class") is None, (
        f"a non-ECe EC must not classify salinity (nor fall back to the older legacy 1.0): {truths}"
    )
    assert not [p for p in agronomic.get("provenance", []) if p.get("source") == "soil_ec"], (
        f"no soil_ec may enter the agronomic provenance: {agronomic}"
    )


def test_sample_without_collection_date_still_reaches_completeness_and_state(scenario):
    done = scenario["nodate_completeness"]
    assert "has_soil_lab" in done["present"], f"approved analysis hidden by NULL sampled_on: {done}"
    assert done["soil_lab"]["source"] == "soil_lab_results", done["soil_lab"]
    assert done["soil_lab"]["sampled_on_source"] == "sample_created_at", done["soil_lab"]
    assert done["soil_lab"]["sampled_on"] == date.today().isoformat(), done["soil_lab"]
    soil = scenario["nodate_state"]["soil_lab"]
    assert soil["source"] == "soil_lab_results" and soil["ec_dsm"] == 3.0, soil
    assert soil["sampled_on_source"] == "sample_created_at", soil
    assert soil["ec_result_id"] == scenario[f"{scenario['nodate_field']}_ec_result_id"], soil
