"""G9 (F-E10) — the VRA prescription reads the owner's approved soil lab result, on live PG.

``generate_vra_prescription`` accepts approved lab evidence only from the server-built
``evidence_context["approved_soil_lab"]`` block (W0-12). The advisor feeds the engine the
platform's AI context pack, so the pack has to carry that block, read from the lab owner
(sahool-platform, ``soil_lab_results``) through the same read the field 4R plan uses
(``lab_store.latest_soil_4r_rows``). Over a migrated Postgres, through a NOBYPASSRLS role:

- an approved sample reaches the prescription with each result's method, unit, sampling
  date and approval reference, and the zones are lab supported;
- a newer sample that is not approved is not used;
- another tenant's approved sample on the same field is not used;
- a field with no approved lab result says the prescription was computed without
  laboratory data;
- the prescription stays not machine-exportable and review-required either way.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)
ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL", DSN)
_TABLES = ("lab_samples", "soil_lab_results", "fields")


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

_ZONES = [
    {"zone_id": "pz-1", "productivity_class": "high", "area_ha": 4.0},
    {"zone_id": "pz-2", "productivity_class": "medium", "area_ha": 4.0},
    {"zone_id": "pz-3", "productivity_class": "low", "area_ha": 4.0},
]


def _platform():
    if str(PLATFORM) not in sys.path:
        sys.path.insert(0, str(PLATFORM))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import api.main as main

    return main


async def _seed_sample(admin, *, tenant, field, status, sampled_on, results):
    sid = f"g9-{uuid.uuid4().hex[:12]}"
    await admin.execute(
        """INSERT INTO lab_samples (sample_id, tenant_id, field_id, kind, latitude, longitude,
                                    sampled_on, depth_cm_from, depth_cm_to, status, created_by)
           VALUES ($1, $2::uuid, $3, 'soil', 15.3, 44.2, $4, 0, 30, $5, 'seed')""",
        sid,
        tenant,
        field,
        sampled_on,
        status,
    )
    ids = {}
    for analyte, value, unit, method, quality in results:
        rid = str(uuid.uuid4())
        approved_at = datetime.now(UTC) - timedelta(days=1) if quality == "approved" else None
        await admin.execute(
            """INSERT INTO soil_lab_results (result_id, tenant_id, sample_id, analyte, value_json,
                                             unit, method_code, quality_status, observed_at,
                                             approved_by, approved_at)
               VALUES ($1::uuid, $2::uuid, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11)""",
            rid,
            tenant,
            sid,
            analyte,
            json.dumps(value),
            unit,
            method,
            quality,
            datetime.now(UTC) - timedelta(days=2),
            "reviewer-1" if approved_at else None,
            approved_at,
        )
        ids[analyte] = rid
    return sid, ids


async def _scenario(monkeypatch) -> dict:
    main = _platform()
    from api.routers.field_ai_context import field_ai_context_pack
    from core.canonical_schemas import UserRole, UserSchema

    from services.ai_agronomist import ai_evidence_runtime as runtime

    tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
    tag = uuid.uuid4().hex[:8]
    lab_field, bare_field = f"g9-lab-{tag}", f"g9-bare-{tag}"
    admin = await asyncpg.connect(ADMIN_DSN)
    role = None
    if (
        await admin.fetchval(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        and DSN == ADMIN_DSN
    ):
        role = f"g9_rls_{uuid.uuid4().hex[:10]}"
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
    out: dict = {"tenant": tenant}
    try:
        for field in (lab_field, bare_field):
            await admin.execute(
                "INSERT INTO fields (field_id, name, tenant_id, lat, lon) "
                "VALUES ($1, $1, $2::uuid, 15.3, 44.2)",
                field,
                tenant,
            )
        today = date.today()
        out["sampled_on"] = (today - timedelta(days=10)).isoformat()
        _, out["approved_ids"] = await _seed_sample(
            admin,
            tenant=tenant,
            field=lab_field,
            status="approved",
            sampled_on=today - timedelta(days=10),
            results=[
                ("ph", 7.9, "1", "saturated_paste_ph", "approved"),
                ("phosphorus_mg_kg", 12.0, "mg/kg", "olsen", "approved"),
            ],
        )
        # A newer sample whose results are not reviewed: not lab evidence.
        _, out["unapproved_ids"] = await _seed_sample(
            admin,
            tenant=tenant,
            field=lab_field,
            status="result_received",
            sampled_on=today - timedelta(days=2),
            results=[("phosphorus_mg_kg", 99.0, "mg/kg", "olsen", "unreviewed")],
        )
        # Another tenant's approved sample written against the same field id: never read.
        _, out["other_tenant_ids"] = await _seed_sample(
            admin,
            tenant=other,
            field=lab_field,
            status="approved",
            sampled_on=today - timedelta(days=1),
            results=[("phosphorus_mg_kg", 55.0, "mg/kg", "olsen", "approved")],
        )

        user = UserSchema(
            user_id="advisor", tenant_id=tenant, role=UserRole.MANAGER, name_ar="مستشار"
        )
        for key, field in (("lab", lab_field), ("bare", bare_field)):
            pack = await field_ai_context_pack(
                field,
                days=730,
                include_weather=False,
                include_imagery=False,
                include_events=False,
                user=user,
            )
            pack = pack.model_dump(mode="json")
            out[f"{key}_pack"] = pack
            fetch = runtime._build_agent_tool_fetcher(
                field_state={"field_id": field}, ai_pack=pack, annotations={}
            )
            out[f"{key}_strict"] = fetch("generate_vra_prescription", {"zones": _ZONES})
            out[f"{key}_estimated"] = fetch(
                "generate_vra_prescription", {"zones": _ZONES, "allow_estimated": True}
            )
    finally:
        await pool.close()
        for field in (lab_field, bare_field):
            await admin.execute(
                "DELETE FROM soil_lab_results WHERE sample_id IN "
                "(SELECT sample_id FROM lab_samples WHERE field_id=$1)",
                field,
            )
            await admin.execute("DELETE FROM lab_samples WHERE field_id=$1", field)
            await admin.execute("DELETE FROM fields WHERE field_id=$1", field)
        if role:
            await admin.execute(
                f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}";'
                f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM "{role}";'
                f'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM "{role}";'
                f'REVOKE USAGE ON SCHEMA public FROM "{role}";'
                f'DROP ROLE "{role}"'
            )
        await admin.close()
    return out


@pytest.fixture(scope="module")
def scenario():
    mp = pytest.MonkeyPatch()
    try:
        yield asyncio.run(_scenario(mp))
    finally:
        mp.undo()


def _levels(out):
    return {z["zone_id"]: z["evidence_level"] for z in out["prescription_zones"]}


def test_approved_owner_lab_reaches_the_prescription(scenario):
    out = scenario["lab_strict"]
    assert out["vra_prescription"] is not None, (
        "an approved lab result exists for this field and tenant, yet the prescription was "
        f"not produced from it: {out['readiness_gate']}"
    )
    assert set(_levels(out).values()) == {"lab_supported"}, _levels(out)
    assert out["readiness_gate"]["lab_evidence_source"] == "approved_soil_lab"


def test_prescription_carries_method_units_date_and_approval_ref(scenario):
    basis = scenario["lab_strict"]["vra_prescription"]["laboratory_basis"]
    assert basis["status"] == "approved_laboratory_results", basis
    by_analyte = {r["analyte"]: r for r in basis["results"]}
    assert set(by_analyte) == {"ph", "phosphorus_mg_kg"}, by_analyte
    p = by_analyte["phosphorus_mg_kg"]
    assert p["result_id"] == scenario["approved_ids"]["phosphorus_mg_kg"]
    assert p["method_code"] == "olsen"
    assert p["unit"] == "mg/kg"
    assert p["sampled_on"] == scenario["sampled_on"]
    assert p["approval_ref"] == f"soil_lab_results:{p['result_id']}"
    assert p["approved_at"], "the approval time must travel with the result"
    assert by_analyte["ph"]["method_code"] == "saturated_paste_ph"
    assert by_analyte["ph"]["unit"] == "1"


def test_unapproved_and_other_tenant_results_are_not_used(scenario):
    used = {
        r["result_id"]
        for r in scenario["lab_strict"]["vra_prescription"]["laboratory_basis"]["results"]
    }
    lineage = set(scenario["lab_strict"]["vra_prescription"]["source_lineage"]["lab_result_ids"])
    pack_ids = {r["result_id"] for r in scenario["lab_pack"]["approved_soil_lab"]["results"]}
    for leaked in list(scenario["unapproved_ids"].values()) + list(
        scenario["other_tenant_ids"].values()
    ):
        assert leaked not in used | lineage | pack_ids, f"result {leaked} must not be used"
    assert scenario["lab_pack"]["approved_soil_lab"]["tenant_id"] == scenario["tenant"]


def test_no_approved_lab_states_computed_without_laboratory_data(scenario):
    block = scenario["bare_pack"]["approved_soil_lab"]
    assert block["status"] == "unavailable" and block["results"] == [], block
    strict = scenario["bare_strict"]
    assert strict["vra_prescription"] is None
    assert strict["readiness_gate"]["reason"] == "missing_lab_results_or_estimation_consent"
    out = scenario["bare_estimated"]
    basis = out["vra_prescription"]["laboratory_basis"]
    assert basis["status"] == "computed_without_laboratory_data", basis
    assert basis["results"] == []
    assert out["readiness_gate"]["laboratory_basis"] == "computed_without_laboratory_data"


@pytest.mark.parametrize("key", ["lab_strict", "lab_estimated", "bare_estimated"])
def test_prescription_stays_review_required_and_not_machine_exportable(scenario, key):
    out = scenario[key]
    assert out["ready_for_machine_export"] is False
    assert out["readiness_gate"]["ready_for_machine_export"] is False
    assert out["vra_prescription"]["requires_agronomist_review"] is True
    assert "agronomist_review" in out["readiness_gate"]["required_before_export"]
