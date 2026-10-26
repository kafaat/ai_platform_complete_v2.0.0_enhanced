"""Format placeholders in commit messages are not gap-ID claims."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "ci" / "brain_commit_claim_guard.py"
    spec = importlib.util.spec_from_file_location("brain_commit_claim_guard_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def test_date_format_placeholder_matches_the_id_shape_but_is_excluded():
    body = "a date picker field instead of typing YYYY-MM-DD"
    assert guard._GAP_ID.findall(body) == ["YYYY-MM-DD"]
    assert "YYYY-MM-DD" in guard._NOT_GAP_IDS


def test_a_real_looking_gap_id_is_still_a_claim():
    body = "fixes MOBILE-NOT-REGISTERED-ANYWHERE-01"
    ids = [i for i in guard._GAP_ID.findall(body) if i not in guard._NOT_GAP_IDS]
    assert ids == ["MOBILE-NOT-REGISTERED-ANYWHERE-01"]
