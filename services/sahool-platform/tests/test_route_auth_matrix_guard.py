"""حارس مصفوفة التفويض (#4، تدقيق 2026-07-05): يكمّل حارس المُطفِّرة القائم بقفل
مجموعة القراءات العامّة على allowlist مُراجَع — كي لا تصبح قراءةٌ لبيانات مستأجِر
عامّةً بصمت. أيّ GET عامّ جديد غير موثَّق يُفشِل الاختبار (قرار واعٍ لا انزلاق).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

pytestmark = pytest.mark.unit

CORE = os.path.join(os.path.dirname(__file__), "..")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import api.main as m  # noqa: E402

_AUTH_FNS = {"get_current_user", "_require_service_token", "require_permission", "require_role"}
_ALLOWLIST = os.path.join(os.path.dirname(__file__), "_public_read_allowlist.json")


def _walk(dep, acc):
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", "") in _AUTH_FNS:
        acc.add(call.__name__)
    for sub in getattr(dep, "dependencies", []):
        _walk(sub, acc)


def _public_reads() -> set[str]:
    out = set()
    for route in m.app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" not in methods or not path.startswith("/api/v1"):
            continue
        dep = getattr(route, "dependant", None)
        acc: set[str] = set()
        if dep is not None:
            _walk(dep, acc)
        if "get_current_user" not in acc and "_require_service_token" not in acc:
            out.add(path)
    return out


def test_public_reads_match_reviewed_allowlist():
    """لا قراءة عامّة جديدة بلا مراجعة — allowlist يُوثّق كلّ GET بلا مصادقة."""
    allow = set(json.load(open(_ALLOWLIST, encoding="utf-8"))["public_reads"])
    live = _public_reads()
    new_public = sorted(live - allow)
    assert not new_public, (
        "قراءات عامّة جديدة (GET بلا مصادقة) — راجِعها: إن كانت مرجعيّة أضِفها إلى "
        "_public_read_allowlist.json، وإلّا أضِف Depends(get_current_user):\n  "
        + "\n  ".join(new_public)
    )
