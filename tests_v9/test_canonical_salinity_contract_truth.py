from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/v225_canonical_salinity_state.sql"
MANIFEST = ROOT / "migrations/MANIFEST.txt"
REGISTRY = ROOT / "docs/capability-registry/domains/irrigation.yaml"


def test_migration_registered_before_final_rls_hardening():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "v225_canonical_salinity_state.sql" in text
    assert text.index("v225_canonical_salinity_state.sql") < text.index(
        "v206_rls_final_hardening.sql"
    )


pytestmark = pytest.mark.unit


def test_migration_force_rls_append_only_and_fail_closed():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "salinity_evidence_observations FORCE ROW LEVEL SECURITY" in text
    assert "canonical_salinity_states FORCE ROW LEVEL SECURITY" in text
    assert text.count("WITH CHECK") >= 2
    assert "BEFORE UPDATE OR DELETE ON salinity_evidence_observations" in text
    assert "BEFORE UPDATE OR DELETE ON canonical_salinity_states" in text
    assert "NOT operational_recommendation_allowed OR" in text


# سجلّ مصادر الحقيقة الزراعيّة (docs/architecture/agricultural_sources_of_truth.yaml)
# **خارج هذه الشريحة** — ولم يُحذَف تأكيده تخفيفاً بل لأنّ صفوفه كما وصلت تُعلن ما
# ليس في الشجرة: ``workflow_consumer: canonical_event_consumers.py`` وحدةٌ استُبعِدت
# لأنّها غير قابلة للوصول، و``acceptance_tests`` تشير إلى ملفّ سقط معها، و``writer``
# يسمّي خدمةً **لا تكتب هذه الجداول أصلاً** (لا كاتب لها اليوم — انظر
# docs/architecture/db_ownership.yml). يُنزَل السجلّ في شريحته بصفوفٍ تقول ما هو قائم.


def test_registry_links_both_capabilities_without_claiming_runtime():
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    for cid in ("IRR-009", "IRR-010"):
        cap = next(item for item in payload["capabilities"] if item["id"] == cid)
        evidence = {item["path"] for item in cap.get("evidence", [])}
        tests = set(cap.get("tests", []))
        assert "services/sahool-platform/api/canonical_salinity_state.py" in evidence
        assert "migrations/v225_canonical_salinity_state.sql" in evidence
        assert "tests_v9/test_canonical_salinity_state.py" in tests
        assert cap["production_certified"] is False
