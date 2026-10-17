"""وسيطُ NATS يُلزِم TLS، ولا يعمل بمادّةٍ ذاتيّةٍ أو تطويريّةٍ في الإنتاج بصمت.

**العطلُ مقيسٌ على main@1cb6cd6c:** منفذ العملاء 4222 نصٌّ صريح — `nats/nats.conf` بلا كتلة
``tls``، فكلماتُ مرور الخدمات في ``CONNECT`` والأحداثُ كلُّها تعبر ``sahool-internal`` مقروءة.
صار الوسيطُ يُلزِم TLS، والمادّةُ لا تُلتزَم: ``sahool-nats-tls-init`` يسبقه ويفحصها، ويولّد CA
تطويرٍ وشهادةَ خادمٍ **فقط** حين تغيب و``SAHOOL_ENV`` صريحةٌ غيرُ إنتاجيّة — سياسةُ
``sahool-nginx-tls-init`` نفسُها (``tests_v9/test_gateway_tls_init.py``)، بملفّاتٍ مستقلّة.

هنا **عقدُ compose** (الترتيب · التركيب · الافتراض · ما يبلغ العملاء). و**سلوكُ السكربت الحقيقيّ**
— مشتركٌ مع Postgres (``scripts/tls/ensure_service_tls.sh``) — في ``tests_v9/test_service_tls_init.py``؛
والتحقّقُ الحيّ على nats-server حقيقيّ في ``tests_v9/test_nats_least_privilege.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
CONF = ROOT / "nats" / "nats.conf"
INIT = "sahool-nats-tls-init"
BROKER = "sahool-nats"
DEV_VALUES = {"development", "dev", "local", "test"}
CLIENT_CA_DIR = "/etc/sahool/nats-ca"

pytestmark = [pytest.mark.unit]


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _conf_body() -> str:
    return "\n".join(
        line
        for line in CONF.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


#: تُزال من المكدّس في الموجة نفسها على فرعٍ آخر (``compose``) فلا تُمَسّ كتلتُها هنا كي يندمج
#: الفرعان بلا تعارض؛ يُتجاهَل حضورُها فقط — وبعد الدمج يُحذَف هذا السطر.
WAVE_REMOVED = frozenset({"sahool-weather-polygon-worker"})


def _nats_clients() -> dict[str, dict]:
    return {
        name: svc
        for name, svc in _services().items()
        if isinstance(svc.get("environment"), dict)
        and "NATS_URL" in svc["environment"]
        and name not in WAVE_REMOVED
    }


# ── عقدُ compose ─────────────────────────────────────────────────────────────


def test_the_broker_config_requires_tls_from_the_mounted_pair():
    body = _conf_body()
    block = re.search(r"^tls\s*\{(?P<body>[^}]*)\}", body, re.M)
    assert block, "لا كتلةَ `tls` في nats.conf — 4222 نصٌّ صريحٌ يحمل كلماتِ المرور"
    cert = re.search(r'cert_file:\s*"([^"]+)"', block["body"])
    key = re.search(r'key_file:\s*"([^"]+)"', block["body"])
    assert cert and key
    assert os.path.dirname(cert[1]) == os.path.dirname(key[1]) == "/etc/nats/tls"
    assert "verify_and_map" not in block["body"] and "insecure" not in block["body"]
    mounts = [str(v) for v in _services()[BROKER]["volumes"]]
    assert "./nats/tls/server:/etc/nats/tls:ro" in mounts, "الوسيطُ لا يُركِّب زوجَه حيث يقرؤه"


def test_the_broker_waits_for_the_tls_gate():
    deps = _services()[BROKER].get("depends_on") or {}
    assert deps.get(INIT, {}).get("condition") == "service_completed_successfully", (
        "sahool-nats يُقلِع بلا بوّابة TLS — شهادةٌ غائبة تصير حلقةَ إعادة تشغيل"
    )
    init = _services()[INIT]
    assert str(init.get("restart")) == "no"
    assert init.get("network_mode") == "none", "المهمّةُ تقرأ وتكتب مجلّداً فقط — لا شبكةَ لها"
    assert "./nats/tls:/etc/service-tls" in [str(v) for v in init["volumes"]]
    assert "./scripts/tls/ensure_service_tls.sh:/ensure_service_tls.sh:ro" in [
        str(v) for v in init["volumes"]
    ], "السكربتُ المشترك وحدَه — لا نسخةً خاصّةً بالوسيط تتباعد عن سياسة Postgres"
    assert "/ensure_service_tls.sh" in [str(x) for x in init["entrypoint"]]
    env = init["environment"]
    assert (env["TLS_CODE"], env["TLS_SERVICE_HOST"]) == ("NATS", BROKER)


def test_the_gate_never_defaults_to_a_development_environment():
    raw = str(_services()[INIT]["environment"]["SAHOOL_ENV"])
    match = re.fullmatch(r"\$\{SAHOOL_ENV(?::?-(?P<default>[^}]*)|:\?[^}]*)?\}", raw)
    assert match, f"SAHOOL_ENV في {INIT} ليس تمريراً من البيئة: {raw!r}"
    assert (match.group("default") or "").strip().lower() not in DEV_VALUES, (
        f"{INIT} يفترض بيئةَ تطوير ({raw}) — نشرٌ بلا SAHOOL_ENV يولّد CA ذاتيّاً ويعمل به"
    )


def test_every_client_verifies_the_broker_with_its_ca_and_never_sees_the_key():
    """nats-py يُرقّي بـ``ssl.create_default_context()`` — ``CERT_REQUIRED`` وفحصُ الاسم.

    فالتحقّقُ قائمٌ بلا شيفرة، والناقصُ **الثقة**: CA الوسيط يصل عبر ``SSL_CERT_DIR``
    (إضافةً إلى مخزن النظام، لا استبدالاً) ومجلّدٍ لا مفتاحَ فيه.
    """
    offenders = []
    for name, svc in _nats_clients().items():
        env = svc["environment"]
        url = str(env["NATS_URL"])
        mounts = [str(v) for v in svc.get("volumes") or []]
        dirs = str(env.get("SSL_CERT_DIR") or "").split(":")
        if not url.startswith("tls://") or not url.endswith("@sahool-nats:4222"):
            offenders.append(f"{name}: {url[:40]}… ليس tls://…@sahool-nats:4222")
        if CLIENT_CA_DIR not in dirs or "/etc/ssl/certs" not in dirs:
            offenders.append(f"{name}: SSL_CERT_DIR={env.get('SSL_CERT_DIR')!r}")
        if f"./nats/tls/ca:{CLIENT_CA_DIR}:ro" not in mounts:
            offenders.append(f"{name}: لا يُركِّب CA الوسيط")
        if any(m.startswith(("./nats/tls/server", "./nats/tls:")) for m in mounts):
            offenders.append(f"{name}: يُركِّب مجلّدَ مفتاح الوسيط")
    assert _nats_clients(), "انهار الاستخراج — شرطٌ على لا عملاء يمرّ دائماً"
    assert not offenders, "\n  ".join(["عملاءُ لا يتحقّقون من الوسيط:", *offenders])


def test_no_broker_tls_material_can_be_committed():
    for name in ("server/server-key.pem", "server/server.pem", "ca/ca.pem", "ca/34fbece9.0"):
        rc = subprocess.run(
            ["git", "check-ignore", "--no-index", "-q", f"nats/tls/{name}"], cwd=ROOT, check=False
        ).returncode
        assert rc == 0, f"nats/tls/{name} غير مُتجاهَل — مادّةُ الوسيط قد تُلتزَم"
