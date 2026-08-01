"""حارس ساكن لبوّابة إدخال المواسم في nginx (SEASON-RECORD-ENTRY-01 شريحة 3b-infra).

نموذج الثقة الحسّاس يُبنى في ``nginx/nginx.v9.conf`` — لا يمكن تشغيل nginx في طبقة الوحدة،
لكن نُثبّت الأسلاك **نصّيّاً** كي لا تنحدر صامتةً (تعديل خاطئ يفتح ثغرة عزل/انتحال):

  ① مصدر قانونيّ **واحد** مُعلَن: ``map $request_uri $season_canonical_path`` — نفس المتغيّر
     يُغذّي X-Canonical-Path لـauth **و** هدف proxy_pass للـupstream، فلا يختلفان (شرط ②).
  ② القبول (حسّاس) خلف ``auth_request /_auth_edge_sign`` الذي يوقّع تصديق حافّة مقيَّد الوجهة؛
     البوّابة تولّد X-Canonical-Method/Path وتُلغي أيّ قيمة من العميل (شرط ③ — البرهان الحيّ
     الوحيد يتطلّب nginx مُشغَّلاً؛ هنا نُثبّت أنّ البوّابة **تكتبها بنفسها** فتَطمِس المزوَّرة).
  ③ ترويسات التصديق (X-User-Id/X-Roles/X-Edge-*) تُرفَع من ردّ auth بـ``auth_request_set``
     وتُمرَّر upstream — لا تُقبَل من العميل (تُمسَح صراحةً في المسار العامّ).
  ④ توكن الخدمة المخصّص يُحقَن خادميّاً في كلا مساري المواسم (لا يصل من العميل).
  ⑤ القانونيّة لا تُسرَّب للـupstream — الخدمة تحسب method/path من طلبها المُستلَم (شرط ①).

وحدة صرفة — ``pytest -m unit`` (نصّ، لا شبكة/nginx).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CONF = Path(__file__).resolve().parents[1] / "nginx" / "nginx.v9.conf"


def _conf() -> str:
    return _CONF.read_text(encoding="utf-8")


def _location_body(conf: str, header_regex: str) -> str:
    """استخرج جسم كتلة ``location`` مُتوازِنة الأقواس ابتداءً من ترويسة تطابق header_regex."""
    m = re.search(header_regex, conf)
    assert m, f"location header not found: {header_regex}"
    i = conf.index("{", m.start())
    depth = 0
    for j in range(i, len(conf)):
        if conf[j] == "{":
            depth += 1
        elif conf[j] == "}":
            depth -= 1
            if depth == 0:
                return conf[i + 1 : j]
    raise AssertionError(f"unbalanced braces after {header_regex}")


def test_single_declared_canonical_source_map() -> None:
    """① مصدر واحد: map على $request_uri الأصليّ (ثابت عبر الطلبات الفرعيّة، عكس $uri)."""
    conf = _conf()
    assert re.search(r"map\s+\$request_uri\s+\$season_canonical_path\s*\{", conf), (
        "missing single-source map $request_uri -> $season_canonical_path"
    )
    # المسار الداخليّ بعد rewrite (/internal/seasons...) — لا يُسرَّب المسار العامّ للـupstream.
    assert "/internal/seasons" in conf


def test_scout_ingest_upstream_declared() -> None:
    conf = _conf()
    assert re.search(
        r"upstream\s+scout_ingest_backend\s*\{\s*server\s+sahool-scout-ingest:8000", conf
    ), "missing scout_ingest_backend upstream -> sahool-scout-ingest:8000"


def test_edge_sign_subrequest_generates_canonical_and_strips_client() -> None:
    """② البوّابة تُصدِر X-Canonical-* بنفسها فتَطمِس أيّ قيمة عميل (شرط ③، طمس بنيويّ)."""
    body = _location_body(_conf(), r"location\s*=\s*/_auth_edge_sign\b")
    assert "internal;" in body, "edge-sign subrequest must be internal (client cannot reach it)"
    assert "proxy_pass http://auth_backend/v1/auth/edge-sign;" in body
    # الوجهة القانونيّة من المصدر الواحد (لا من العميل): method ثابت POST، path = المتغيّر.
    assert re.search(r'proxy_set_header\s+X-Canonical-Method\s+"POST"', body)
    assert re.search(r"proxy_set_header\s+X-Canonical-Path\s+\$season_canonical_path", body)
    # يُلغي (يُفرِغ) ترويسات هويّة/تصديق قد يرسلها العميل قبل توقيع auth (fail-closed للانتحال).
    for h in ("X-Tenant-Id", "X-User-Id", "X-Roles", "X-Edge-Attestation"):
        assert re.search(rf'proxy_set_header\s+{re.escape(h)}\s+""', body), h
    # اشتقاق التوكن داخل الطلب الفرعيّ (درس bug1: set في if بالأمّ لا يَنفُذ للفرعيّ).
    assert "$cookie_sahool_at" in body and "Authorization $fwd_auth" in body


def test_accept_location_edge_signed_and_lifts_attestation() -> None:
    """القبول: auth_request للتوقيع، auth_request_set يرفع التصديق، توكن خدمة، لا تسريب قانونيّة."""
    body = _location_body(_conf(), r"location\s+~\s+\^/api/v1/seasons/\[\^/\]\+/accept\$")
    assert "auth_request /_auth_edge_sign;" in body, "accept must gate on the edge-sign subrequest"
    assert "proxy_pass http://scout_ingest_backend$season_canonical_path" in body
    # ③ رفع ترويسات التصديق من ردّ auth (لا من العميل) وتمريرها upstream.
    for var in ("x_user_id", "x_roles", "x_edge_timestamp", "x_edge_attestation", "x_tenant_id"):
        assert f"$upstream_http_{var}" in body, var
    for h in ("X-User-Id", "X-Roles", "X-Edge-Timestamp", "X-Edge-Attestation", "X-Tenant-Id"):
        assert re.search(rf"proxy_set_header\s+{re.escape(h)}\s+\$", body), h
    # ④ توكن الخدمة يُحقَن خادميّاً (envsubst) — لا يصل من العميل.
    assert 'proxy_set_header X-Season-Entry-Token "${SEASON_ENTRY_SERVICE_TOKEN}";' in body
    # ⑤ القانونيّة لا تُسرَّب للـupstream (الخدمة تحسب method/path من طلبها — شرط ①).
    assert re.search(r'proxy_set_header\s+X-Canonical-Path\s+""', body)
    assert re.search(r'proxy_set_header\s+X-Canonical-Method\s+""', body)


def test_general_season_location_verifies_and_strips_all_trust() -> None:
    """بقيّة نقاط الموسم: تحقّق JWT + توكن خدمة، بلا سلطة مُراجِع (لا تُمرَّر ترويسات تصديق)."""
    body = _location_body(_conf(), r"location\s+~\s+\^/api/v1/seasons\b(?!/)")
    assert "auth_request /_auth_verify;" in body
    assert "proxy_pass http://scout_ingest_backend$season_canonical_path" in body
    assert 'proxy_set_header X-Season-Entry-Token "${SEASON_ENTRY_SERVICE_TOKEN}";' in body
    # لا قبول هنا ⇒ تُمسَح كلّ ترويسات الهويّة/التصديق من العميل (لا سلطة مُراجِع تُمرَّر).
    for h in (
        "X-User-Id",
        "X-Roles",
        "X-Edge-Attestation",
        "X-Edge-Timestamp",
        "X-Canonical-Path",
        "X-Canonical-Method",
    ):
        assert re.search(rf'proxy_set_header\s+{re.escape(h)}\s+""', body), h


def test_accept_location_precedes_general_location() -> None:
    """nginx يطابق regex بالترتيب — المسار الأضيق (accept) **قبل** العامّ وإلّا يُلتقَط بلا توقيع."""
    conf = _conf()
    accept = conf.index("/api/v1/seasons/[^/]+/accept")
    general = re.search(r"location\s+~\s+\^/api/v1/seasons\b(?!/)", conf)
    assert general and accept < general.start(), (
        "accept location must appear before the general one"
    )
