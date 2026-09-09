"""Fail-closed inventory for the open NATS ownership gaps."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/architecture/nats_subject_ownership_contract.json"
SUBJECT = "sahool.actuator.dispatch.requested"
BROKER = "sahool-nats"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _python_sources() -> list[Path]:
    return sorted((ROOT / "services").rglob("*.py")) + sorted((ROOT / "agents").rglob("*.py"))


def test_compose_nats_clients_match_the_declared_inventory() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    connected = []
    for name, service in compose["services"].items():
        # الوسيطُ نفسُه **ليس عميلاً**. صار يحمل `NATS_USER`/`NATS_PASSWORD` بعد إغلاق
        # NATS-BROKER-HAS-NO-AUTHENTICATION-…-01، فدخل الجردَ بمطابقةٍ على «NATS في
        # اسم المتغيّر». والجردُ يقيس **مَن يتّصل بالوسيط** لا مَن هو الوسيط.
        if name == BROKER:
            continue
        environment = service.get("environment") or {}
        if isinstance(environment, dict) and any(
            "NATS" in str(key) or "nats://" in str(value) for key, value in environment.items()
        ):
            connected.append(name)
    assert sorted(connected) == sorted(_contract()["connected_services"])


def test_actuator_dispatch_has_one_publisher_and_no_repository_consumer() -> None:
    publishers: list[str] = []
    consumers: list[str] = []
    literal_sites: list[str] = []
    for path in _python_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if SUBJECT not in text:
            continue
        literal_sites.append(str(path.relative_to(ROOT)))
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != SUBJECT:
                continue
            if node.func.attr == "publish":
                publishers.append(str(path.relative_to(ROOT)))
            if node.func.attr in {"subscribe", "pull_subscribe"}:
                consumers.append(str(path.relative_to(ROOT)))
    # The platform publisher calls a wrapper whose literal is the first argument.
    worker = ROOT / "services/sahool-platform/api/phase_runtime_workers.py"
    assert SUBJECT in worker.read_text(encoding="utf-8")
    assert literal_sites == ["services/sahool-platform/api/phase_runtime_workers.py"]
    assert not consumers
    gap = _contract()["gaps"]["AGENT-TO-ACTUATOR-ADAPTER-ABSENT"]
    assert gap["status"] == "OPEN"
    assert gap["consumers"] == []
    # Direct AST publishers may be empty because the production call uses _publish_nats;
    # there must never be a second direct publisher hidden elsewhere.
    assert len(set(publishers)) <= 1


def test_plugin_subject_transform_is_declared_as_an_open_divergence() -> None:
    worker = (ROOT / "services/sahool-platform/api/phase_runtime_workers.py").read_text(
        encoding="utf-8"
    )
    hooks = (ROOT / "shared/marketplace_ecosystem_phase12.py").read_text(encoding="utf-8")
    notifications = (ROOT / "agents/notification/agent.py").read_text(encoding="utf-8")
    assert 'f"sahool.{str(row[' in worker
    assert '"field.updated"' in hooks
    assert '("sahool.events.>", "notif_domain_events")' in notifications
    gap = _contract()["gaps"]["NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE"]
    assert gap["status"] == "OPEN"


def test_nats_requires_credentials_but_still_has_no_per_service_subject_acl() -> None:
    """كان هذا الاختبار يُثبِّت **غيابَ** المصادقة شرطاً — لقطةُ عطلٍ صارت ثابتاً.

    فلمّا أُغلِقت `NATS-BROKER-HAS-NO-AUTHENTICATION-…-01` أحمرَّ الاختبارُ **على
    الإصلاح**: أي أنّ عملاً صحيحاً كسر اختباراً يفترض بقاءَ الشجرة كما كانت. وهو
    الصنفُ الذي تمنعه قاعدةُ المالك: لا يحوّل اختبارٌ تشغيليٌّ لقطةً تاريخيّة إلى
    ثابتٍ أمنيّ.

    والصيغةُ الآن تقيس الحقيقتين معاً — **ما أُغلِق** و**ما لم يُغلَق** — فيبقى
    الصفُّ صادقاً في الاتّجاهين:
      * الوسيطُ يشترط اعتماداً (`authorization` مع استيفاءٍ من البيئة).
      * ولا `accounts`/`permissions`/`nkeys`: لا عزلَ مواضيعَ لكلّ خدمة.
    ولذلك تبقى الفجوةُ **OPEN**: شرطُ إغلاقها المكتوب يطلب قوائمَ سماحٍ لكلّ خدمة
    **مُثبَتةً بمِسبارَين حيَّين**، ولم يقع منها إلّا منعُ المجهول — ساكناً.
    """
    config = (ROOT / "nats/nats.conf").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in config.splitlines() if not line.lstrip().startswith("#")
    ).lower()
    assert "authorization" in body, "المصادقةُ أُزيلت — الوسيطُ عاد مفتوحاً"
    assert "$nats_user" in body and "$nats_password" in body, (
        "الاعتمادُ يجب أن يُورَث من البيئة لا يُكتَب في ملفٍّ مُلتزَم"
    )
    for token in ("accounts", "nkeys", "permissions"):
        assert token not in body, f"ظهر `{token}` — إن أُضيف عزلُ المواضيع فحدِّث الفجوة وشرطَ إغلاقها"
    gap = _contract()["gaps"]["NATS-AUTHORIZATION-NOT-ENFORCED"]
    assert gap["status"] == "OPEN", "شرطُ الإغلاق (قوائمُ سماحٍ لكلّ خدمة بمِسبارَين حيَّين) لم يقع"
