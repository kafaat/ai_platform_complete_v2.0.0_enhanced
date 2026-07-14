"""حارس موحّد: كل عنوان خدمة داخليّ (sahool-*) في الكود يطابق خدمة compose واسمها ومنفذها.

خلفيّة (تدقيق البوّابة/انحراف العناوين — P0): وُجِدت افتراضات عناوين خدمات وهميّة أو
بمنافذ خاطئة مخبّأة خلف overrides (decision-service:8090/8007، sahool-tts، sahool-supervisor،
sahool-weather-service:8092، sahool-edge:8000، sahool-zlmediakit:8080). أيّ منها يفشل صامتاً
عند غياب env override.

الحارس يجمع أسماء الخدمات ومنافذها الداخليّة من كلّ ملفّات ``docker-compose*.yml`` (v9 +
overlays) ويمسح ``services/`` و``bots/`` و``agents/`` عن كلّ سلسلة ``http://sahool-<svc>:<port>``:
  * الاسم يجب أن يكون خدمة compose معروفة (يمنع invalid_host).
  * المنفذ يجب أن يطابق المنفذ الداخليّ للخدمة حين نستطيع اشتقاقه (يمنع wrong_port).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

# مضيفات خدمات معروفة خارج compose الأساسيّ (بنية تحتيّة أو تكامل خارجيّ اختياريّ مقبول).
_KNOWN_EXTRA_HOSTS = {
    "sahool-nats",
    "sahool-redis",
    "sahool-postgres",
    "sahool-qdrant",
    "sahool-frontend",
    # تكامل ERPNext خارجيّ اختياريّ: ليس خدمة runtime في v9. مزوّد ERP fail-closed
    # (بلا مفاتيح ⇒ NullProvider) فلا يتّصل بمضيف وهميّ؛ العنوان placeholder يُضبَط
    # لكلّ نشر عبر ERPNEXT_URL. مسموح به صراحةً كي لا يُعَدّ انحرافاً.
    "sahool-erpnext",
}


def _load_compose_services() -> tuple[set[str], dict[str, int]]:
    names: set[str] = set(_KNOWN_EXTRA_HOSTS)
    ports: dict[str, int] = {}
    for comp in ROOT.glob("docker-compose*.yml"):
        try:
            doc = yaml.safe_load(comp.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for name, spec in (doc.get("services") or {}).items():
            names.add(name)
            if name in ports or not isinstance(spec, dict):
                continue
            # 1) منفذ الفحص الصحّيّ: localhost:PORT أو :PORT/health.
            hc = str(spec.get("healthcheck", {}))
            m = re.search(r"(?:localhost|127\.0\.0\.1):(\d{2,5})", hc)
            if m:
                ports[name] = int(m.group(1))
                continue
            # 2) الجانب الداخليّ من تعيين المنافذ (HOST:CONTAINER[/proto]).
            for p in spec.get("ports", []) or []:
                mm = re.match(r"^(?:[\d.]+:)?\d+:(\d+)", str(p))
                if mm:
                    ports[name] = int(mm.group(1))
                    break
    return names, ports


_URL_RE = re.compile(r"http://(sahool-[a-z0-9-]+):(\d+)")


def _scan_code() -> list[tuple[str, int, str, int]]:
    hits: list[tuple[str, int, str, int]] = []
    for base in ("services", "bots", "agents"):
        for p in (ROOT / base).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                # تجاهل أسطر التعليقات النقيّة كي لا نمنع أمثلة توضيحيّة.
                if line.lstrip().startswith("#"):
                    continue
                for m in _URL_RE.finditer(line):
                    hits.append((str(p.relative_to(ROOT)), i, m.group(1), int(m.group(2))))
    return hits


def _scan_compose_env() -> list[tuple[str, str, str, int]]:
    """يمسح قيَم ``environment`` في كلّ ملفّات compose عن ``http://sahool-<svc>:<port>``.

    الثغرة التي فاتت (تدقيق الحاويات V21 §3.1): كان الحارس يمسح الكود فقط، فمرّ
    ``WEATHER_SERVICE_URL: ...weather-service:8092`` في افتراض compose لعامل دفتر
    المياه (المنفذ الصحيح 8000). نمسح الآن افتراضات compose ذاتها.
    """
    # نطاق: ملفّ الإنتاج المُشهَّد ``docker-compose.v9.yml`` فقط (ما فحصه التدقيق).
    # طبقات overlay البديلة (unified/light) لها تسمية خدمات مختلفة وتُدقَّق منفصلةً.
    hits: list[tuple[str, str, str, int]] = []
    for comp in [ROOT / "docker-compose.v9.yml"]:
        if not comp.exists():
            continue
        try:
            doc = yaml.safe_load(comp.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        for svc, spec in (doc.get("services") or {}).items():
            if not isinstance(spec, dict):
                continue
            env = spec.get("environment")
            # environment قد تكون dict {KEY: val} أو list ["KEY=val"].
            values: list[str] = []
            if isinstance(env, dict):
                values = [str(v) for v in env.values()]
            elif isinstance(env, list):
                values = [str(v) for v in env]
            for val in values:
                for m in _URL_RE.finditer(val):
                    hits.append((str(comp.relative_to(ROOT)), svc, m.group(1), int(m.group(2))))
    return hits


def test_no_compose_env_endpoint_drift() -> None:
    """افتراضات compose (environment) لا تحمل مضيفاً وهميّاً أو منفذاً خاطئاً.

    مرآة لحارس الكود لكن على compose نفسه — يقفل صنف الانحراف الذي مرّ في افتراض
    عامل دفتر المياه (weather-service:8092 بدل :8000).
    """
    names, ports = _load_compose_services()
    invalid_host: list[str] = []
    wrong_port: list[str] = []
    for comp, svc, host, port in _scan_compose_env():
        if host not in names:
            invalid_host.append(f"{comp} [{svc}] -> {host}:{port} (unknown service)")
            continue
        expected = ports.get(host)
        if expected is not None and port != expected:
            wrong_port.append(f"{comp} [{svc}] -> {host}:{port} (expected :{expected})")

    problems = invalid_host + wrong_port
    assert not problems, "compose environment endpoint drift:\n" + "\n".join(problems)


def test_no_internal_service_endpoint_drift() -> None:
    names, ports = _load_compose_services()
    assert "sahool-decision-service" in names, "compose parse sanity failed"

    invalid_host: list[str] = []
    wrong_port: list[str] = []
    for path, line, host, port in _scan_code():
        if host not in names:
            invalid_host.append(f"{path}:{line} -> {host}:{port} (unknown service)")
            continue
        expected = ports.get(host)
        if expected is not None and port != expected:
            wrong_port.append(f"{path}:{line} -> {host}:{port} (expected :{expected})")

    problems = invalid_host + wrong_port
    assert not problems, "internal service endpoint drift:\n" + "\n".join(problems)
