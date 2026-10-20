"""نطاقُ استثناءات Gitleaks المساريّة — كلُّ مدخلٍ يُعفي ملفّاً واحداً مُسمّى (C05).

المقيس بـgitleaks 8.24.3 محلّيّاً على شجرة #997: مدخلُ `docs/audits/patches/.*\\.patch$`
جعل الماسحَ **يتخطّى الملفَّ كلَّه** («Skipping file due to global allowlist»)، فملفُّ
patch جديدٌ يحمل توكناً اصطناعيّاً مرّ بلا إبلاغ؛ وبعد تضييقه إلى ملفّ SUP-08 وحده
أُبلِغ التوكن. فالاستثناءُ المساريّ إعفاءٌ كاملٌ لا تخفيفٌ، ويجب أن يُسمّي ملفّاً بعينه.

الحارسُ لا يحتاج الأداة: يقرأ `.gitleaks.toml` ويطابق تعبيراتِ `paths` على الملفّات
المتعقَّبة، فيفرض (١) أنّ كلَّ مدخلٍ يصيب ملفّاً متعقَّباً واحداً بالضبط، و(٢) أنّ
ملفّاً افتراضيّاً جديداً في المجلّد نفسه لا يصيبه أيُّ مدخل.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".gitleaks.toml"


def _allowlist_paths() -> list[str]:
    data = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return list(data["allowlist"]["paths"])


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def test_every_path_allowlist_entry_names_exactly_one_tracked_file():
    tracked = _tracked()
    for pattern in _allowlist_paths():
        matches = [p for p in tracked if re.search(pattern, p)]
        assert len(matches) == 1, (
            f"مدخلُ الاستثناء {pattern!r} يصيب {len(matches)} ملفّاً متعقَّباً {matches[:5]} — "
            "الاستثناءُ المساريّ يُعفي الملفَّ كلَّه فيجب أن يُسمّي ملفّاً واحداً"
        )


@pytest.mark.parametrize(
    "hypothetical",
    [
        "docs/audits/patches/NEW-review.patch",
        "docs/audits/patches/SUP-09-anything.patch",
        "scripts/ci/some_other_guard.py",
        "scripts/release/scan_release_archive_v2.py",
        # Copilot على #999: نمطٌ بلا مرساة `^` لاحقةٌ لا مسار — نسخةٌ متداخلة تحت مجلّدٍ
        # آخر كانت تُعفى أيضاً. مقيسٌ بـgitleaks 8.24.3: نسخةُ SUP-08 تحت `vendor/` تُبلَّغ
        # الآن (إيجاباها الكاذبان يظهران) بينما ملفُّ الجذر ما زال يُتخطّى.
        "vendor/docs/audits/patches/SUP-08-actuator-v2-PENDING-GATE-01.patch",
        "x/scripts/ci/jwt_secret_configuration_guard.py",
    ],
)
def test_a_new_file_beside_an_allowlisted_one_is_still_scanned(hypothetical: str):
    for pattern in _allowlist_paths():
        assert not re.search(pattern, hypothetical), (
            f"{pattern!r} يُعفي {hypothetical} — مدخلٌ جامع يُخفي سرّاً في ملفٍّ لاحق"
        )


def test_every_path_allowlist_entry_is_anchored_at_both_ends():
    """gitleaks يبحث عن النمط داخل المسار؛ فبلا `^` و`$` يُعفي المدخلُ كلَّ ما ينتهي أو يبدأ به."""
    for pattern in _allowlist_paths():
        assert pattern.startswith("^") and pattern.endswith("$"), pattern


def _pr_range_step():
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/secret-history-scan.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["gitleaks-full-history"]["steps"]
    return next(step for step in steps if step.get("id") == "pr-merge-history")


def test_pr_merge_scan_is_gating_and_uses_event_commit_ids():
    step = _pr_range_step()
    assert step["if"] == "github.event_name == 'pull_request'"
    assert not step.get("continue-on-error", False)
    assert step["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert step["env"]["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert "set -euo pipefail" in step["run"]
    assert "gitleaks git --redact --exit-code=2" in step["run"]
    assert "--no-merges" not in step["run"]
    assert "--first-parent" not in step["run"]


@pytest.mark.parametrize("location", ["second_parent", "merge_resolution", "removed_later"])
def test_pr_scan_reaches_content_the_pinned_action_skips(tmp_path, location):
    """The scanner's actual log options must include side history and merge diffs."""

    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=tmp_path, text=True, encoding="utf-8"
        ).strip()

    def commit(path, content):
        (tmp_path / path).write_text(content, encoding="utf-8")
        git("add", path)
        git("commit", "-qm", "fixture change")

    git("init", "-q", "-b", "main")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Fixture")
    commit("readme", "base\n")
    base = git("rev-parse", "HEAD")
    git("checkout", "-qb", "side")
    marker = "MERGE_SCOPE_" + "WITNESS"
    commit("side.txt", marker + "\n" if location != "merge_resolution" else "side\n")
    git("checkout", "-qb", "pr", base)
    commit("topic.txt", "topic\n")
    git("merge", "--no-ff", "--no-commit", "side")
    if location == "merge_resolution":
        (tmp_path / "merge.txt").write_text(marker + "\n", encoding="utf-8")
        git("add", "merge.txt")
    git("commit", "-qm", "merge side")
    if location == "removed_later":
        commit("side.txt", "removed\n")
    head = git("rev-parse", "HEAD")
    old = git("log", "-p", "-U0", "--no-merges", "--first-parent", f"{base}..{head}")
    assert not any(line.startswith("+") and marker in line for line in old.splitlines())
    command = _pr_range_step()["run"]
    options = re.search(r'--log-opts="([^"]+)"', command).group(1)
    options = options.replace("${PR_BASE_SHA}", base).replace("${PR_HEAD_SHA}", head)
    patch = git("log", "-p", "-U0", *shlex.split(options))
    assert any(line.startswith("+") and marker in line for line in patch.splitlines())
