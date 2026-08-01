"""تصنيف مادّة المفاتيح — RUNTIME-CONTRACT-KEY-SUFFIX-NOT-SECRET-01.

`SECRET_MARKERS` تُفحَص كسلاسل جزئيّة، فكان الاسم يحتاج أن يحوي
`PRIVATE_KEY`/`API_KEY`/`ACCESS_KEY` ليُعَدّ سرّاً. واللاحقة المجرّدة `..._KEY` لا تطابق
أيّاً منها، فنُشِرت **عشرة مفاتيح توقيع وHMAC** بوصفها تهيئة عاديّة — منها
`FCM_SERVER_KEY` و`SEASON_EDGE_HMAC_KEY` و`DECISION_WORKER_ASSERTION_KEY`. وعقدٌ يذكر
مفتاح توقيع بجوار مستوى السجلّ لا يكون غير مرتّب فحسب، بل **يُبلِّغ سطح الأسرار أصغر
ممّا هو**.

القاعدة تُغلَق عند الفشل: اللاحقة تعني مادّة مفتاح، والاستثناءات **مُعلَنة بسطر مصدرها**
لا مُستنتَجة من الاسم.

ولماذا إعلان لا نمط أذكى؟ لأنّ `MFA_ALLOW_DERIVED_KEY` و`MFA_AUDIT_HASH_KEY` يفترقان
بكلمة واحدة في الخدمة نفسها، وأحدهما **راية منطقيّة** لا مفتاح. نمطٌ يفصل بينهما يكون
نمطاً مُفصَّلاً على ثلاثة عشر اسماً معروفاً — قائمةً في ثوب نمط، تنهار عند الاسم الرابع
عشر. فالحقيقة هنا في الكود المستهلِك لا في الاسم، والدليل هو **القراءة** لا قراءة الاسم.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "runtime_contract_generator", ROOT / "scripts/ci/runtime_contract_generator.py"
)
generator = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(generator)

CONTRACTS = ROOT / "runtime-contracts/generated/runtime_contracts.json"

# العشرة التي كانت مُصنَّفة `configuration` وهي مادّة مفاتيح — (الاسم، الخدمة).
_MISCLASSIFIED = [
    ("ACTIVATION_EVIDENCE_SIGNING_KEY", "decision-service"),
    ("ACTIVATION_PROBE_SIGNING_KEY", "decision-service"),
    ("DECISION_WORKER_ASSERTION_KEY", "decision-service"),
    ("DECISION_WORKER_ASSERTION_PREVIOUS_KEY", "decision-service"),
    ("FCM_SERVER_KEY", "sahool-platform"),
    ("FIELD_FORMS_SYNC_HMAC_KEY", "scout-ingest-service"),
    ("FIELD_SERVICE_TENANT_ASSERTION_KEY", "field-management-service"),
    ("FIELD_SERVICE_TENANT_ASSERTION_PREVIOUS_KEY", "field-management-service"),
    ("MFA_AUDIT_HASH_KEY", "auth"),
    ("SEASON_EDGE_HMAC_KEY", "auth"),
]

# الثلاثة المُعفاة — كلٌّ بسببه المقيس من الكود المستهلِك.
_EXEMPT = [
    ("JWT_PUBLIC_KEY", "auth"),
    ("MFA_ALLOW_DERIVED_KEY", "auth"),
    ("STAGING_PROBE_IDEMPOTENCY_KEY", "decision-service"),
]


def _service(name: str) -> dict:
    for entry in json.loads(CONTRACTS.read_text(encoding="utf-8"))["services"]:
        if entry["service"] == name:
            return entry
    raise AssertionError(f"الخدمة {name} غائبة عن عقود التشغيل")


@pytest.mark.parametrize(("var", "_service_name"), _MISCLASSIFIED)
def test_key_material_classifies_as_secret(var: str, _service_name: str):
    """على الدالّة مباشرةً — اختبار الأثر وحده يمرّ على منطق مكسور بأثر مُولَّد سلفاً."""
    assert generator.is_secret(var) is True


@pytest.mark.parametrize(("var", "_service_name"), _EXEMPT)
def test_declared_exemptions_classify_as_configuration(var: str, _service_name: str):
    """`JWT_PUBLIC_KEY` **يصحّ** ألّا يكون سرّاً — وعدّه سرّاً تضخيمٌ كاذب للسطح.

    على الدالّة مباشرةً وليس على الأثر: أوّل صياغة لهذا الاختبار قرأت الأثر المُولَّد،
    فتجاهُلُ الإعفاءات كلّيّاً **بقي أخضر** — نفس عمى التكذيب الذي أُصلِح في
    RUNTIME-CONTRACT-INDIRECT-ENV-01 داخل الجلسة نفسها، ووقعتُ فيه ثانيةً.
    """
    assert generator.is_secret(var) is False


@pytest.mark.parametrize(("var", "service"), _MISCLASSIFIED)
def test_key_material_is_a_secret_in_the_generated_contract(var: str, service: str):
    """والأثر أيضاً — يحرس أن يكون العقد المُلتزَم مُعاد التوليد لا بائتاً."""
    entry = _service(service)
    assert var in entry["secrets"], f"{var} يجب أن يكون سرّاً في عقد {service}"
    assert var not in entry["configuration"]


@pytest.mark.parametrize(("var", "service"), _EXEMPT)
def test_declared_exemptions_stay_configuration_in_the_contract(var: str, service: str):
    entry = _service(service)
    assert var in entry["configuration"], f"{var} مُعفى مُعلَن ويجب أن يبقى تهيئة"
    assert var not in entry["secrets"]


def test_an_undeclared_key_name_is_a_secret_by_default():
    """fail-closed: اسم جديد باللاحقة بلا إعلان ⇒ سرّ. العجز عن الإثبات ليس إثباتاً."""
    assert generator.is_secret("SOME_BRAND_NEW_SIGNING_KEY") is True
    assert generator.is_secret("ANOTHER_ROTATION_KEYS") is True


def test_losing_the_declaration_over_reports_secrets_never_under_reports(monkeypatch):
    """تعذُّر قراءة الإعلان يجعل الجميع أسراراً — الفشل يقع في الجهة الآمنة من السؤال."""
    monkeypatch.setattr(generator, "NONSECRET_KEYS_FILE", ROOT / "does_not_exist.json")
    assert generator.declared_nonsecret_keys() == set()
    assert generator.is_secret("JWT_PUBLIC_KEY") is True


def test_every_declared_exemption_carries_its_evidence_line():
    """إعفاء بلا سطر مصدر ادّعاءٌ لا دليل — والقائمة كلّها تقوم على أنّ الدليل قراءة."""
    data = json.loads(
        (ROOT / "docs/architecture/runtime_contract_nonsecret_keys.json").read_text(
            encoding="utf-8"
        )
    )
    names = {e["name"] for e in data["nonsecret"]}
    assert names == {n for n, _ in _EXEMPT}
    for entry in data["nonsecret"]:
        assert ".py:" in entry["evidence"], f"{entry['name']} بلا سطر مصدر مقروء"
        assert entry["reason"].strip()


def test_non_key_names_are_untouched_by_the_rule():
    """القاعدة تمسّ اللاحقة وحدها — لا تُوسّع التصنيف على تهيئة عاديّة."""
    for name in ("LOG_LEVEL", "REDIS_URL", "RASTER_MAX_READ_DIM", "CDSE_CLOUD_POLICY"):
        assert generator.is_secret(name) is False
