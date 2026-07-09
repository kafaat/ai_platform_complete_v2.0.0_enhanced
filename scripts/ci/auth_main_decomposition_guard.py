#!/usr/bin/env python3
"""Guard the auth-service main.py decomposition boundary.

Auth is security-sensitive. main.py may remain the compatibility shell that
re-exports symbols for decomposed routers, but MFA runtime logic must not creep
back into the bootstrap file.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "services" / "auth"
MAIN = AUTH / "main.py"
MFA_RUNTIME = AUTH / "mfa_runtime.py"
MAX_MAIN_LOC = 1050
REQUIRED_RUNTIME_FUNCS = {
    "_ip_hash",
    "_emit_mfa_audit",
    "_store_recovery_codes",
    "_consume_recovery_code",
    "_register_mfa_failure",
    "_mfa_reset_and_maybe_migrate",
    "_consume_totp_step",
    "mfa_login_verify",
    "_verify_caller_mfa",
}


def fail(msg: str) -> None:
    print(f"auth_main_decomposition_guard_failed: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    main_src = MAIN.read_text(encoding="utf-8")
    runtime_src = MFA_RUNTIME.read_text(encoding="utf-8") if MFA_RUNTIME.exists() else ""
    loc = len(main_src.splitlines())
    if loc > MAX_MAIN_LOC:
        fail(f"services/auth/main.py LOC {loc} exceeds {MAX_MAIN_LOC}; keep runtime logic decomposed")
    if not MFA_RUNTIME.exists():
        fail("services/auth/mfa_runtime.py missing")
    for name in sorted(REQUIRED_RUNTIME_FUNCS):
        if not re.search(rf"^async def {re.escape(name)}\b|^def {re.escape(name)}\b", runtime_src, re.M):
            fail(f"mfa_runtime.py missing {name}")
        if name not in main_src:
            fail(f"main.py no longer re-exports/references {name}; routers expect main.{name}")
    if re.search(r"^async def _verify_caller_mfa\b", main_src, re.M):
        fail("_verify_caller_mfa implementation drifted back into main.py")
    if re.search(r"^async def mfa_login_verify\b", main_src, re.M):
        fail("mfa_login_verify implementation drifted back into main.py")
    if "from mfa_runtime import" not in main_src:
        fail("main.py must import/re-export MFA helpers from mfa_runtime")
    if "def _main():" not in runtime_src or "import main" not in runtime_src:
        fail("mfa_runtime must use lazy main import to preserve router compatibility without eager cycles")
    print("✓ auth main decomposition guard passed")


if __name__ == "__main__":
    main()
