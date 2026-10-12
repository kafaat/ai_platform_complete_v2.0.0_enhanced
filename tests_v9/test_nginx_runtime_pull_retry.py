"""سحبُ صورة nginx في اختبار التشغيل يُعيد المحاولة على انقطاعٍ عابر، ولا يبتلع فشلاً دائماً.

مقيس على #1125 (تشغيل 37122157444): ``docker pull nginx:1.27.5-alpine`` مات بـ
``connection reset by peer`` من ``auth.docker.io`` قبل أيّ اختبار، فاحمرّ «Frontend Typecheck»
على PRٍ لا يمسّ الواجهة، ونجح بإعادة التشغيل. الإعادةُ هنا محدودة وتُرفع آخرَ خطأ كما هو.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PATH = Path(__file__).resolve().parents[1] / "frontend" / "tests" / "test_nginx_runtime.py"


def _module():
    spec = importlib.util.spec_from_file_location("nginx_runtime_under_test", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Run:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, cmd, check, timeout):
        self.calls.append(cmd)
        self.timeouts = getattr(self, "timeouts", []) + [timeout]
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return subprocess.CompletedProcess(cmd, 0)


def _reset():
    return subprocess.CalledProcessError(1, ["docker", "pull"])


def test_a_transient_reset_is_retried_and_then_succeeds():
    mod = _module()
    run, waits = _Run([_reset(), None]), []
    mod.pull_image("nginx:1.27.5-alpine", run=run, sleep=waits.append)
    assert run.calls == [["docker", "pull", "nginx:1.27.5-alpine"]] * 2
    assert waits == [5]


def test_a_timeout_is_retried_like_a_reset():
    mod = _module()
    run, waits = _Run([subprocess.TimeoutExpired("docker", 180), _reset(), None]), []
    mod.pull_image("nginx:1.27.5-alpine", run=run, sleep=waits.append)
    assert len(run.calls) == 3 and waits == [5, 15]


def test_a_persistent_failure_still_fails_after_the_last_attempt():
    mod = _module()
    run, waits = _Run([_reset(), _reset(), _reset()]), []
    with pytest.raises(subprocess.CalledProcessError):
        mod.pull_image("nginx:1.27.5-alpine", run=run, sleep=waits.append)
    assert len(run.calls) == mod.PULL_ATTEMPTS == 3
    assert waits == [5, 15]


def test_the_ci_entrypoint_pulls_through_the_retrying_helper():
    source = _PATH.read_text(encoding="utf-8")
    assert "pull_image(image)" in source
    assert source.count('["docker", "pull", image]') == 1, "سحبٌ مباشرٌ ثانٍ يتجاوز الإعادة"


def test_each_attempt_uses_the_bounded_timeout():
    mod = _module()
    run = _Run([_reset(), None])
    mod.pull_image("nginx:1.27.5-alpine", run=run, sleep=lambda _s: None)
    assert run.timeouts == [mod.PULL_TIMEOUT_SECONDS] * 2


def test_the_whole_retry_budget_fits_inside_the_ci_step_with_room_for_the_test():
    """مراجعة #1130: ٣ × 180ث + الانتظار = 560ث لا تسع خطوةً حدُّها 5 دقائق، فيُقطع السحبُ
    قبل أن يُرفع خطؤه. الحدُّ يُقرأ من ci.yml نفسه لا يُنسخ."""
    import yaml

    mod = _module()
    workflow = yaml.safe_load(
        (_PATH.parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "frontend/tests/test_nginx_runtime.py --docker" in str(step.get("run", ""))
    ]
    assert len(steps) == 1, "خطوةُ اختبار تشغيل nginx يجب أن تكون واحدة"
    step_seconds = int(steps[0]["timeout-minutes"]) * 60
    test_reserve_seconds = 60  # الخطوةُ كاملةً ~36ث على main@76a5ca58
    assert mod.pull_budget_seconds() + test_reserve_seconds <= step_seconds, (
        mod.pull_budget_seconds(),
        step_seconds,
    )
