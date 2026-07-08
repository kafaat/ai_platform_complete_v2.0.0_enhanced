"""حارس M4 — مُدقِّق الـmigrations يفحص ``ON CONFLICT`` **عبر الملفّات** (لا إيجابيّة كاذبة).

v18 يستخدم ``ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL`` في دالّة، والفهرس الجزئيّ
المطابق ``ux_events_dedup ON events(dedup_key) WHERE dedup_key IS NOT NULL`` مُعرَّف في v11.
الفحص القديم (نفس-الملفّ) كان يُصدِر تحذيراً كاذباً؛ الآن يفحص عبر كلّ الـmigrations.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"


def _load_validator():
    spec = importlib.util.spec_from_file_location("sahool_migval", MIG / "validate_migrations.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _corpus(v) -> str:
    manifest = [
        re.sub(r"#.*", "", line).strip()
        for line in (MIG / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
    ]
    return "\n".join(
        v.strip_comments((MIG / f).read_text(encoding="utf-8"))
        for f in manifest
        if f and (MIG / f).exists()
    )


def test_v11_defines_partial_unique_index_for_dedup_key():
    sql = (MIG / "v11_events_bus.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX" in sql and "ux_events_dedup" in sql
    assert "ON events(dedup_key)" in sql and "WHERE dedup_key IS NOT NULL" in sql


def test_v18_on_conflict_not_flagged_with_cross_file_scope():
    v = _load_validator()
    issues = v.check_file(str(MIG / "v18_entity_ids_text.sql"), all_code=_corpus(v))
    on_conflict_issues = [i for i in issues if "ON CONFLICT" in i]
    assert on_conflict_issues == [], (
        f"v18 ON CONFLICT flagged despite v11 index: {on_conflict_issues}"
    )


def test_same_file_scope_still_flags_when_index_missing():
    # توافق رجعيّ: بلا corpus (نفس الملفّ) وقيد مفقود ⇒ يبقى التحذير قائماً.
    v = _load_validator()
    tmp = MIG / "_nonexistent_probe.sql"  # لا نكتب ملفّاً؛ نستدعي check_file على v18 بلا corpus.
    issues = v.check_file(str(MIG / "v18_entity_ids_text.sql"))  # all_code=None ⇒ نفس الملفّ
    assert any("ON CONFLICT" in i for i in issues), (
        "same-file scope must still warn (backward compat)"
    )
    assert not tmp.exists()
