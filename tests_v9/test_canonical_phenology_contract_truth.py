from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations/v224_canonical_phenology_state.sql"
MANIFEST = ROOT / "migrations/MANIFEST.txt"
REGISTRY = ROOT / "docs/capability-registry/domains/farm_management.yaml"


def test_migration_registered_before_final_rls_hardening():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "v224_canonical_phenology_state.sql" in text
    assert text.index("v224_canonical_phenology_state.sql") < text.index(
        "v206_rls_final_hardening.sql"
    )


pytestmark = pytest.mark.unit


def test_migration_is_force_rls_and_append_only():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "phenology_observations ENABLE ROW LEVEL SECURITY" in text
    assert "phenology_observations FORCE ROW LEVEL SECURITY" in text
    assert "canonical_phenology_states ENABLE ROW LEVEL SECURITY" in text
    assert "canonical_phenology_states FORCE ROW LEVEL SECURITY" in text
    assert text.count("WITH CHECK") >= 2
    assert "BEFORE UPDATE OR DELETE ON phenology_observations" in text
    assert "BEFORE UPDATE OR DELETE ON canonical_phenology_states" in text


# سجلّ مصادر الحقيقة الزراعيّة (docs/architecture/agricultural_sources_of_truth.yaml)
# **خارج هذه الشريحة** — ولم يُحذَف تأكيده تخفيفاً بل لأنّ صفوفه كما وصلت تُعلن ما
# ليس في الشجرة: ``workflow_consumer: canonical_event_consumers.py`` وحدةٌ استُبعِدت
# لأنّها غير قابلة للوصول، و``acceptance_tests`` تشير إلى ملفّ سقط معها، و``writer``
# يسمّي خدمةً **لا تكتب هذه الجداول أصلاً** (لا كاتب لها اليوم — انظر
# docs/architecture/db_ownership.yml). يُنزَل السجلّ في شريحته بصفوفٍ تقول ما هو قائم.


def test_fm004_links_repository_evidence_without_claiming_certification():
    payload = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    cap = next(item for item in payload["capabilities"] if item["id"] == "FM-004")
    evidence = {item["path"] for item in cap.get("evidence", [])}
    tests = set(cap.get("tests", []))
    assert "services/sahool-platform/api/canonical_phenology_state.py" in evidence
    assert "migrations/v224_canonical_phenology_state.sql" in evidence
    assert "tests_v9/test_canonical_phenology_state.py" in tests
    assert cap["production_certified"] is False
