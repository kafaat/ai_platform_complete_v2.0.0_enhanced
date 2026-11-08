"""S8 — حدّ bcrypt ذو الـ٧٢ بايت: 422 للمدخل الجديد، و401 (لا 500) عند الدخول.

bcrypt ٥.٠.٠ يرمي ``ValueError`` لكلمة مرور > ٧٢ بايت، بينما النماذج تحدّ بـ١٢٨ **محرفاً**
(٣٧ محرفاً عربيّاً = ٧٤ بايت). على origin/main cc0d2e295 كان ذلك HTTP 500 في
التسجيل/الدخول/الاستعادة (مقيس). يُشغَّل كلّ فحص في عمليّة فرعيّة بـcwd=services/auth كي
لا يصطدم ``import main`` بوحدات ``main`` لخدمات أخرى (نمط test_auth_service).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import TEST_JWT_SECRET

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "services" / "auth"

# ٣٧ محرفاً عربيّاً (٧٤ بايت) + "Aa1!" ⇒ ٤١ محرفاً (≤ ١٢٨) لكن ٧٨ بايت (> ٧٢).
LONG_PW = "كلمة" * 9 + "ك" + "Aa1!"
OK_PW = "Aa1!" + "x" * 68  # ٧٢ بايت تماماً — الحدّ المسموح


def _run(script: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=AUTH,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "JWT_SECRET": TEST_JWT_SECRET,
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.splitlines()[-1])


def test_fixture_password_is_within_char_limit_but_over_byte_limit():
    assert len(LONG_PW) <= 128 and len(LONG_PW.encode()) > 72
    assert len(OK_PW.encode()) == 72


def test_new_password_models_reject_over_72_bytes_with_clear_message():
    out = _run(
        f"""
import json
import main
from pydantic import ValidationError
LONG, OK = {LONG_PW!r}, {OK_PW!r}
cases = {{
    "RegisterRequest": dict(email="a@b.ye", full_name="Ali", password=None),
    "PasswordResetConfirm": dict(token="t" * 20, new_password=None),
    "ChangePasswordRequest": dict(current_password="x", new_password=None),
    "InvitationAcceptRequest": dict(token="t" * 20, full_name="Ali", password=None),
}}
res = {{}}
for cls, kw in cases.items():
    field = "new_password" if "new_password" in kw else "password"
    model = getattr(main, cls)
    model(**{{**kw, field: OK}})  # الحدّ نفسه مقبول
    try:
        model(**{{**kw, field: LONG}})
        res[cls] = "accepted"
    except ValidationError as e:
        res[cls] = str(e)
print(json.dumps(res))
"""
    )
    for cls, msg in out.items():
        assert msg != "accepted", f"{cls} قبل كلمة مرور > ٧٢ بايت (bcrypt ٥ ⇒ 500)"
        assert "72" in msg, f"{cls}: رسالة الرفض لا تذكر الحدّ: {msg}"


def test_hash_and_verify_never_raise_on_over_long_input():
    out = _run(
        f"""
import json
import main
LONG, OK = {LONG_PW!r}, {OK_PW!r}
h = main.hash_password(OK, 4)
res = {{
    "ok": main.verify_password(OK, h),
    "ok_bytes_hash": main.verify_password(OK, h.encode()),
    "wrong": main.verify_password(OK[:-1] + "y", h),
    "long": main.verify_password(LONG, h),
    "malformed": main.verify_password(OK, "not-a-bcrypt-hash"),
    "none": main.verify_password(OK, None),
}}
try:
    main.hash_password(LONG, 4)
    res["hash_long"] = "hashed"
except ValueError as e:
    res["hash_long"] = str(e)
print(json.dumps(res))
"""
    )
    assert out["ok"] is True and out["ok_bytes_hash"] is True
    assert out["wrong"] is False
    assert out["long"] is False
    assert out["malformed"] is False and out["none"] is False
    assert "72" in out["hash_long"]


def test_login_with_over_long_password_is_401_not_500():
    out = _run(
        f"""
import json
from contextlib import asynccontextmanager
import bcrypt
import main
from fastapi.testclient import TestClient

# تجزئة قائمة كما يخزّنها الإصدار السابق (توافق التجزئات) — مستقلّة عن الإصلاح.
stored = bcrypt.hashpw({OK_PW!r}.encode(), bcrypt.gensalt(4)).decode()
row = {{"id": 1, "email": "a@b.ye", "password_hash": stored, "role": "owner",
        "full_name": "Ali", "tenant_id": None, "active": True, "mfa_enabled": False,
        "mfa_secret": None, "encrypted_mfa_secret": None, "mfa_failed_attempts": 0,
        "mfa_locked_until": None}}

class Conn:
    async def fetchrow(self, *a, **k):
        return row

@asynccontextmanager
async def fake_acquire():
    yield Conn()

async def noop(*a, **k):
    return 0

main._acquire = fake_acquire
main.check_ip_rate = noop
main.check_lockout = noop
main.record_failed_login = noop
client = TestClient(main.app, raise_server_exceptions=False)
r = client.post("/v1/auth/login", json={{"email": "a@b.ye", "password": {LONG_PW!r}}})
ok = client.post("/v1/auth/login", json={{"email": "a@b.ye", "password": {OK_PW!r}}})
print(json.dumps({{"status": r.status_code, "ok_status": ok.status_code}}))
"""
    )
    assert out["status"] == 401, out
    # التجزئة القائمة تبقى صالحة: كلمة المرور الصحيحة تتجاوز فحص bcrypt (لا 401/500).
    assert out["ok_status"] not in (401, 500), out
