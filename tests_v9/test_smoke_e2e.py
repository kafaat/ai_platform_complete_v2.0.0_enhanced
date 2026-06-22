"""غلاف integration لِسكربت scripts/smoke_e2e.py — يتخطّى تلقائياً حين غياب المكدّس الحيّ.

لا يُشغَّل في بوّابة الوحدات (مُعلَّم integration). يتطلّب مكدّس unified حيّاً
(postgis+redis+auth+sahool-platform+nginx) وضبط BASE_URL/AUTH_BASE. عند غياب الخدمات
يتخطّى بدل الفشل، فيبقى آمناً في أيّ تشغيل offline.
"""

from __future__ import annotations

import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "smoke_e2e.py"


def _stack_reachable() -> bool:
    base = os.getenv("BASE_URL") or os.getenv("AUTH_BASE")
    if not base:
        return False
    try:
        urllib.request.urlopen(base.rstrip("/") + "/auth/me", timeout=3)
    except urllib.error.HTTPError:
        return True  # استجاب (حتى 401/404) ⇒ الخدمة حيّة
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return True


@pytest.mark.integration
def test_smoke_e2e_against_live_stack():
    if not _stack_reachable():
        pytest.skip("لا مكدّس حيّ (اضبط BASE_URL/AUTH_BASE ووجّهه لمكدّس unified) — تخطٍّ.")
    assert _SCRIPT.exists(), f"السكربت مفقود: {_SCRIPT}"
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"فشل دخان E2E (خرج={result.returncode}).\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
