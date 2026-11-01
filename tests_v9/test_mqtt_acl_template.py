"""قالب ACL لوسيط MQTT (تدقيق 2026-11-01، A8) — أقلّ امتياز، ويغطّي ما تستعمله الشيفرة فعلاً.

القالب غير مُفعَّل بعد (قرار نشر)، لكنّه يجب أن يبقى **صالحاً للتفعيل**: لا منحَ واسعاً، الجهاز
يقرأ أوامره وحده، وكلّ موضوعٍ تنشره/تشترك فيه خدمةٌ مغطّى لهويّتها — وإلّا يكسر تفعيلُه الإنتاج.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ACL = ROOT / "mosquitto" / "acl.template"


def _grants() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    user = None
    for raw in ACL.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "user":
            user = parts[1]
            out.setdefault(user, [])
        elif parts[0] == "pattern":
            out.setdefault("%pattern", []).append((parts[1], parts[2]))
        elif parts[0] == "topic":
            assert user is not None, f"topic بلا user: {line}"
            out[user].append((parts[1], parts[2]))
        else:
            raise AssertionError(f"سطر ACL غير متوقّع: {line}")
    return out


def _matches(pattern: str, topic: str) -> bool:
    p, t = pattern.split("/"), topic.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return True
        if i >= len(t) or (seg != "+" and seg != t[i]):
            return False
    return len(p) == len(t)


def _allowed(user: str, access: str, topic: str) -> bool:
    return any(
        a in (access, "readwrite") and _matches(pat, topic) for a, pat in _grants().get(user, [])
    )


def test_no_identity_is_granted_the_whole_broker():
    for user, grants in _grants().items():
        for access, pat in grants:
            assert pat not in {"#", "+/#", "sahool/#"}, f"{user}: {access} {pat}"
            assert access != "readwrite", f"{user}: readwrite {pat}"


def test_devices_read_only_their_own_command_topic():
    assert _grants()["%pattern"] == [("read", "sahool/actuator/%u/command")]


def test_actuator_identity_covers_exactly_what_the_service_uses():
    src = (ROOT / "services/actuator-service/actuator_runtime.py").read_text(encoding="utf-8")
    assert 'topic = f"sahool/actuator/{device_id}/command"' in src
    assert 'topic = "sahool/+/+/telemetry/+"' in src
    assert _allowed("sahool-actuator-service", "write", "sahool/actuator/valve-1/command")
    assert _allowed("sahool-actuator-service", "read", "sahool/+/+/telemetry/+")
    # لا ينشر قراءاتٍ ولا يقرأ أوامر غيره.
    assert not _allowed("sahool-actuator-service", "write", "sahool/t/f/telemetry/soil")


def test_video_identity_cannot_command_valves():
    assert _allowed("sahool-video-processor", "write", "sahool/tenant/t1/alerts/pest")
    assert _allowed("sahool-video-processor", "write", "sahool/video/stream/started")
    assert not _allowed("sahool-video-processor", "write", "sahool/actuator/valve-1/command")


def test_template_carries_no_secret_values():
    text = ACL.read_text(encoding="utf-8")
    assert not re.search(r"(?im)^\s*password\s+\S+", text)
    assert "acl_file /mosquitto/config/acl" in (ROOT / "mosquitto/mosquitto.conf").read_text(
        encoding="utf-8"
    )
