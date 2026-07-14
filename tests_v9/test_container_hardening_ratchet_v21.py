"""حارس صرّار تصلّب زمن التشغيل للحاويات (تدقيق الحاويات V21 §5 / CT-05).

الدفعة الأولى (الأكثر أماناً): العمّال الخمسة لزمن تشغيل الأطوار
(``phase-runtime`` outbox/plugin/model/actuator/water_ledger) بلا مجلّدات، وكلّ
دخْلهم DB (شبكة) + سجلّات stdout + ملفّ نبضة تحت ``/tmp`` (CT-06) — لذا يحملون:
``read_only: true`` + ``tmpfs: [/tmp]`` + ``cap_drop: [ALL]`` +
``no-new-privileges``. إضافةً، أربع خدمات بلا مجلّدات كانت تنقص
``no-new-privileges`` صارت تحمله (خطوة أولى؛ ``read_only`` مؤجَّل لدفعة لاحقة
بعد تعليل الكتابات لكلّ خدمة).

هذا صرّار (ratchet): ``HARDENED_SET`` أدناه يجب أن يكون **مجموعة جزئيّة** من الواقع
في ``docker-compose.v9.yml`` — الدفعات المقبلة تُوسّعه ولا تُقلّصه أبداً. أيّ انحدار
يُزيل تصلّباً مُطبّقاً يُفشِل هذا الاختبار.

ملاحظة أمانة: ``read_only`` لم يُتحقَّق منه زمن تشغيل داخل الصندوق (لا يمكن رفع
الحاويات هنا) — التحقّق هنا تحليل compose + تعليل الكتابات فقط. ``pytest -m unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_COMPOSE = ROOT / "docker-compose.v9.yml"

# العمّال الخمسة المُصلَّبون بالكامل في الدفعة الأولى (read_only + tmpfs + cap_drop + nnp).
FULLY_HARDENED_WORKERS = (
    "sahool-phase-runtime-outbox-worker",
    "sahool-plugin-runtime-worker",
    "sahool-model-registry-worker",
    "sahool-actuator-dispatch-worker",
    "sahool-water-ledger-worker",
)

# الخدمات الأربع التي أُضيف إليها no-new-privileges فقط في هذه الدفعة (لا read_only بعد).
NNP_ADDED_SERVICES = (
    "raster-tiler-service",
    "sahool-weather-polygon-worker",
    "sahool-weather-signal-engine",
    "sahool-soil-service",
)

# صرّار: خريطة الحدّ الأدنى المضمون من التصلّب. الواقع يجب أن يشمل هذا (superset).
# الدفعات المقبلة تُضيف مفاتيح/خدمات هنا ولا تحذف. مفاتيح كلّ خدمة مجموعة جزئيّة
# من مفاتيح تصلّبها الفعليّة.
HARDENED_SET: dict[str, set[str]] = {
    **{w: {"read_only", "tmpfs", "cap_drop", "no-new-privileges"} for w in FULLY_HARDENED_WORKERS},
    **{s: {"no-new-privileges"} for s in NNP_ADDED_SERVICES},
}

# خدمات مرحّلة لدفعات لاحقة (توثيق فقط، لا تأكيد): تحمل no-new-privileges لكنّها
# لم تُنقل بعد إلى read_only لأنّ كتاباتها تحتاج تعليلاً (مجلّدات/كاش/حالة على القرص).
STAGED_FOR_LATER_BATCHES = (
    "sahool-migrate",  # يملك مجلّدات — خارج نطاق CT-05.
    "sahool-zlmediakit-config",  # يملك مجلّد zlm-conf — خارج نطاق CT-05.
    "sahool-nginx",  # كاش nginx على القرص — دفعة لاحقة.
)


def _load_services() -> dict:
    data = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    assert "services" in data, "compose بلا مفتاح services"
    return data["services"]


def _actual_hardening(svc: dict) -> set[str]:
    """يستخرج مجموعة سمات التصلّب المُطبَّقة فعليّاً على خدمة."""
    applied: set[str] = set()
    if svc.get("read_only") is True:
        applied.add("read_only")
    tmpfs = svc.get("tmpfs") or []
    if isinstance(tmpfs, str):
        tmpfs = [tmpfs]
    if any(str(t).split(":", 1)[0] == "/tmp" for t in tmpfs):
        applied.add("tmpfs")
    cap_drop = svc.get("cap_drop") or []
    if any(str(c).upper() == "ALL" for c in cap_drop):
        applied.add("cap_drop")
    sec = svc.get("security_opt") or []
    if any(str(o).replace(" ", "") == "no-new-privileges:true" for o in sec):
        applied.add("no-new-privileges")
    return applied


def test_compose_parses():
    services = _load_services()
    assert isinstance(services, dict) and services


def test_five_workers_fully_hardened():
    services = _load_services()
    for worker in FULLY_HARDENED_WORKERS:
        assert worker in services, f"العامل مفقود من compose: {worker}"
        applied = _actual_hardening(services[worker])
        for attr in ("read_only", "tmpfs", "cap_drop", "no-new-privileges"):
            assert attr in applied, f"{worker} ينقص {attr}"


def test_four_services_have_no_new_privileges():
    services = _load_services()
    for svc_name in NNP_ADDED_SERVICES:
        assert svc_name in services, f"الخدمة مفقودة من compose: {svc_name}"
        applied = _actual_hardening(services[svc_name])
        assert "no-new-privileges" in applied, f"{svc_name} ينقص no-new-privileges"


def test_four_services_not_yet_read_only():
    """توثيق الحدّ: هذه الخدمات لم تُنقل إلى read_only بعد (دفعة لاحقة بعد تعليل الكتابات)."""
    services = _load_services()
    for svc_name in NNP_ADDED_SERVICES:
        assert services[svc_name].get("read_only") is not True, (
            f"{svc_name} صار read_only دون تعليل الكتابات — حدّث الصرّار عمداً"
        )


def test_hardened_workers_declare_pythondontwritebytecode():
    """تحت read_only لا تُكتب .pyc — نضمن PYTHONDONTWRITEBYTECODE=1 لتفادي محاولة كتابة تفشل."""
    services = _load_services()
    for worker in FULLY_HARDENED_WORKERS:
        env = services[worker].get("environment") or {}
        assert isinstance(env, dict), f"{worker}: environment ليست خريطة"
        assert str(env.get("PYTHONDONTWRITEBYTECODE")) == "1", (
            f"{worker} ينقص PYTHONDONTWRITEBYTECODE=1"
        )


def test_ratchet_hardened_set_is_subset_of_actual():
    """صرّار: كلّ سمة في HARDENED_SET يجب أن تكون مُطبَّقة فعلاً. لا انحدار."""
    services = _load_services()
    for svc_name, required in HARDENED_SET.items():
        assert svc_name in services, f"HARDENED_SET يشير إلى خدمة مفقودة: {svc_name}"
        applied = _actual_hardening(services[svc_name])
        missing = required - applied
        assert not missing, f"انحدار تصلّب على {svc_name}: مفاتيح مفقودة {sorted(missing)}"


def test_staged_services_still_present():
    """الخدمات المرحّلة لدفعات لاحقة موجودة (توثيق النطاق المتبقّي، لا تأكيد تصلّب)."""
    services = _load_services()
    for svc_name in STAGED_FOR_LATER_BATCHES:
        assert svc_name in services, f"خدمة مرحّلة مفقودة: {svc_name}"
