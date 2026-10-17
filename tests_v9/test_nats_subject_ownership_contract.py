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
    notifications = (ROOT / "shared/notification_consumers.py").read_text(encoding="utf-8")
    assert 'f"sahool.{str(row[' in worker
    assert '"field.updated"' in hooks
    assert '("sahool.events.>", "notif_domain_events")' in notifications
    gap = _contract()["gaps"]["NATS-SUBJECT-NAMESPACE-CONTRACT-DIVERGENCE"]
    assert gap["status"] == "OPEN"


def test_per_service_subject_acls_close_the_authorization_gap_with_live_probes() -> None:
    """الصفُّ يقيس الحقيقتين معاً — **ما أُغلِق** و**بأيّ شاهد** — لا لقطةَ عطلٍ ثابتاً.

    كان هذا الاختبارُ يُثبِّت **غيابَ** `permissions` شرطاً، فأحمرَّ على الإصلاح كما أحمرَّ
    سلفُه على إغلاق المصادقة: عملٌ صحيحٌ يكسر اختباراً يفترض بقاءَ الشجرة كما كانت. فالصيغةُ
    الآن تربط الإغلاقَ **بشرطه المكتوب**: قوائمُ سماحٍ لكلّ خدمة، ومنعُ المجهول، ومِسبارٌ سالبٌ
    وموجبٌ **حيّان** — في `tests_v9/test_nats_least_privilege.py` الذي يُشغَّل على nats-server
    حقيقيّ في مِرقاة CI (`notification-rollout.yml`، `NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1`).
    """
    config = (ROOT / "nats/nats.conf").read_text(encoding="utf-8")
    body = "\n".join(line for line in config.splitlines() if not line.lstrip().startswith("#"))
    assert "authorization" in body, "المصادقةُ أُزيلت — الوسيطُ عاد مفتوحاً"
    assert "no_auth_user" not in body, "مستخدمٌ افتراضيٌّ للمجهول يُعيد الوسيطَ مفتوحاً"
    assert body.count("permissions:") >= len(_contract()["connected_services"]), (
        "هويّةٌ بلا `permissions` — العزلُ ناقص"
    )
    gap = _contract()["gaps"]["NATS-AUTHORIZATION-NOT-ENFORCED"]
    assert gap["status"] == "CLOSED"
    for witness in gap["verified_by"]:
        assert (ROOT / witness).is_file(), f"شاهدُ الإغلاق غائب: {witness}"
    live = (ROOT / "tests_v9/test_nats_least_privilege.py").read_text(encoding="utf-8")
    assert (
        "test_live_each_identity_publishes_its_own_subjects_and_is_refused_everyone_elses" in live
    )
    assert "test_live_unauthenticated_and_wrong_password_are_refused" in live
    workflow = (ROOT / ".github/workflows/notification-rollout.yml").read_text(encoding="utf-8")
    assert "tests_v9/test_nats_least_privilege.py" in workflow, (
        "المِسباران الحيّان لا يُشغَّلان في CI — الإغلاقُ بلا شاهدٍ مستمرّ"
    )
    assert 'NATS_LEAST_PRIVILEGE_LIVE_REQUIRED: "1"' in workflow
