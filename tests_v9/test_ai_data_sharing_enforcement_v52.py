"""حارس إنفاذ سياسة مشاركة البيانات (V52) — قبل إرسال سياق الحقل لمزوّد خارجيّ.

يُغلِق فجوة الإنفاذ التي رصدها تدقيق V51: تخزين مستوى المشاركة وحده لا يكفي — يجب أن
يُحجَب/يُنقَّح سياق الحقل فعليّاً للمزوّد السحابيّ حسب سياسة المستأجِر. منطق صرف، ``-m unit``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


GEN = _load("services/ai_agronomist/ai_generation.py", "sahool_ai_generation_enforce")

_EXTERNAL = GEN.GenConfig("openrouter", "http://x/chat/completions", {}, "m", "openai_chat")
_LOCAL = GEN.GenConfig("local", "http://x/v1/messages", {}, "m", "messages")
_CTX = "الحقل user@example.com عند 24.7136, 46.6753 معرّف 12345678-1234-1234-1234-123456789abc"


def test_local_provider_always_receives_full_context():
    for mode in ("local_only", "redacted_external", "full_external"):
        assert GEN.prepare_context_for_provider(_LOCAL, _CTX, {"data_sharing_level": mode}) == _CTX


def test_external_local_only_blocks_context():
    assert (
        GEN.prepare_context_for_provider(_EXTERNAL, _CTX, {"data_sharing_level": "local_only"})
        is None
    )
    # الافتراضيّ المتحفّظ: سياسة غائبة ⇒ حجب خارجيّ أيضاً.
    assert GEN.prepare_context_for_provider(_EXTERNAL, _CTX, None) is None
    assert GEN.prepare_context_for_provider(_EXTERNAL, _CTX, {}) is None


def test_external_redacted_strips_identifiers():
    out = GEN.prepare_context_for_provider(
        _EXTERNAL, _CTX, {"data_sharing_level": "redacted_external"}
    )
    assert out is not None
    assert "user@example.com" not in out and "[redacted-email]" in out
    assert "12345678-1234-1234-1234-123456789abc" not in out
    assert "46.6753" not in out  # الإحداثيّات مُنقَّحة


def test_external_full_passes_context():
    assert (
        GEN.prepare_context_for_provider(_EXTERNAL, _CTX, {"data_sharing_level": "full_external"})
        == _CTX
    )


def test_legacy_data_sharing_key_is_honored():
    """توافق رجعيّ: مفتاح ``data_sharing`` (صياغة قديمة) يُحترَم أيضاً."""
    assert GEN.prepare_context_for_provider(_EXTERNAL, _CTX, {"data_sharing": "local_only"}) is None


def test_redaction_bounds_payload_length():
    big = "x" * 20000
    assert len(GEN.redact_context_for_external(big)) <= 6000


def test_provider_snapshot_shape_no_secrets():
    snap = GEN.public_provider_snapshot()
    assert set(snap) >= {
        "generation_enabled",
        "provider",
        "provider_class",
        "available",
        "models",
        "data_sharing_modes",
    }
    assert snap["data_sharing_modes"] == ["local_only", "redacted_external", "full_external"]
    # لا تتسرّب أسرار في اللقطة.
    blob = repr(snap).lower()
    assert "api_key" not in blob and "authorization" not in blob
