from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_migration_registered_before_v206():
    lines = [
        x.strip()
        for x in (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]
    assert "v226_canonical_nutrient_ledger.sql" in lines
    assert lines.index("v226_canonical_nutrient_ledger.sql") < lines.index(
        "v206_rls_final_hardening.sql"
    )


pytestmark = pytest.mark.unit


def test_migration_enforces_rls_and_append_only():
    text = (ROOT / "migrations/v226_canonical_nutrient_ledger.sql").read_text(encoding="utf-8")
    assert text.count("FORCE ROW LEVEL SECURITY") >= 2
    assert "WITH CHECK" in text
    assert "BEFORE UPDATE OR DELETE" in text
    assert "canonical_nutrient_ledgers" in text


# سجلّ مصادر الحقيقة الزراعيّة (docs/architecture/agricultural_sources_of_truth.yaml)
# **خارج هذه الشريحة** — ولم يُحذَف تأكيده تخفيفاً بل لأنّ صفوفه كما وصلت تُعلن ما
# ليس في الشجرة: ``workflow_consumer: canonical_event_consumers.py`` وحدةٌ استُبعِدت
# لأنّها غير قابلة للوصول، و``acceptance_tests`` تشير إلى ملفّ سقط معها، و``writer``
# يسمّي خدمةً **لا تكتب هذه الجداول أصلاً** (لا كاتب لها اليوم — انظر
# docs/architecture/db_ownership.yml). يُنزَل السجلّ في شريحته بصفوفٍ تقول ما هو قائم.
