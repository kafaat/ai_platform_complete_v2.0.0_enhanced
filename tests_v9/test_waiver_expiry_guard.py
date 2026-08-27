"""WAIVER-EXPIRY-GUARD — deterministic logic tests (injected 'today', no clock reliance).

Also asserts the live endpoint-coverage waiver config is internally well-formed: every
waiver marked temporary carries a parseable expiry (so the guard can enforce it).
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "ci" / "waiver_expiry_guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("waiver_expiry_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = _load_guard()
TODAY = _dt.date(2026, 7, 11)


# Temporary waivers must carry accountability metadata (owner + reason). The fixtures
# below supply both so each test isolates the expiry-semantics assertion it targets;
# the missing-field contract is pinned separately in test_temporary_requires_owner_reason.
_ACCOUNTABLE = {"owner": "team", "reason": "time-boxed exception"}


def test_future_expiry_passes():
    entries = [{"endpoint": "/x", "expiry": "2026-10-11", "temporary": True, **_ACCOUNTABLE}]
    assert guard.check_waivers(entries, today=TODAY) == []


def test_expired_waiver_is_flagged():
    entries = [{"endpoint": "/x", "expiry": "2026-07-10", "temporary": True, **_ACCOUNTABLE}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert len(problems) == 1
    assert "expired 2026-07-10" in problems[0]


def test_expiry_today_is_not_expired():
    # expiry == today is still valid (expires at end of the day).
    entries = [{"endpoint": "/x", "expiry": "2026-07-11", "temporary": True, **_ACCOUNTABLE}]
    assert guard.check_waivers(entries, today=TODAY) == []


def test_temporary_without_expiry_is_flagged():
    entries = [{"endpoint": "/x", "temporary": True, **_ACCOUNTABLE}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert len(problems) == 1
    assert "no expiry" in problems[0]


def test_malformed_expiry_is_flagged():
    entries = [{"endpoint": "/x", "expiry": "11-10-2026", "temporary": True, **_ACCOUNTABLE}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert len(problems) == 1
    assert "malformed expiry" in problems[0]


def test_temporary_requires_owner_reason():
    # A temporary waiver missing accountability metadata is flagged per missing field
    # (owner + reason), independent of a valid future expiry.
    entries = [{"endpoint": "/x", "expiry": "2026-10-11", "temporary": True}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert any("missing required field owner" in p for p in problems)
    assert any("missing required field reason" in p for p in problems)


def test_permanent_waiver_without_expiry_is_ignored():
    # no expiry, not temporary ⇒ permanent by design (e.g. admin-ops) ⇒ not flagged.
    entries = [{"endpoint": "/admin/x", "reason_category": "admin-ops"}]
    assert guard.check_waivers(entries, today=TODAY) == []


def test_iter_waivers_supports_dict_and_list():
    assert list(guard._iter_waivers({"waivers": [{"a": 1}]})) == [{"a": 1}]
    assert list(guard._iter_waivers([{"b": 2}])) == [{"b": 2}]


def test_live_endpoint_coverage_waivers_are_wellformed():
    data = json.loads(
        (ROOT / "config" / "endpoint_ui_coverage_waivers.json").read_text(encoding="utf-8")
    )
    for w in guard._iter_waivers(data):
        if w.get("temporary") is True:
            # a temporary waiver must carry a parseable expiry so CI can enforce it.
            _dt.date.fromisoformat(str(w["expiry"]))


# ── مرادفاتُ الانقضاء القريبة ─────────────────────────────────────────────────
#
# العطلُ الذي وُجِدت هذه الاختباراتُ لأجله: سبعةُ إعفاءاتٍ في الملفّ الحيّ كانت
# تحمل تاريخَها تحت `expires`، والحارسُ يقرأ `expiry` وحدَه — فمرّت صامتةً منذ
# نزولها، وأقربُها كان على بعد أربعة أيّام. تاريخٌ لا تراه CI ليس موعداً نهائيّاً.


def test_a_near_miss_expiry_key_is_flagged_not_ignored():
    """`expires` وحدَه: كان يمرّ بلا ملاحظةٍ واحدة، فصار يُبلَّغ باسمه وقيمته."""
    entries = [{"endpoint": "/x", "expires": "2026-08-31"}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert len(problems) == 1
    assert "'expires'" in problems[0] and "2026-08-31" in problems[0]
    assert "rename it to 'expiry'" in problems[0]


def test_every_near_miss_key_is_covered_not_just_the_one_that_bit_us():
    """الصنفُ لا الحالة: كلُّ تهجٍّ في القائمة يُرفَض، لا `expires` وحدَه."""
    for alias in guard.EXPIRY_NEAR_MISS_KEYS:
        problems = guard.check_waivers([{"endpoint": "/x", alias: "2026-10-11"}], today=TODAY)
        assert problems, f"المرادفُ {alias} يمرّ بلا ملاحظة"
        assert repr(alias) in problems[0]


def test_a_valid_expiry_alongside_an_alias_is_still_flagged():
    """الالتباسُ نفسُه عطل: مُدخَلٌ بتاريخين يقرأ كلُّ ناظرٍ فيه واحداً."""
    entries = [{"endpoint": "/x", "expiry": "2026-10-11", "expires": "2026-07-10"}]
    problems = guard.check_waivers(entries, today=TODAY)
    assert len(problems) == 1
    assert "'expires'" in problems[0]


def test_a_waiver_with_only_expiry_draws_no_alias_complaint():
    """ولا إيجابيّاتٍ كاذبة: التهجّي القانونيُّ وحدَه يمرّ نظيفاً."""
    assert guard.check_waivers([{"endpoint": "/x", "expiry": "2026-10-11"}], today=TODAY) == []


def test_live_waiver_configs_carry_no_invisible_deadline():
    """راتشِتٌ على البيانات: صفرُ مرادفٍ في أيّ ملفّ يفحصه الحارس.

    الاختبارُ السابق (`..._are_wellformed`) لم يكن ليمسك هذا: كان يفحص المؤقّتةَ
    وحدَها، والسبعةُ لم تُعلَن `temporary` — فمرّت من فتحتين لا واحدة.
    """
    for path in guard.WAIVER_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for w in guard._iter_waivers(data):
            present = [k for k in guard.EXPIRY_NEAR_MISS_KEYS if k in w]
            assert not present, (
                f"{path.name}: {w.get('endpoint') or w.get('id')} يحمل {present} — "
                "تاريخٌ لا يقرؤه الحارس"
            )
