"""تكذيب عمى المولّد عن المتغيّرات المقروءة عبر ثابت — RUNTIME-CONTRACT-INDIRECT-ENV-01.

`ENV_CALL_RE` كان يلتقط اسم المتغيّر **فقط كنصّ حرفيّ داخل النداء**، فـ
`os.getenv(_CLOUD_POLICY_ENV, "strict")` في `services/raster-service/cdse_client.py`
كان غير مرئيّ تماماً. النتيجة أنّ `CDSE_CLOUD_POLICY` — وهو ما يحكم رفض/قبول بيانات
المشهد الوصفيّة التالفة — لم يظهر في أيّ عقد تشغيل ولا في أيّ ملفّ تهيئة، **بينما
`--check` يمرّ**. أي بوّابة اكتمال تُبلِغ باكتمال لا تملكه: الصمت كان يُقرأ «لا يوجد
متغيّر» لا «لم أنظر».

وليست حالةً واحدة: إصلاح النمط أظهر ثلاثة عشر متغيّراً مخفيّاً عبر خمس خدمات، منها
مفتاحا تعمية MFA في `auth`.

التكذيب يمرّ عبر `extract_env_names` — وهي **نفس الدالّة التي يقرأ بها المسح**، لا
`resolve_indirect_env` وحدها. الفرق ليس شكليّاً: أوّل محاولة تكذيب هنا فشلت. حذفتُ
نداء الحلّ من مسار المسح فبقيت الاختبارات خضراء، لأنّ اختبار الأثر المُولَّد يقرأ
ملفّاً مُولَّداً سلفاً واختبار الدالّة يستدعيها مباشرة — فلا أحد منهما يمرّ بالمسح.
أي أنّ الاختبار كان سيسمح بعودة العطل بشكله الأصليّ بالضبط: قدرة موجودة لا تجري.
لذا صار للمسح مَفصِل واحد يُمسَك منه.
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

# الحادثة الأصليّة: المصدر الحقيقيّ، لا نصّ مُصطنَع.
_CDSE_CLIENT = ROOT / "services/raster-service/cdse_client.py"

# متغيّرات مخفيّة أظهرها الإصلاح — (الخدمة، المتغيّر، أهو سرّ؟).
_RECOVERED = [
    ("raster-service", "CDSE_CLOUD_POLICY", False),
    ("auth", "MFA_SECRET_ENCRYPTION_KEY", True),
    ("auth", "MFA_SECRET_DECRYPTION_KEYS", True),
    ("decision-service", "DECISION_WORKER_ASSERTION_KEY", False),
    ("edge-inference", "PEST_MODEL_PATH", False),
]


def _service(name: str) -> dict:
    contracts = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    for entry in contracts["services"]:
        if entry["service"] == name:
            return entry
    raise AssertionError(f"الخدمة {name} غائبة عن عقود التشغيل")


def test_scan_seam_resolves_the_indirect_read_through_a_module_constant():
    """المصدر الذي كشف العطل: `_CLOUD_POLICY_ENV = "CDSE_CLOUD_POLICY"` ثمّ نداء به.

    عبر `extract_env_names` قصداً — فصلُ الحلّ عن المسح يُفشِل هذا الاختبار، وهو ما
    لم يكن يفعله استدعاء `resolve_indirect_env` مباشرةً.
    """
    names = generator.extract_env_names(_CDSE_CLIENT.read_text(encoding="utf-8"), _CDSE_CLIENT.name)
    assert "CDSE_CLOUD_POLICY" in names


def test_literal_reads_still_resolve_alongside_the_indirect_ones():
    """الإضافة لا تُزيح النمط الحرفيّ — نفس الملفّ يقرأ `CDSE_ENABLED` حرفيّاً."""
    names = generator.extract_env_names(_CDSE_CLIENT.read_text(encoding="utf-8"), _CDSE_CLIENT.name)
    assert "CDSE_ENABLED" in names


def test_unresolvable_identifier_is_dropped_not_guessed():
    """اسم لا يُحلّ يُسقَط — اختراع اسم أسوأ من الإغفال الذي يُصلحه هذا التغيير."""
    assert generator.extract_env_names('os.getenv(name_from_caller, "x")') == set()


def test_constant_never_passed_to_a_read_is_not_admitted():
    """الحلّ مربوط بالاستعمال لا بوجود الثابت — وإلّا صار كلّ نصّ كبير متغيّر بيئة."""
    assert generator.extract_env_names('_UNUSED = "NOT_AN_ENV_VAR"\nvalue = 1\n') == set()


@pytest.mark.parametrize(("service", "var", "is_secret"), _RECOVERED)
def test_recovered_variables_are_present_in_the_generated_contract(
    service: str, var: str, is_secret: bool
):
    """الأثر المُولَّد نفسه — لا الدالّة وحدها: قدرة لا تجري تساوي غيابها."""
    entry = _service(service)
    bucket = "secrets" if is_secret else "configuration"
    assert var in entry[bucket], (
        f"{var} غائب عن {bucket} في عقد {service}؛ عودة الغياب تعني عودة العمى نفسه."
    )
