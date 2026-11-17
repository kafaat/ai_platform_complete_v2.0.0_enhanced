"""W1-03 review: one ECe rule for field_state, proved on live PG (NOBYPASSRLS role).

Over HTTP into the platform app, on a migrated Postgres, every sample through
``/api/v1/lab/*`` and approved by a second user:

- an older critical ECe (saturated paste, 12 dS/m) and a newer approved pH-only sample: the
  pH-only sample carries no EC, so the ECe is still the older one; Salinity>Vigor keeps the
  field in ``human_review`` and the salinity age is the ECe sample's, not the pH sample's.
  The control field (same shape, ECe 1.0) stays ``auto``, so the escalation is the ECe's;
- an older critical ECe and a newer EC 1:5: the ECe is unknown (not fed as current) but the
  critical prior is not dropped: ``human_review``, labelled ``ece_unknown_prior_critical``;
- a correction submission supersedes the approved ECe at once, so the persisted
  ``field_state`` is recomputed then, not only on the next review decision.
"""

from __future__ import annotations

import asyncio
import json
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
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
_TABLES = (
    "lab_samples",
    "soil_lab_results",
    "soil_lab_tests",
    "fields",
    "field_state",
    "imagery_automation_fields",
)
_OLD = date.today() - timedelta(days=20)
_NEW = date.today() - timedelta(days=1)


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


def _agronomic(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return value or {}


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from core.canonical_schemas import UserRole, UserSchema

    tenant = str(uuid.uuid4())
    tag = uuid.uuid4().hex[:8]
    control, phonly, extract, corr = (
        f"w103e-{k}-{tag}" for k in ("control", "phonly", "extract", "corr")
    )
    admin = await asyncpg.connect(ADMIN_DSN)
    role = None
    if (
        await admin.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        and DSN == ADMIN_DSN
    ):
        role = f"w103e_rls_{uuid.uuid4().hex[:10]}"
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
    for field in (control, phonly, extract, corr):
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id, lat, lon) "
            "VALUES ($1, $1, $2::uuid, 15.3, 44.2)",
            field,
            tenant,
        )
        # A fresh, healthy NDVI scene: the state reaches auto unless salinity escalates it.
        await admin.execute(
            "INSERT INTO imagery_automation_fields (field_id, tenant_id, bbox_west, bbox_south,"
            " bbox_east, bbox_north, last_image_date, last_ndvi_mean, last_ndvi_date)"
            " VALUES ($1, $2::uuid, 44.1, 15.2, 44.3, 15.4, CURRENT_DATE, 0.7, CURRENT_DATE)",
            field,
            tenant,
        )
    acting = {"user": None}
    main.app.dependency_overrides[main.get_current_user] = lambda: acting["user"]
    out: dict = {"fields": {"control": control, "phonly": phonly, "extract": extract}}

    def as_user(actor: str, role_: UserRole = UserRole.MANAGER) -> None:
        acting["user"] = UserSchema(user_id=actor, tenant_id=tenant, role=role_, name_ar="مختبر")

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app, raise_app_exceptions=False),
            base_url="http://platform",
            timeout=120,
        ) as client:

            async def approved_sample(field: str, sampled_on: date, results: dict) -> str:
                as_user("lab-tech")
                made = await client.post(
                    "/api/v1/lab/samples",
                    json={
                        "field_id": field,
                        "kind": "soil",
                        "latitude": 15.3,
                        "longitude": 44.2,
                        "depth_cm_from": 0,
                        "depth_cm_to": 30,
                        "sampled_on": sampled_on.isoformat(),
                    },
                )
                assert made.status_code == 200, made.text
                sid = made.json()["sample_id"]
                put = await client.post(
                    "/api/v1/lab/soil-results", json={"sample_id": sid, **results}
                )
                assert put.status_code == 200, put.text
                as_user("reviewer", UserRole.AGRONOMIST)
                ok = await client.post(
                    f"/api/v1/lab/samples/{sid}/transition", json={"target_status": "approved"}
                )
                assert ok.status_code == 200, ok.text
                return sid

            paste = {"ec_extraction_method": "saturated_paste"}
            await approved_sample(control, _OLD, {"ec_dsm": 1.0, **paste})
            await approved_sample(control, _NEW, {"ph": 7.9})
            await approved_sample(phonly, _OLD, {"ec_dsm": 12.0, **paste})
            await approved_sample(phonly, _NEW, {"ph": 7.9})
            await approved_sample(extract, _OLD, {"ec_dsm": 12.0, **paste})
            await approved_sample(
                extract,
                _NEW,
                {"ec_dsm": 0.4, "ec_extraction_method": "soil_water_1_5", "ph": 7.9},
            )
            out["phonly_ece_id"] = str(
                await admin.fetchval(
                    "SELECT r.result_id FROM soil_lab_results r JOIN lab_samples s"
                    " USING (tenant_id, sample_id) WHERE s.field_id=$1 AND r.analyte='ec_dsm'",
                    phonly,
                )
            )
            as_user("viewer")
            for name, field in (("control", control), ("phonly", phonly), ("extract", extract)):
                out[f"{name}_state"] = (await client.get(f"/api/v1/fields/{field}/state")).json()
                out[f"{name}_persisted"] = await admin.fetchrow(
                    "SELECT validity, execution_mode FROM field_state WHERE field_id=$1", field
                )

            # Correction: an approved critical ECe on a published sample, superseded by a
            # correction that still awaits review.
            sid = await approved_sample(corr, _NEW, {"ec_dsm": 12.0, **paste})
            await admin.execute("UPDATE lab_samples SET status='published' WHERE sample_id=$1", sid)
            rid = await admin.fetchval(
                "SELECT result_id FROM soil_lab_results WHERE sample_id=$1 AND analyte='ec_dsm'",
                sid,
            )
            out["corr_before"] = await admin.fetchrow(
                "SELECT agronomic, computed_at FROM field_state WHERE field_id=$1", corr
            )
            as_user("lab-tech")
            fixed = await client.post(
                "/api/v1/lab/soil-results",
                json={
                    "sample_id": sid,
                    "ec_dsm": 1.0,
                    **paste,
                    "supersedes_result_ids": {"ec_dsm": str(rid)},
                    "correction_reason": "instrument recalibration",
                },
            )
            assert fixed.status_code == 200, fixed.text
            out["corr_after"] = await admin.fetchrow(
                "SELECT agronomic, computed_at FROM field_state WHERE field_id=$1", corr
            )
            out["corr_superseded"] = await admin.fetchval(
                "SELECT quality_status FROM soil_lab_results WHERE result_id=$1", rid
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


def test_control_field_reaches_auto(scenario):
    """Sanity: same shape with a low ECe is auto, so an escalation below is the ECe's."""
    state = scenario["control_state"]
    assert state["execution_mode"] == "auto", f"control must be auto: {state}"
    assert state["soil_lab"]["ec_dsm"] == 1.0, state["soil_lab"]


def test_newer_ph_only_sample_keeps_the_older_critical_ece(scenario):
    state = scenario["phonly_state"]
    soil = state["soil_lab"]
    assert soil["ec_dsm"] == 12.0, f"a pH-only sample dropped the older critical ECe: {soil}"
    assert soil["ec_result_id"] == scenario["phonly_ece_id"], soil
    assert soil["ec_sampled_on"] == _OLD.isoformat(), (
        f"salinity age must be the ECe sample's, not the pH-only sample's: {soil}"
    )
    truths = state["agronomic"]["operational_truths"]
    assert truths.get("salinity_class") == "critical", truths
    assert state["execution_mode"] == "human_review", "Salinity>Vigor failed open"
    persisted = scenario["phonly_persisted"]
    assert persisted["execution_mode"] == "human_review", dict(persisted)


def test_newer_non_ece_extract_keeps_a_critical_prior_ece_escalated(scenario):
    state = scenario["extract_state"]
    soil = state["soil_lab"]
    assert soil["ec_dsm"] is None, f"an EC 1:5 must leave the ECe unknown: {soil}"
    assert soil["ec_other_extract"]["extraction_method"] == "soil_water_1_5", soil
    assert soil["ec_prior_ece"]["value_dsm"] == 12.0, soil
    assert soil["ece_unknown_prior_critical"] is True, soil
    assert state["execution_mode"] == "human_review", "a critical prior ECe must not fail open"
    assert scenario["extract_persisted"]["execution_mode"] == "human_review"


def test_correction_submission_recomputes_field_state(scenario):
    before, after = scenario["corr_before"], scenario["corr_after"]
    assert scenario["corr_superseded"] == "superseded", scenario["corr_superseded"]
    truths_before = _agronomic(before["agronomic"]).get("operational_truths") or {}
    assert truths_before.get("salinity_class") == "critical", truths_before
    assert after["computed_at"] > before["computed_at"], (
        "the correction superseded the approved ECe: field_state must be recomputed then"
    )
    truths_after = _agronomic(after["agronomic"]).get("operational_truths") or {}
    assert truths_after.get("salinity_class") != "critical", (
        f"field_state still shows the superseded ECe: {truths_after}"
    )
