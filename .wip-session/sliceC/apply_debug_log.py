"""Slice C: SAHOOL_DEBUG state becomes visible in the startup log (state only, never a value)."""
import pathlib, sys
root = pathlib.Path(sys.argv[1])
p = root / "services/sahool-platform/api/routers/readiness.py"
s = p.read_text(encoding="utf-8")
old = '''import os

from core.prod_readiness import evaluate_readiness
from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission

router = APIRouter()
'''
new = '''import logging
import os

from core.prod_readiness import _truthy, evaluate_readiness
from fastapi import APIRouter, Depends

from api.main import Permission, UserSchema, require_permission

router = APIRouter()

# SAHOOL-DEBUG-FLAG-INVISIBLE-AT-RUNTIME-01: دخولُ dev يُسجِّل تحذيراً عند الإقلاع
# (`main.py:165`) فتُقاس حالتُه من سجلّ Railway بلا قراءة القيم؛ و`SAHOOL_DEBUG` لم يكن
# يُسجِّل شيئاً فلا تُقاس حالتُه إلّا من اللوحة. سطرٌ واحد عند الاستيراد (والموجِّهُ يُستورَد
# عند الإقلاع) يُسجِّل **الحالةَ لا القيمة**. `main.py` عند سقف أسطره، فالسطرُ هنا.
DEBUG_FLAG_STATE = "on" if _truthy(os.environ.get("SAHOOL_DEBUG")) else "off"
logging.getLogger(__name__).warning("SAHOOL_DEBUG=%s", DEBUG_FLAG_STATE)
'''
assert s.count(old) == 1, "readiness.py header changed"
p.write_text(s.replace(old, new), encoding="utf-8")

t = root / "services/sahool-platform/tests/test_debug_flag_startup_log.py"
t.write_text('''"""SAHOOL-DEBUG-FLAG-INVISIBLE-AT-RUNTIME-01 — حالةُ SAHOOL_DEBUG تظهر في سجلّ الإقلاع."""

from __future__ import annotations

import importlib
import logging

import pytest

pytestmark = pytest.mark.unit


def _reload_readiness(monkeypatch, caplog, value):
    if value is None:
        monkeypatch.delenv("SAHOOL_DEBUG", raising=False)
    else:
        monkeypatch.setenv("SAHOOL_DEBUG", value)
    import api.routers.readiness as readiness

    with caplog.at_level(logging.WARNING, logger=readiness.__name__):
        caplog.clear()
        readiness = importlib.reload(readiness)
    return readiness, [r.getMessage() for r in caplog.records if r.name == readiness.__name__]


@pytest.mark.parametrize(
    ("value", "state"), [("1", "on"), ("true", "on"), ("0", "off"), ("", "off"), (None, "off")]
)
def test_the_startup_log_states_the_debug_flag(monkeypatch, caplog, value, state) -> None:
    """الصفرُ مُميَّزٌ عن الغياب: السطرُ يُكتب في الحالتين، فغيابُه يعني أنّ الموجِّه لم يُستورَد."""
    readiness, messages = _reload_readiness(monkeypatch, caplog, value)
    assert readiness.DEBUG_FLAG_STATE == state
    assert messages == [f"SAHOOL_DEBUG={state}"]


def test_the_log_line_never_carries_the_raw_value(monkeypatch, caplog) -> None:
    _, messages = _reload_readiness(monkeypatch, caplog, "yes-secret-looking-value")
    assert messages == ["SAHOOL_DEBUG=off"]
    assert all("secret" not in m for m in messages)
''', encoding="utf-8")
print("applied")
