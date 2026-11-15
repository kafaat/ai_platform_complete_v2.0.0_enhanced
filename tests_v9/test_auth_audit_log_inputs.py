"""R-H3 (وحدة): مُدخَلات صفّ ``audit_log`` صالحةٌ لأعمدته قبل أن تبلغ القاعدة.

``ip_address`` عمودُ ``inet``: وسمٌ نصّيّ (``"authenticated"``/``"system"``) أو ``"unknown"``
كان يُسقط الصفّ كلّه، فضاعت أحداث تغيير كلمة المرور وMFA وإعادة التعيين. الشاهد الحيّ
للكتابة نفسها (RLS + المستأجِر) في ``test_auth_audit_log_live_pg.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

AUTH = Path(__file__).resolve().parents[1] / "services" / "auth"


def _client_address():
    if str(AUTH) not in sys.path:
        sys.path.insert(0, str(AUTH))
    import client_address

    return client_address


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("203.0.113.9", "203.0.113.9"),
        (" 2001:db8::1 ", "2001:db8::1"),
        ("authenticated", None),
        ("system", None),
        ("unknown", None),
        ("", None),
        (None, None),
    ],
)
def test_audit_inet_accepts_only_an_address(raw, expected):
    assert _client_address().audit_inet(raw) == expected


def test_no_auth_audit_call_passes_a_label_as_the_address():
    """لا موقع نداء يمرّر وسماً نصّيّاً حرفيّاً مكان العنوان (الوسيط الثالث)."""
    offenders: list[str] = []
    for path in sorted([AUTH / "main.py", *AUTH.glob("routers/*.py")]):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "audit_log" or len(node.args) < 3:
                continue
            ip = node.args[2]
            if isinstance(ip, ast.Constant) and isinstance(ip.value, str):
                offenders.append(f"{path.name}:{node.lineno} ip={ip.value!r}")
    assert not offenders, offenders
