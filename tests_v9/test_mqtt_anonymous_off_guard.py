"""حارس تشديد MQTT — رفض الوصول المجهول (allow_anonymous false) + مصادقة العميل.

يثبت ساكنًا أنّ:
  • mosquitto.conf يرفض المجهول ويعتمد password_file (لا allow_anonymous true).
  • docker-compose.v9.yml يولّد passwd من env عند الإقلاع، وفحص الصحّة يوثّق نفسه،
    والعميلان (actuator/video) يتلقّيان MQTT_USERNAME/MQTT_PASSWORD.
  • كود العميل يمرّر بيانات الاعتماد إلى aiomqtt عبر _mqtt_auth_kwargs.
ووظيفيًّا أنّ _mqtt_auth_kwargs يعيد بيانات الاعتماد إن ضُبطت واسمًا فارغًا ⇒ {} (مجهول، متوافق للخلف).

الاختبارات الوظيفيّة تعزل كلّ خدمة في عمليّة فرعيّة (اسمَا الحزمة ``routers``/``main``
مشتركان بين الخدمات ⇒ تلوّث sys.modules داخل عمليّة واحدة).

ملاحظة صدق: هذا حارس تهيئة/منطق عميل. إثبات الرفض الحيّ (اتّصال مجهول يفشل + موثّق ينجح)
عبر وسيط فعليّ يبقى معلّقًا — يُجرى في CI/بيئة Docker سليمة، لا هنا.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONF = (ROOT / "mosquitto" / "mosquitto.conf").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")


def test_broker_rejects_anonymous() -> None:
    assert "allow_anonymous false" in CONF
    assert "allow_anonymous true" not in CONF
    assert "password_file /mosquitto/config/passwd" in CONF


def test_compose_generates_passwd_and_authenticates_healthcheck() -> None:
    assert "mosquitto_passwd -b -c /mosquitto/config/passwd" in COMPOSE
    # فحص الصحّة يمرّر بيانات الاعتماد (لم يعد الاتّصال المجهول ممكنًا).
    assert 'mosquitto_sub -h 127.0.0.1 -p 1883 -u "$$MQTT_USERNAME" -P "$$MQTT_PASSWORD"' in COMPOSE
    # كلا العميلَين + الوسيط يستلمون بيانات الاعتماد (env مطلوب، لا افتراضيّ صامت).
    assert COMPOSE.count("MQTT_USERNAME: ${MQTT_USERNAME:?") >= 3
    assert COMPOSE.count("MQTT_PASSWORD: ${MQTT_PASSWORD:?") >= 3


def test_client_code_passes_auth_kwargs() -> None:
    actuator = (ROOT / "services" / "actuator-service" / "actuator_runtime.py").read_text("utf-8")
    video_main = (ROOT / "services" / "video-processor" / "main.py").read_text("utf-8")
    video_events = (ROOT / "services" / "video-processor" / "stream_events.py").read_text("utf-8")
    assert "def _mqtt_auth_kwargs" in actuator
    assert "**_mqtt_auth_kwargs()" in actuator
    assert "def _mqtt_auth_kwargs" in video_main
    assert "**_mqtt_auth_kwargs()" in video_main
    assert "**auth" in video_events


# ── وظيفيّ (معزول في عمليّة فرعيّة لتفادي تصادم أسماء الحزم بين الخدمتَين) ──
_ACTUATOR_SNIPPET = """
import sys
sys.path.insert(0, "services/actuator-service")
import actuator_runtime as a
a.MQTT_USERNAME = ""
assert a._mqtt_auth_kwargs() == {}, a._mqtt_auth_kwargs()
a.MQTT_USERNAME, a.MQTT_PASSWORD = "svc", "secret"
assert a._mqtt_auth_kwargs() == {"username": "svc", "password": "secret"}, a._mqtt_auth_kwargs()
print("OK")
"""

_VIDEO_SNIPPET = """
import os, sys
sys.path.insert(0, "services/video-processor")
import main as m
os.environ.pop("MQTT_USERNAME", None)
assert m._mqtt_auth_kwargs() == {}, m._mqtt_auth_kwargs()
os.environ["MQTT_USERNAME"], os.environ["MQTT_PASSWORD"] = "svc", "secret"
assert m._mqtt_auth_kwargs() == {"username": "svc", "password": "secret"}, m._mqtt_auth_kwargs()
print("OK")
"""


def _run_isolated(snippet: str) -> None:
    res = subprocess.run(
        [sys.executable, "-c", snippet], cwd=str(ROOT), capture_output=True, text=True
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    assert "OK" in res.stdout, res.stdout


def test_actuator_auth_kwargs_helper() -> None:
    pytest.importorskip("aiomqtt", reason="actuator_runtime import pulls aiomqtt")
    pytest.importorskip("fastapi", reason="actuator_runtime import pulls fastapi")
    _run_isolated(_ACTUATOR_SNIPPET)


def test_video_auth_kwargs_helper() -> None:
    pytest.importorskip("aiomqtt", reason="video main import pulls aiomqtt")
    pytest.importorskip("fastapi", reason="video main import pulls fastapi")
    _run_isolated(_VIDEO_SNIPPET)
