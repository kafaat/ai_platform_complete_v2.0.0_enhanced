import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_field_live_gate_proves_restricted_role_and_role_closure():
    s = (ROOT / "scripts/staging/field_management_live_gate.sh").read_text(encoding="utf-8")
    for token in (
        "rolsuper",
        "rolbypassrls",
        "rolcreatedb",
        "rolcreaterole",
        "pg_auth_members",
        "reachable_privileged_role_count",
        "owner_or_superuser_proof_accepted",
    ):
        assert token in s
    assert "FIELD_RLS_EVIDENCE_OUT" in s


def test_kg_legacy_platform_store_is_physically_absent():
    assert not (ROOT / "services/sahool-platform/core/knowledge_graph/sqlite_graph.py").exists()


def test_kg_freeze_is_deterministic_and_has_real_consumers():
    p = ROOT / "scripts/architecture/s4_kg_consumer_freeze.py"
    spec = importlib.util.spec_from_file_location("kgfreeze", p)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    d = m.document()
    assert d["legacy_platform_store_absent"] is True
    paths = {x["evidence"] for x in d["consumers"]}
    assert "services/ai_agronomist/ai_evidence_runtime.py" in paths
    assert any("mcp_servers/generic_context_server.py" in x for x in paths)


def test_kg_runtime_collector_is_read_only_and_subject_bound():
    s = (ROOT / "scripts/staging/kg_runtime_parity_collector.py").read_text(encoding="utf-8")
    assert "/v1/edges?" in s and "/graphql" in s
    assert "subject_sha" in s and "read_only" in s
    assert "git" in s and "rev-parse" in s and "checkout_subject_sha_mismatch" in s
    assert "'/v1/nodes'" not in s and "method='PUT'" not in s and "method='DELETE'" not in s


def test_s5_dead_farmonaut_provider_identity_is_retired():
    assert not (ROOT / "services/sahool-platform/core/connectors/farmonaut.py").exists()
    policy = json.loads(
        (ROOT / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    assert (
        "services/sahool-platform/core/connectors/farmonaut.py"
        not in policy["baseline"]["platform_provider_clients"]
    )


def test_s5_platform_cdse_duplicate_is_retired():
    assert not (ROOT / "services/sahool-platform/core/connectors/copernicus.py").exists()
    assert (ROOT / "services/raster-service/cdse_client.py").is_file()
    policy = json.loads(
        (ROOT / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    assert (
        "services/sahool-platform/core/connectors/copernicus.py"
        not in policy["baseline"]["platform_provider_clients"]
    )


def test_s5_duplicate_openmeteo_core_connector_is_retired():
    ident = "services/sahool-platform/core/connectors/weather_openmeteo.py"
    assert not (ROOT / ident).exists()
    assert (ROOT / "services/sahool-platform/api/connectors/openmeteo.py").is_file()
    policy = json.loads(
        (ROOT / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    assert ident not in policy["baseline"]["platform_provider_clients"]
    assert ident not in policy["baseline"]["platform_domain_compute"]


def test_s5_dead_machine_capability_compute_is_retired():
    ident = "services/sahool-platform/api/canonical_irrigation_machine_capability.py"
    assert not (ROOT / ident).exists()
    policy = json.loads(
        (ROOT / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    assert ident not in policy["baseline"]["platform_domain_compute"]


def test_s5_dead_platform_imagery_registry_is_retired():
    ident = "services/sahool-platform/api/imagery_providers.py"
    assert not (ROOT / ident).exists()
    assert (ROOT / "services/raster-service/cdse_client.py").is_file()
    policy = json.loads(
        (ROOT / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    assert ident not in policy["baseline"]["platform_domain_compute"]
