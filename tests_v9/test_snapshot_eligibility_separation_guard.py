"""‏`CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`: اللقطة لا تكتسب أهليّة.

الحارس يعمل خطوةً حاجبة في `ci.yml`، فهذه الاختبارات لا تُعيد فحص ما يفحصه — تحرس
**دلالته**: أنّ الطريقين إلى العطل مسدودان معاً، وأنّه لا يُبلِغ خضرةً حين يفقد موضوعه.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "ci" / "snapshot_eligibility_separation_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_eligibility_separation_guard", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MOD = _load()


def test_the_tree_is_clean_right_now():
    assert MOD.violations() == []


def _repo(tmp_path: Path, *, model_body: str, migration: str) -> Path:
    service = tmp_path / "services" / "decision-service"
    (service / "migrations").mkdir(parents=True, exist_ok=True)
    (service / "main.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        f"class VegetationSnapshotIn(BaseModel):\n{model_body}\n\n\ndef unrelated():\n    pass\n",
        encoding="utf-8",
    )
    (service / "migrations" / "019_x.sql").write_text(migration, encoding="utf-8")
    return tmp_path


_CLEAN_MODEL = "    field_id: str\n    snapshot_hash: str\n"
_CLEAN_TABLE = (
    "CREATE TABLE IF NOT EXISTS decision_vegetation_snapshots (\n"
    "  snapshot_id text PRIMARY KEY, tenant_id uuid NOT NULL,\n"
    "  snapshot_hash text NOT NULL, payload jsonb NOT NULL\n"
    ");\n"
)


def _violations_in(monkeypatch, root: Path) -> list[str]:
    service = root / "services" / "decision-service"
    monkeypatch.setattr(MOD, "ROOT", root)
    monkeypatch.setattr(MOD, "SERVICE", service)
    monkeypatch.setattr(MOD, "MIGRATIONS", service / "migrations")
    monkeypatch.setattr(MOD, "MODEL_FILE", service / "main.py")
    return MOD.violations()


def test_a_clean_tree_is_not_denounced(tmp_path, monkeypatch):
    """حارسٌ يُطلِق على الشجرة السليمة يُنزَع في أوّل يوم."""
    root = _repo(tmp_path, model_body=_CLEAN_MODEL, migration=_CLEAN_TABLE)
    assert _violations_in(monkeypatch, root) == []


def test_an_eligibility_field_on_the_model_is_caught(tmp_path, monkeypatch):
    """الطريق الأوّل: حقلٌ يُضاف إلى النموذج لأنّ واجهةً احتاجته."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL + "    policy_version: str | None = None\n",
        migration=_CLEAN_TABLE,
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "policy_version" in found[0]


def test_an_eligibility_column_in_the_create_table_is_caught(tmp_path, monkeypatch):
    """الطريق الثاني: عمودٌ في تعريف الجدول."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE.replace(
            "  snapshot_hash text NOT NULL,",
            "  snapshot_hash text NOT NULL, decision_eligible boolean,",
        ),
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "decision_eligible" in found[0]


def test_an_alter_table_add_column_is_caught_too(tmp_path, monkeypatch):
    """الطريق الثالث — والأرجح عمليّاً: هجرةٌ لاحقة تُضيف العمود «للسرعة».

    حارسٌ يقرأ `CREATE TABLE` وحده يمرّ على هذه، وهي المسار الطبيعيّ لأنّ أحداً لا
    يُعيد كتابة تعريف جدول قائم.
    """
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE
        + "\nALTER TABLE decision_vegetation_snapshots ADD COLUMN eligibility_assessment_id text;\n",
    )
    found = _violations_in(monkeypatch, root)
    assert len(found) == 1 and "eligibility_assessment_id" in found[0]


def test_an_unrelated_column_is_not_denounced(tmp_path, monkeypatch):
    """النطاق ضيّق عمداً: الحارس يمنع **حكم الأهليّة** لا كلّ تطوّر للمخطَّط."""
    root = _repo(
        tmp_path,
        model_body=_CLEAN_MODEL,
        migration=_CLEAN_TABLE
        + "\nALTER TABLE decision_vegetation_snapshots ADD COLUMN cloud_pct real;\n",
    )
    assert _violations_in(monkeypatch, root) == []


def test_losing_its_subject_is_a_failure_not_a_pass(tmp_path, monkeypatch):
    """**أهمّ اختبار هنا.**

    لو أُعيد تسمية الجدول أو النموذج، فحارسٌ ساكت يُقرأ «لا مخالفة» وهو يعني «لم
    أنظر». وهذا الصنف بعينه مُسجَّل في هذا المستودع: `runtime_contract_generator`
    كان أخضر لأنّه لا يرى، لا لأنّه لا يجد.
    """
    service = tmp_path / "services" / "decision-service"
    (service / "migrations").mkdir(parents=True, exist_ok=True)
    (service / "main.py").write_text("class SomethingElse:\n    pass\n", encoding="utf-8")
    (service / "migrations" / "019_x.sql").write_text(
        "CREATE TABLE IF NOT EXISTS renamed_snapshots (id text);\n", encoding="utf-8"
    )
    found = _violations_in(monkeypatch, tmp_path)
    assert len(found) == 2, found
    assert any("VegetationSnapshotIn" in line for line in found)
    assert any("decision_vegetation_snapshots" in line for line in found)


def test_the_message_names_the_file_and_the_remedy():
    """رسالة الحارس جزءٌ منه: من يقرأها يجب أن يعرف أين يذهب."""
    body = _SCRIPT.read_text(encoding="utf-8")
    assert "decision_eligibility_assessments" in body
    assert "eligibility_policy.py" in body
