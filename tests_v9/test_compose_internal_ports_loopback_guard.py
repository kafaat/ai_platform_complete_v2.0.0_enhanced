"""حارس CI (SEC-1 / HIGH-DOCKER-01): حصر منافذ الخدمات الداخليّة على loopback.

الخلفيّة: ``docker-compose.light.yml`` كان يكشف خدمات التطبيق الداخليّة (auth، supervisor،
mcp، guardrails، edge-inference، video-processor، actuator) على كلّ واجهات المضيف
(``ports: ["8120:8000"]`` ⇒ 0.0.0.0)، بينما مخازن بياناته محصورة أصلاً على 127.0.0.1.
أيّ منفذ بلا بادئة ``127.0.0.1:`` يُنشَر على كلّ الواجهات ⇒ سطح هجوم غير مقصود.

هذا الاختبار فحص ملفّات نقيّ (بلا Docker، بلا yaml، بلا fastapi): يمسح
``docker-compose.light.yml`` ويؤكّد أنّ كلّ خدمة *داخليّة* تنشر منافذها على 127.0.0.1 فقط.
الخدمات العامّة عمداً (بوّابة nginx + خدمات الحافة edge) مُدرَجة في قائمة سماح صريحة أدناه؛
أيّ خدمة داخليّة جديدة/مُعدَّلة تكشف منفذاً على كلّ الواجهات تُفشِل الاختبار.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# جذر المستودع (هذا الملفّ في tests_v9/ تحت الجذر مباشرةً).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# ملفّ الهدف: التركيب الخفيف. (v9.yml القانونيّ محروس على حدة ولا يُمَسّ هنا.)
_TARGET = "docker-compose.light.yml"

# قائمة سماح: خدمات يُسمَح لها بنشر منافذ على كلّ الواجهات (0.0.0.0) لأنّها عامّة عمداً.
#   • nginx      — بوّابة الحافة العكسيّة (80/443) هي نقطة الدخول العامّة الوحيدة للتطبيق
#                  (None ⇒ كامل الخدمة عامّ).
#   • fastbee    — وسيط IoT/MQTT للحافة: منفذ MQTT 1883 فقط عامّ (عتاد ميدانيّ خارج المضيف).
#   • zlmediakit — خادم وسائط للحافة: RTSP 554 + WebRTC 10000/udp فقط عامّان (بثّ الكاميرات).
# SEC-4: fastbee/zlmediakit ليستا عامّتَين بالكامل — منفذ الإدارة HTTP (8081/8082) يجب أن يبقى
# على 127.0.0.1 فقط. أيّ منفذ *غير* مُدرَج هنا (منفذ إدارة جديد مثلاً) يُعامَل معاملة داخليّة.
# القيمة = مجموعة منافذ المضيف العامّة المسموح بها لهذه الخدمة (None ⇒ كامل الخدمة عامّ).
_PUBLIC_PORT_ALLOWLIST: dict[str, frozenset[str] | None] = {
    "nginx": None,
    "fastbee": frozenset({"1883"}),
    "zlmediakit": frozenset({"554", "10000"}),
}
# أسماء الخدمات العامّة (للتحقّق من عدم قِدَم القائمة في test_target_compose_parsed).
_PUBLIC_ALLOWLIST = frozenset(_PUBLIC_PORT_ALLOWLIST)


def _host_port(port_spec: str) -> str:
    """أعِد منفذ المضيف المنشور من سلسلة منفذ.

    يدعم ``HOST:CONTAINER`` و``IP:HOST:CONTAINER`` (مثل ``127.0.0.1:8081:8080``)
    مع لاحقة بروتوكول اختياريّة (``/udp``). منفذ المضيف هو الحقل قبل الأخير."""
    fields = port_spec.strip().split(":")
    host = fields[-2] if len(fields) >= 2 else fields[0]
    return host.split("/", 1)[0].strip()


_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$")
_TOPLEVEL_RE = re.compile(r"^[A-Za-z]")
_PORTS_INLINE_RE = re.compile(r"^    ports:\s*(.*)$")
_BLOCK_ITEM_RE = re.compile(r"^      -\s*(.*)$")


def _strip_scalar(raw: str) -> str:
    """أزِل الاقتباس والتعليق اللاحق من قيمة منفذ في YAML."""
    v = raw.strip()
    if v and v[0] in "\"'":
        # سلسلة مقتبسة: التقط حتى الاقتباس المُغلِق.
        m = re.match(r"""(["'])(.*?)\1""", v)
        if m:
            return m.group(2)
    # غير مقتبسة: اقطع أيّ تعليق لاحق.
    return v.split("#", 1)[0].strip()


def _service_ports(text: str) -> dict[str, list[str]]:
    """أعِد خريطة {اسم الخدمة: [سلاسل المنافذ المنشورة]} من نصّ compose (فحص نصّيّ نقيّ)."""
    lines = text.splitlines()
    result: dict[str, list[str]] = {}
    in_services = False
    current: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^services:\s*$", line):
            in_services = True
            i += 1
            continue
        if not in_services:
            i += 1
            continue
        svc = _SERVICE_RE.match(line)
        if svc:
            current = svc.group(1)
            result.setdefault(current, [])
            i += 1
            continue
        if _TOPLEVEL_RE.match(line):
            # مفتاح جذريّ جديد (بلا إزاحة) ⇒ انتهى قسم services.
            in_services = False
            current = None
            i += 1
            continue
        if current is not None:
            pm = _PORTS_INLINE_RE.match(line)
            if pm:
                rest = pm.group(1).strip()
                if rest.startswith("["):
                    # اقرأ داخل [...] فقط — تجاهل أيّ تعليق لاحق قد يحوي "منافذ" وهميّة.
                    bracket = rest[rest.index("[") + 1 : rest.rindex("]")]
                    for q in re.findall(r'"([^"]*)"|\'([^\']*)\'', bracket):
                        result[current].append(q[0] or q[1])
                    i += 1
                    continue
                # صيغة الكتلة: اجمع بنود "- ..." التالية.
                j = i + 1
                while j < len(lines):
                    bm = _BLOCK_ITEM_RE.match(lines[j])
                    if not bm:
                        break
                    result[current].append(_strip_scalar(bm.group(1)))
                    j += 1
                i = j
                continue
        i += 1
    return result


def _internal_port_cases() -> list[tuple[str, str]]:
    """كلّ (اسم خدمة، سلسلة منفذ) يجب أن يُحصَر على loopback في الملفّ الهدف.

    الخدمات الداخليّة: كلّ منافذها. خدمات قائمة السماح العامّة: فقط المنافذ *غير*
    المُدرَجة صراحةً كعامّة (منافذ الإدارة الجديدة مثلاً) — أمّا منافذها العامّة المقصودة
    (MQTT/RTSP/WebRTC، أو كامل nginx) فتُستثنى. أيّ منفذ داخليّ يُنشَر على كلّ الواجهات يُفشِل."""
    path = _REPO_ROOT / _TARGET
    if not path.exists():
        return []
    out: list[tuple[str, str]] = []
    for name, ports in _service_ports(path.read_text(encoding="utf-8")).items():
        allowed = _PUBLIC_PORT_ALLOWLIST.get(name, frozenset())
        if allowed is None:  # كامل الخدمة عامّ (nginx).
            continue
        for p in ports:
            # منفذ عامّ مقصود (مُدرَج صراحةً) ⇒ لا يُفحَص؛ خلاف ذلك يجب أن يكون loopback.
            if _host_port(p) in allowed and not p.startswith("127.0.0.1:"):
                continue
            out.append((name, p))
    return out


@pytest.mark.unit
def test_target_compose_parsed():
    """تحقّق سلامة التحليل: الملفّ موجود وله خدمات ذات منافذ منشورة (وإلّا فالحارس أعمى)."""
    path = _REPO_ROOT / _TARGET
    assert path.exists(), f"{_TARGET} مفقود — الحارس يفترض وجوده."
    ports_map = _service_ports(path.read_text(encoding="utf-8"))
    assert any(ports_map.values()), (
        f"لم يُستخرَج أيّ منفذ من {_TARGET} — المحلّل النصّيّ مكسور أو تغيّر التنسيق."
    )
    # قائمة السماح ليست stale: كلّ اسم فيها خدمةٌ فعليّة في الملفّ.
    for name in _PUBLIC_ALLOWLIST:
        assert name in ports_map, (
            f"خدمة قائمة السماح '{name}' غير موجودة في {_TARGET} — نظّف القائمة."
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "svc_name,mgmt_host_port",
    [("fastbee", "8081"), ("zlmediakit", "8082")],
)
def test_edge_mgmt_http_port_bound_loopback(svc_name, mgmt_host_port):
    """SEC-4: the edge services' HTTP MANAGEMENT ports must be loopback-only.

    fastbee/zlmediakit are public for their line protocols (MQTT/RTSP/WebRTC) but their
    admin HTTP ports (8081/8082) are not — a regression that re-exposes them on all
    interfaces must fail here even though the service is otherwise allowlisted."""
    path = _REPO_ROOT / _TARGET
    ports = _service_ports(path.read_text(encoding="utf-8")).get(svc_name, [])
    mgmt = [p for p in ports if _host_port(p) == mgmt_host_port]
    assert mgmt, f"{_TARGET}:{svc_name} لا ينشر منفذ الإدارة {mgmt_host_port} — تغيّر التنسيق؟"
    for p in mgmt:
        assert p.startswith("127.0.0.1:"), (
            f"{_TARGET}:{svc_name} يكشف منفذ الإدارة '{p}' على كلّ الواجهات. "
            "احصره على 127.0.0.1: (منفذ إدارة HTTP داخليّ)."
        )


@pytest.mark.unit
@pytest.mark.parametrize("svc_name,port", _internal_port_cases())
def test_internal_service_ports_bound_loopback(svc_name, port):
    """كلّ منفذ لخدمة داخليّة يجب أن يُنشَر على 127.0.0.1 فقط (لا 0.0.0.0)."""
    assert port.startswith("127.0.0.1:"), (
        f"{_TARGET}:{svc_name} يكشف المنفذ '{port}' على كلّ الواجهات (0.0.0.0). "
        "احصره على 127.0.0.1: (خدمة داخليّة)، أو أضِفه لقائمة السماح العامّة صراحةً "
        "إن كان يحتاج كشفاً عامّاً (edge)."
    )
