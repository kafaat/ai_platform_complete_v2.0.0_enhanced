"""عقدُ انضباط إثبات الأسلاف — `SQUASH-MERGE-MAKES-ANCESTRY-AN-UNSATISFIABLE-PROOF-01`.

هذا المستودع يُدمَج **سحقاً**: التزاماتُ الفروع لا تصير أسلافاً لـ`main` أبداً،
فبرهانُ «موجودٌ على main» بـ``merge-base --is-ancestor`` على SHA فرعٍ **غيرُ قابل
للإرضاء بالبناء** — يفشل على محتوًى هابطٍ فعلاً. الصنفُ أصاب ثلاث مرّات في يومٍ
واحد (2026-08-22): تدقيقان خارجيّان أصدرا NO-GO كاذباً على D09 («D09-C/M/E NOT
FOUND») لأنّ مرساتيهما ``7fecea3d`` و``3635dfb8`` التزاما فرعٍ سُحِق، وثالثةٌ
على D06-C1 بالآليّة نفسها. المعيارُ الصحيح تطابقُ الشجرة أو القياسُ السلوكيّ.

العقدُ هنا وجهان: مسحٌ يُبقي كلَّ استعمالٍ لـ``--is-ancestor`` في الشيفرة
التنفيذيّة مُدقَّقاً بقائمة سماحٍ مسبَّبة — الموضعُ الجديد يحمرّ حتى يُدقَّق —
وبرهانٌ تنفيذيّ يبني السيناريو في مستودعٍ مؤقّت فيُثبِت الفخَّ والمعيارَ البديل
معاً، كي لا يبقى الدرسُ نثراً يُنسى.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
LIVE_RUNBOOK = ROOT / "scripts/staging/post_commit_live_acceptance.sh"

# قائمةُ السماح **مسبَّبة**: الموضعُ بلا سببٍ مكتوب ليس مُدقَّقاً بل مُهرَّباً.
# إضافةُ موضعٍ جديد هنا تعني أنّ كاتبه أجاب: لماذا لا يكذب هذا الاستعمال تحت squash؟
AUDITED_SITES = {
    "scripts/ops/live_gap_closure/run_preflight.sh": (
        "يثبت أنّ SHA موضوع القياس ينحدر من التزام أساسٍ ثابت على main قبل تشغيل "
        "جلسة الإغلاق؛ لا يستعمل SHA فرعٍ لإثبات هبوط squash، ويبقى قابلاً للإرضاء "
        "لأنّ التزام الأساس جزءٌ من تاريخ main نفسه."
    ),
    "scripts/ops/branch_funeral.py": (
        "مُصنِّفُ تنظيفٍ لا برهان: تحت squash ينحرف إلى «غير مدموج» فيمتنع عن الحذف — "
        "الاتجاهُ الآمن — وتغطية الدمج الفعليّ عند merged_set من حالة الـPR لا من الأسلاف."
    ),
    "scripts/staging/post_commit_live_acceptance.sh": (
        "يثبت انحدارَ رأسٍ من التزامِ خطّ أساسٍ **داخل تاريخ main نفسه** — "
        "تاريخُ main خطّيٌّ عبر التزامات السحق، فالبرهان قابلٌ للإرضاء."
    ),
    "tests_v9/test_gap_landing_claims_name_a_real_commit.py": (
        "الإنفاذُ المقابل للفخّ لا ضحيّتُه: يرفض ادّعاءَ هبوطٍ مكتوباً بـSHA فرعٍ "
        "ويُلزِم الكاتبَ بالتزام main بعد السحق — رفضُه هو عينُ الدرس."
    ),
}

_NEEDLE = "--is-ancestor"
_SCAN_SUFFIXES = {".py", ".sh", ".yml", ".yaml"}


def _tracked_executable_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120
    ).stdout
    return [
        ROOT / line
        for line in out.splitlines()
        if Path(line).suffix in _SCAN_SUFFIXES and (ROOT / line).is_file()
    ]


def test_every_is_ancestor_site_in_executable_code_is_audited():
    found = set()
    for path in _tracked_executable_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel == Path(__file__).relative_to(ROOT).as_posix():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _NEEDLE in text:
            found.add(rel)
    unaudited = found - set(AUDITED_SITES)
    assert not unaudited, (
        f"استعمالُ `--is-ancestor` جديدٌ غيرُ مُدقَّق: {sorted(unaudited)} — "
        "تحت squash قد يكون برهاناً غيرَ قابلٍ للإرضاء؛ دقِّقه وسبِّبه في القائمة أو استبدل "
        "به تطابقَ الشجرة"
    )
    vanished = set(AUDITED_SITES) - found
    assert not vanished, (
        f"مواضعُ في قائمة السماح لم تعد موجودة: {sorted(vanished)} — "
        "قائمةٌ تذكر ما زال تُقرأ تغطيةً لما كان"
    )


def test_live_acceptance_agent_is_exactly_subject_bound_and_non_authoritative():
    text = LIVE_RUNBOOK.read_text(encoding="utf-8")
    assert "doctor|preflight|rag|s5|c11|c12|verify|check-seal|abort|recover|all|agent" in text
    assert "agent mode requires EXPECTED_SUBJECT_SHA=<40-hex>" in text
    assert "agent mode requires EXPECTED_SUBJECT_TREE=<40-hex>" in text
    assert "AGENT_CONFIRM_EVIDENCE_ONLY=1" in text
    assert 'EXECUTION_ACTOR_KIND="ai-agent"' in text
    assert "'authority_promotion':False" in text
    assert "'physical_shrink_authorized':False" in text
    assert "'runtime_verified':False" in text
    assert "'production_certified':False" in text
    assert "flock -n 9" in text
    assert "timeout --kill-after=30s" in text
    assert "round_doc['round_state']='SEALED'" in text


def test_refused_agent_mode_creates_no_evidence_namespace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "checkout", "-q", "-B", "main")
    (repo / "tracked.txt").write_text("subject\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "subject")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    evidence = tmp_path / "must-not-exist"
    result = subprocess.run(
        ["bash", str(LIVE_RUNBOOK), "agent"],
        cwd=repo,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHON": "python3",
            "EXPECTED_BASELINE_SHA": sha,
            "LIVE_ACCEPTANCE_ARTIFACT_DIR": str(evidence),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 2
    assert "agent mode requires EXPECTED_SUBJECT_SHA" in result.stderr
    assert not evidence.exists()


def test_abort_transition_updates_pointer_and_round_atomically(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "checkout", "-q", "-B", "main")
    (repo / "tracked.txt").write_text("subject\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "subject")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    tree = _git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
    evidence = tmp_path / "evidence"
    round_dir = evidence / "rounds" / "round-001"
    round_dir.mkdir(parents=True)
    body = {
        "schema": "sahool.live-acceptance-round/v1",
        "round_id": "round-001",
        "round_state": "OPEN",
        "subject_sha": sha,
        "subject_tree": tree,
        "baseline_sha": sha,
        "opened_at_epoch": 1,
    }
    (round_dir / "ROUND.json").write_text(json.dumps(body), encoding="utf-8")
    (evidence / "ROUND.json").write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        ["bash", str(LIVE_RUNBOOK), "abort"],
        cwd=repo,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repo),
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHON": "python3",
            "EXPECTED_BASELINE_SHA": sha,
            "LIVE_ACCEPTANCE_ARTIFACT_DIR": str(evidence),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (
        json.loads((round_dir / "ROUND.json").read_text(encoding="utf-8"))["round_state"]
        == "ABORTED"
    )
    assert (
        json.loads((evidence / "ROUND.json").read_text(encoding="utf-8"))["round_state"]
        == "ABORTED"
    )


def test_live_acceptance_summary_is_written_before_the_checksum_manifest():
    text = LIVE_RUNBOOK.read_text(encoding="utf-8")
    summary_write = text.index("(root/'SUMMARY.json').write_text")
    manifest_write = text.index("(root/'SHA256SUMS.txt').write_text")
    assert summary_write < manifest_write


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    # بيئةُ git معزولةٌ بنمط المستودع المعتمد (راجع test_brain_duplicate_gap_identity_guard):
    # HOME داخل الجذر المؤقّت وGIT_CONFIG_NOSYSTEM يقطعان إعدادات المضيف، وPATH ثابت
    # لا موروث — فلا يتلوّن السلوك بجهاز المشغّل.
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(repo),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def test_squash_merge_defeats_the_ancestor_proof_while_tree_equality_holds(tmp_path):
    """البرهانُ التنفيذيّ: السيناريو الذي أنتج NO-GO الكاذب، مبنيّاً لا محكيّاً."""
    repo = tmp_path / "r"
    repo.mkdir()
    # `init -b` حديثٌ نسبيّاً؛ نمطُ المستودع: init ثم إعادة تسمية الفرع — أوسع حملاً.
    _git(repo, "init", "-q")
    _git(repo, "checkout", "-q", "-B", "main")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "f.txt").write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature work")
    feature_sha = _git(repo, "rev-parse", "feature").stdout.strip()

    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "--squash", "-q", "feature")
    _git(repo, "commit", "-q", "-m", "feature work (#1)")

    # المحتوى هبط بتمامه — والسلفيّة مع ذلك تكذب:
    ancestor = _git(repo, "merge-base", "--is-ancestor", feature_sha, "main")
    assert ancestor.returncode != 0, (
        "لو صار التزامُ الفرع سلفاً بعد السحق لما كان لهذا العقد موضوع — تحقّق من أنّ الدمج سحقٌ فعلاً"
    )
    feature_tree = _git(repo, "rev-parse", f"{feature_sha}^{{tree}}").stdout.strip()
    main_tree = _git(repo, "rev-parse", "main^{tree}").stdout.strip()
    assert feature_tree == main_tree, "تطابقُ الشجرة هو المعيارُ الذي يصدق حيث تكذب السلفيّة"
