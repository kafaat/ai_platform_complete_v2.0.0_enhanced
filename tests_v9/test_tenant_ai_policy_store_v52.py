"""حارس حوكمة الذكاء الدائمة للمستأجِر (V52 — Track B).

يتحقّق من:
1. توافق ``TenantPolicyStore`` الرجعيّ (get/set كما قبل V52) + الإدامة عبر حاقن.
2. تطبيع مستوى مشاركة البيانات إلى قيمة قانونيّة (الافتراضيّ ``local_only``).
3. تطابق مستويات المشاركة بين ``tenant_policies`` و``shared/ai/provider_contract``.
4. وجود ترحيل ``v124_tenant_ai_policies`` بأعمدته المطلوبة + إدراجه في MANIFEST.

اختبارات منطق صرف بلا قاعدة بيانات (تُجمَّع تحت ``-m unit``).
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


TP = _load("services/ai_agronomist/tenant_policies.py", "sahool_tenant_policies_under_test")
CONTRACT = _load("shared/ai/provider_contract.py", "sahool_provider_contract_for_tp")


def test_store_backward_compatible_defaults_to_empty():
    """مستأجِر مجهول ⇒ ``{}`` (يحفظ سلوك السماح عند تفعيل الراية العامّة)."""
    store = TP.TenantPolicyStore()
    assert store.get_policy("unknown-tenant") == {}


def test_set_policy_normalizes_and_caches():
    store = TP.TenantPolicyStore()
    store.set_policy("t1", {"ai_generation_allowed": False})
    policy = store.get_policy("t1")
    assert policy["ai_generation_allowed"] is False
    assert policy["data_sharing_level"] == "local_only"  # افتراضيّ متحفّظ


def test_invalid_data_sharing_level_falls_back_to_local_only():
    assert (
        TP.normalize_policy({"data_sharing_level": "send_everything"})["data_sharing_level"]
        == "local_only"
    )
    for level in ("local_only", "redacted_external", "full_external"):
        assert TP.normalize_policy({"data_sharing_level": level})["data_sharing_level"] == level


def test_db_column_name_is_accepted():
    """صفّ القاعدة (``external_data_sharing_level``) يُقبَل مباشرةً."""
    norm = TP.normalize_policy({"external_data_sharing_level": "redacted_external"})
    assert norm["data_sharing_level"] == "redacted_external"


def test_durable_loader_is_consulted_then_cached():
    calls = {"n": 0}

    def loader(tenant_id: str):
        calls["n"] += 1
        return {"ai_generation_allowed": True, "external_data_sharing_level": "full_external"}

    store = TP.TenantPolicyStore(loader=loader)
    first = store.get_policy("t-db")
    second = store.get_policy("t-db")  # الثاني من الكاش ⇒ لا استدعاء إضافيّ
    assert first["data_sharing_level"] == "full_external"
    assert second == first
    assert calls["n"] == 1


def test_loader_failure_is_safe():
    def loader(tenant_id: str):
        raise RuntimeError("db down")

    store = TP.TenantPolicyStore(loader=loader)
    assert store.get_policy("t-x") == {}  # سقوط آمن، لا استثناء للمستدعي


def test_saver_failure_does_not_break_set():
    def saver(tenant_id: str, policy: dict):
        raise RuntimeError("db down")

    store = TP.TenantPolicyStore(saver=saver)
    norm = store.set_policy("t-y", {"data_sharing_level": "redacted_external"})
    assert norm["data_sharing_level"] == "redacted_external"
    assert store.get_policy("t-y")["data_sharing_level"] == "redacted_external"  # الكاش حيّ


def test_levels_match_provider_contract():
    """مستويات المشاركة متطابقة بين الوحدتين (لا انحراف)."""
    assert TP.DATA_SHARING_LEVELS == CONTRACT.DATA_SHARING_LEVELS
    assert TP.DATA_SHARING_LOCAL_ONLY == CONTRACT.DEFAULT_DATA_SHARING_LEVEL


def test_migration_exists_with_required_columns_and_rls():
    sql = (ROOT / "migrations/v124_tenant_ai_policies.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS tenant_ai_policies" in sql
    for col in (
        "tenant_id",
        "ai_generation_allowed",
        "allowed_providers",
        "allowed_models",
        "external_data_sharing_level",
        "redaction_profile",
        "updated_by",
        "updated_at",
    ):
        assert col in sql, f"missing column: {col}"
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.current_tenant', true)" in sql
    for level in ("local_only", "redacted_external", "full_external"):
        assert level in sql


def test_migration_registered_in_manifest():
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert "v124_tenant_ai_policies.sql" in manifest
