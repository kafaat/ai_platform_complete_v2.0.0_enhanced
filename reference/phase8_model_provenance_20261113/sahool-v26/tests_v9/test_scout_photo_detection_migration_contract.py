"""Static schema/governance assertions; *not* a substitute for a PG server.

The real PG15+ gate is scripts/qa/run_scout_photo_stage8_catalog_gate.sh.
"""
from __future__ import annotations
from pathlib import Path
import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_v261_has_composite_proof_constraints_and_append_only_chain():
    sql = (ROOT/'migrations/v261_scout_photo_detection_link_events.sql').read_text()
    for expected in (
        'FOREIGN KEY (tenant_id,field_id,pin_id)',
        'FOREIGN KEY (detection_provenance_id,tenant_id,edge_result_id)',
        'FOREIGN KEY (edge_result_id,tenant_id,field_id)',
        'FOREIGN KEY(previous_event_id,tenant_id,field_id,pin_id)',
        'UNIQUE(previous_event_id)',
        'WHERE previous_event_id IS NULL',
        "d.attestation='attested'",
        'd.input_sha256=p.content_sha256',
        'AND r.field_id=NEW.field_id',
        'FORCE ROW LEVEL SECURITY',
        'BEFORE INSERT OR UPDATE OR DELETE',
        "RAISE EXCEPTION 'scout_photo_detection_link_immutable'",
        'photo.detection_link',
    ):
        assert expected in sql


def test_registry_and_scopes_are_consistent():
    manifests = (ROOT/'migrations/MANIFEST.txt').read_text().splitlines()
    names = [x.strip() for x in manifests if x.strip().endswith('.sql') and not x.strip().startswith('#')]
    assert len(names) == len(set(names))
    assert names.index('v260_scout_photo_grant_audit_enforcement.sql') + 1 == names.index('v261_scout_photo_detection_link_events.sql')
    assert names[-1] == 'v206_rls_final_hardening.sql'
    own = yaml.safe_load((ROOT/'docs/architecture/db_ownership.yml').read_text())['tables']
    assert own['scout_photo_detection_link_events']['owner'] == 'scout-ingest-service'
    assert own['scout_photo_detection_link_events']['writers'] == ['scout-ingest-service']
    router = (ROOT/'services/sahool-platform/api/routers/scout_photo_grants.py').read_text()
    ui = (ROOT/'frontend/src/sections/ScoutPhotoGrantAdminPanel.tsx').read_text()
    ts = (ROOT/'frontend/src/services/scoutPhotoGrants.ts').read_text()
    for x in [router, ui, ts]:
        assert 'photo.detection_link' in x
    assert 'SCOUT_MEDIA_DETECTION_LINK_ENABLED' in (ROOT/'services/scout-ingest-service/detection_link_api.py').read_text()


def test_ingest_is_only_runtime_writer_and_has_live_role_column():
    for name in ['bootstrap_postgres.sh','apply_in_compose.sh']:
        script=(ROOT/'migrations'/name).read_text()
        assert 'GRANT SELECT (id, tenant_id, active, role) ON users TO sahool_ingest' in script
        assert 'GRANT SELECT,INSERT ON scout_photo_detection_link_events TO sahool_ingest' in script
        assert "REVOKE UPDATE,DELETE ON scout_photo_detection_link_events FROM sahool_ingest" in script
        assert "REVOKE INSERT, UPDATE, DELETE ON TABLE public.scout_photo_detection_link_events FROM %I" in script
    assert 'refusing grant administration' not in (ROOT/'frontend/src/sections/ScoutPhotoGrantAdminPanel.tsx').read_text()


def test_stage8_gate_has_refusal_and_cannot_fake_a_live_result():
    runner=(ROOT/'scripts/qa/run_scout_photo_stage8_catalog_gate.sh').read_text()
    sql=(ROOT/'scripts/qa/scout_photo_stage8_catalog_gate.sql').read_text()
    assert "SCOUT_ACCEPTANCE_ENV:-" in runner
    assert 'command -v psql' in runner
    assert 'NOT_RUN: psql is unavailable' in runner
    assert 'SCOUT_STAGE8_CATALOG_PASS' in sql
    assert 'rolbypassrls' in sql
    assert 'SCOUT_STAGE8_BROAD_DML' in sql
    assert 'SCOUT_STAGE8_LIVE_ROLE_READ_MISSING' in sql
