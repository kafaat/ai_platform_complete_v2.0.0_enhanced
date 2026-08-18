from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]
ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/architecture/platform_shrink_ratchet_guard.py"
spec = importlib.util.spec_from_file_location("platform_shrink_ratchet_guard", PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def _sandbox(tmp_path, monkeypatch):
    for rel in [
        "docs/architecture/platform_shrink_ratchet.json",
        "docs/architecture/db_ownership.yml",
    ]:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    shutil.copytree(
        ROOT / "services/sahool-platform",
        tmp_path / "services/sahool-platform",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
    )
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "POLICY", tmp_path / "docs/architecture/platform_shrink_ratchet.json")
    monkeypatch.setattr(mod, "OWNERSHIP", tmp_path / "docs/architecture/db_ownership.yml")
    return tmp_path


def test_current_platform_shrink_baseline_is_exact():
    assert mod.findings() == []


def test_new_platform_owned_table_is_identity_blocked(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    p = root / "docs/architecture/db_ownership.yml"
    p.write_text(
        p.read_text(encoding="utf-8")
        + "\n  s5_mutant_table:\n    owner: sahool-platform\n    writers: [sahool-platform]\n",
        encoding="utf-8",
    )
    assert any(
        "NEW platform_domain_table_ownership: s5_mutant_table" in x
        for x in mod.findings(today=dt.date(2026, 8, 17))
    )


def test_stale_identity_forces_baseline_lowering(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    pol = json.loads(
        (root / "docs/architecture/platform_shrink_ratchet.json").read_text(encoding="utf-8")
    )
    victim = pol["baseline"]["platform_provider_clients"][0]
    (root / victim).unlink()
    assert any(
        x.startswith("STALE platform_provider_clients:")
        for x in mod.findings(today=dt.date(2026, 8, 17))
    )


def test_exception_requires_owner_reason_and_close_date(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    pp = root / "docs/architecture/platform_shrink_ratchet.json"
    pol = json.loads(pp.read_text(encoding="utf-8"))
    pol["exceptions"] = [{"category": "platform_provider_clients", "identity": "x"}]
    pp.write_text(json.dumps(pol), encoding="utf-8")
    assert any("missing fields" in x for x in mod.findings(today=dt.date(2026, 8, 17)))


def test_category_compensation_cannot_hide_new_identity(tmp_path, monkeypatch):
    root = _sandbox(tmp_path, monkeypatch)
    pp = root / "docs/architecture/platform_shrink_ratchet.json"
    pol = json.loads(pp.read_text(encoding="utf-8"))
    victim = pol["baseline"]["platform_provider_clients"][0]
    (root / victim).unlink()
    new = root / "services/sahool-platform/api/connectors/s5_new_provider.py"
    new.write_text("import httpx\nURL='https://example.invalid'\n", encoding="utf-8")
    f = mod.findings(today=dt.date(2026, 8, 17))
    assert any("NEW platform_provider_clients" in x and "s5_new_provider.py" in x for x in f)
    assert any("STALE platform_provider_clients" in x and victim in x for x in f)


def test_an_exception_whose_reason_expired_is_reported_as_unnecessary(tmp_path, monkeypatch):
    """استثناءٌ لهُويّةٍ صارت في الأساس لم يعد يستثني شيئاً — يجب أن يُبلَّغ بائداً.

    السياسة الحيّة تحمل **صفر** استثناء، فقاعدة `stale/unnecessary` لا تمرّ بها حلقةٌ
    على الشجرة الحقيقيّة. بلا هذا الصندوق الرمليّ تبقى القاعدة غير مقيسة، ويُزرَع
    عطلُها فيبقى كلّ اختبارٍ أخضر — وهو ما قاسته البوّابة فعلاً.
    """
    root = _sandbox(tmp_path, monkeypatch)
    pp = root / "docs/architecture/platform_shrink_ratchet.json"
    pol = json.loads(pp.read_text(encoding="utf-8"))
    ident = pol["baseline"]["platform_provider_clients"][0]
    pol["exceptions"] = [
        {
            "category": "platform_provider_clients",
            "identity": ident,
            "owner": "platform-team",
            "reason": "هُويّة في الأساس أصلاً — الاستثناء لا يستثني شيئاً",
            "target_close_by": "2026-10-01",
        }
    ]
    pp.write_text(json.dumps(pol), encoding="utf-8")
    f = mod.findings(today=dt.date(2026, 8, 17))
    assert any(x == f"stale/unnecessary exception: platform_provider_clients:{ident}" for x in f), f
