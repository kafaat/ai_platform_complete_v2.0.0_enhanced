"""The three UWRP v4.3 learning-skill scripts, fixed but not reinstalled.

#1242 merged ``experience-collector``, ``improvement-engine`` and ``skill-regression-lab``
from the owner's v4.3 archive. #1245 removed them again (gap
``UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01``) because:

* ``experience_journal.py`` scanned for credentials with narrow patterns over the
  serialized JSON text of the observation, so 6 of 7 measured credential forms were
  recorded (``OPENAI_API_KEY=`` and ``DB_PASSWORD=`` miss ``\\b``, PEM, ``xoxb-``,
  ``AIza`` and non-HTTP ``scheme://user:pass@`` URLs had no pattern), and escaping
  (``\\n`` for a newline, ``\\"`` for a quote) hid secrets the raw value would show;
* ``draft_proposals.py --out`` replaced whatever path it was given, including a copy
  of ``SKILL.md``;
* ``compare_trials.py`` gates could be passed by the input itself (the owner's other
  session reported this without a reproduction). Three ways are reproduced here: one
  task counted as several cases, one piece of evidence counted as several trials, and a
  duplicate JSON key whose last value the tool uses while a reader sees the first.

The fixed copies live in ``tools/uwrp_learning_candidate/<skill>/scripts/`` with the
original command-line interfaces, so reinstalling them is the owner's separate decision.
Credential samples are assembled at run time so the repository's secret scanners do
not see literals in this file.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "tools" / "uwrp_learning_candidate"
JOURNAL_SCRIPT = CANDIDATE / "experience-collector" / "scripts" / "experience_journal.py"
DRAFTS_SCRIPT = CANDIDATE / "improvement-engine" / "scripts" / "draft_proposals.py"
TRIALS_SCRIPT = CANDIDATE / "skill-regression-lab" / "scripts" / "compare_trials.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


journal_mod = _load("uwrp_candidate_experience_journal", JOURNAL_SCRIPT)
drafts_mod = _load("uwrp_candidate_draft_proposals", DRAFTS_SCRIPT)
trials_mod = _load("uwrp_candidate_compare_trials", TRIALS_SCRIPT)


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _hex(n: int) -> str:
    return f"{n:064x}"


def _observation(**overrides: str) -> dict:
    obs = {
        "schema": "uwrp.experience.v1",
        "observation_id": "EXP-DEMO-001",
        "skill_name": "adaptive-test-accelerator",
        "skill_digest": "a" * 64,
        "task_kind": "code",
        "signal": "resource_exhaustion",
        "outcome": "failure",
        "summary": "Synthetic fixture: parallel tests exhausted temporary disk space.",
        "evidence_ref": "receipt:synthetic-001",
        "evidence_digest": "b" * 64,
    }
    obs.update(overrides)
    return obs


# --- experience_journal.py: credentials ----------------------------------------------

_TAIL = "Q7vX2mL9pR4tW8zK1nB6cJ3hF5"

# The seven measured forms; the first six were recorded by the v4.3 script.
CREDENTIAL_SUMMARIES = {
    "openai_env": "run used OPENAI_API" + "_KEY=sk-" + "proj-" + _TAIL,
    "db_password_env": "compose had DB_PASS" + "WORD=" + _TAIL,
    "pem_private_key": "-----BEGIN RSA " + "PRIVATE KEY-----MIIEow" + _TAIL,
    "slack_bot_token": "notifier used xox" + "b-1234567890-" + _TAIL,
    "google_api_key": "maps call with AI" + "za" + "Sy" + _TAIL + "abcdefghi",
    "postgres_url_userinfo": "dsn postgresql://sahool:" + "s3cretpw" + "@db.internal/sahool",
    "github_pat": "clone used gh" + "p_" + _TAIL,
}

# Forms the scan of serialized JSON missed because escaping changed the text.
ESCAPED_SUMMARIES = {
    "bearer_after_newline": "Authorization: Bearer\n" + "eyJhbGciOiJIUzI1" + _TAIL,
    "quoted_password": 'config had password="' + _TAIL + '"',
}


@pytest.mark.parametrize(
    "summary", list(CREDENTIAL_SUMMARIES.values()), ids=list(CREDENTIAL_SUMMARIES)
)
def test_journal_refuses_each_measured_credential_form(summary: str) -> None:
    with pytest.raises(journal_mod.JournalError, match="secret"):
        journal_mod.validate_observation(_observation(summary=summary))


@pytest.mark.parametrize("summary", list(ESCAPED_SUMMARIES.values()), ids=list(ESCAPED_SUMMARIES))
def test_journal_scans_raw_field_values_not_escaped_json(summary: str) -> None:
    with pytest.raises(journal_mod.JournalError, match="secret"):
        journal_mod.validate_observation(_observation(summary=summary))


@pytest.mark.parametrize(
    "field, value",
    [
        ("observation_id", "xox" + "b-1234567890-" + _TAIL),
        ("evidence_ref", "receipt:AI" + "za" + "Sy" + _TAIL + "abcdefghi"),
    ],
)
def test_journal_scans_identifier_fields_too(field: str, value: str) -> None:
    with pytest.raises(journal_mod.JournalError, match="secret"):
        journal_mod.validate_observation(_observation(**{field: value}))


@pytest.mark.parametrize(
    "summary",
    [
        "Synthetic fixture: parallel tests exhausted temporary disk space.",
        "password reset page timed out after the API key rotation runbook.",
        "fetched https://example.org/docs/page and postgresql://db.internal:5432/sahool",
        "token budget exceeded on a long research task.",
    ],
)
def test_journal_still_accepts_benign_observations(summary: str) -> None:
    obs = _observation(summary=summary)
    assert journal_mod.validate_observation(obs) is obs


def test_journal_cli_refuses_credentials_and_writes_nothing(tmp_path: Path) -> None:
    inp = tmp_path / "obs.json"
    inp.write_text(
        json.dumps(_observation(summary=CREDENTIAL_SUMMARIES["openai_env"])), encoding="utf-8"
    )
    journal = tmp_path / "journal" / "events.jsonl"
    result = _run(JOURNAL_SCRIPT, "record", "--input", str(inp), "--journal", str(journal))
    assert result.returncode == 2, result.stdout
    assert "REFUSED" in result.stderr
    assert not journal.exists()


def test_journal_cli_records_a_clean_observation(tmp_path: Path) -> None:
    inp = tmp_path / "obs.json"
    inp.write_text(json.dumps(_observation()), encoding="utf-8")
    journal = tmp_path / "events.jsonl"
    result = _run(JOURNAL_SCRIPT, "record", "--input", str(inp), "--journal", str(journal))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "RECORDED_UNVERIFIED"
    verify = _run(JOURNAL_SCRIPT, "verify", "--journal", str(journal))
    assert verify.returncode == 0, verify.stderr
    assert json.loads(verify.stdout)["count"] == 1


# --- draft_proposals.py: --out confinement -------------------------------------------


@pytest.fixture()
def journal(tmp_path: Path) -> Path:
    path = tmp_path / "state" / "events.jsonl"
    for i in (1, 2):
        journal_mod.record(
            path,
            _observation(
                observation_id=f"EXP-DEMO-00{i}",
                evidence_ref=f"receipt:synthetic-00{i}",
                evidence_digest=_hex(i),
            ),
        )
    return path


def _skill_copy(tmp_path: Path) -> Path:
    skill = tmp_path / "skills" / "safe-delivery"
    skill.mkdir(parents=True)
    target = skill / "SKILL.md"
    target.write_text("---\nname: safe-delivery\n---\n# body\n", encoding="utf-8")
    return target


def test_drafts_out_refuses_to_overwrite_a_skill_file(tmp_path: Path, journal: Path) -> None:
    target = _skill_copy(tmp_path)
    before = target.read_bytes()
    result = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert result.returncode == 2, result.stdout
    assert "REFUSED" in result.stderr
    assert target.read_bytes() == before


def test_drafts_out_refuses_any_path_inside_a_skill_package(tmp_path: Path, journal: Path) -> None:
    skill_md = _skill_copy(tmp_path)
    target = skill_md.parent / "references" / "new_draft.json"
    result = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert result.returncode == 2, result.stdout
    assert not target.exists()


def test_drafts_out_refuses_an_existing_file_that_is_not_a_draft(
    tmp_path: Path, journal: Path
) -> None:
    target = tmp_path / "out" / "notes.json"
    target.parent.mkdir()
    target.write_text('{"schema": "something-else"}\n', encoding="utf-8")
    before = target.read_bytes()
    result = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert result.returncode == 2, result.stdout
    assert target.read_bytes() == before


def test_drafts_out_refuses_a_source_checkout(tmp_path: Path, journal: Path) -> None:
    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    target = checkout / "drafts" / "proposals.json"
    result = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert result.returncode == 2, result.stdout
    assert not target.exists()


def test_drafts_out_refuses_a_directory(tmp_path: Path, journal: Path) -> None:
    target = tmp_path / "out"
    target.mkdir()
    result = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert result.returncode == 2, result.stdout
    assert target.is_dir()


def test_drafts_out_writes_a_new_draft_and_may_replace_its_own(
    tmp_path: Path, journal: Path
) -> None:
    target = tmp_path / "drafts" / "proposals.json"
    first = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert first.returncode == 0, first.stderr
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == json.loads(first.stdout)
    assert written["proposal_count"] == 1
    assert written["can_auto_apply"] is False
    again = _run(DRAFTS_SCRIPT, "--journal", str(journal), "--out", str(target))
    assert again.returncode == 0, again.stderr
    assert json.loads(target.read_text(encoding="utf-8")) == written
    assert sorted(p.name for p in target.parent.iterdir()) == ["proposals.json"]


# --- compare_trials.py: gates the input can satisfy by itself ------------------------


def _results(origin: str = "reported_real") -> dict:
    cases = []
    n = 100
    for c in range(3):
        arms = {}
        for arm, quality in (("baseline", 0.7), ("candidate", 0.8)):
            trials = []
            for t in range(2):
                n += 1
                trials.append(
                    {
                        "trial_id": f"{arm[0]}{c}-{t}",
                        "quality": quality,
                        "cost_units": 10,
                        "safety_violation": False,
                        "evidence_digest": _hex(n),
                    }
                )
            arms[arm] = trials
        cases.append(
            {"case_id": f"CASE-0{c + 1}", "task_digest": _hex(c + 1), "critical": c == 0, **arms}
        )
    return {
        "schema": "uwrp.skill-ab-results.v1",
        "baseline_skill_sha256": "a" * 64,
        "candidate_skill_sha256": "b" * 64,
        "dataset_sha256": "c" * 64,
        "measurement_origin": origin,
        "grader": "deterministic",
        "blind": True,
        "context": {
            "agent_family": "example-only",
            "model": "none",
            "toolset_digest": "d" * 64,
            "environment_digest": "e" * 64,
        },
        "cases": cases,
    }


POLICY = {
    "schema": "uwrp.skill-ab-policy.v1",
    "min_cases": 3,
    "min_trials_per_arm": 2,
    "min_mean_gain": 0.02,
    "max_case_regression": 0.05,
    "max_mean_cost_increase_ratio": 0.1,
}


def test_trials_controls_still_pass() -> None:
    assert trials_mod.compare(_results(), POLICY)["status"] == "REPORTED_REVIEW_CANDIDATE"
    assert trials_mod.compare(_results("synthetic"), POLICY)["status"] == "SANDBOX_ONLY"


def test_trials_one_task_cannot_count_as_several_cases() -> None:
    data = _results()
    one = data["cases"][0]
    data["cases"] = [one, copy.deepcopy(one), copy.deepcopy(one)]
    for i, case in enumerate(data["cases"]):
        case["case_id"] = f"COPY-{i}"
        for arm in ("baseline", "candidate"):
            for t in case[arm]:
                t["evidence_digest"] = _hex(
                    1000 + 10 * i + int(t["trial_id"][-1]) + (5 if arm == "candidate" else 0)
                )
    with pytest.raises(ValueError, match="task"):
        trials_mod.compare(data, POLICY)


def test_trials_one_evidence_cannot_count_as_several_trials() -> None:
    data = _results()
    for case in data["cases"]:
        for arm in ("baseline", "candidate"):
            case[arm][1]["evidence_digest"] = case[arm][0]["evidence_digest"]
    with pytest.raises(ValueError, match="evidence"):
        trials_mod.compare(data, POLICY)


def test_trials_baseline_and_candidate_cannot_share_a_run() -> None:
    data = _results()
    case = data["cases"][0]
    case["candidate"][0]["evidence_digest"] = case["baseline"][0]["evidence_digest"]
    with pytest.raises(ValueError, match="evidence"):
        trials_mod.compare(data, POLICY)


def _dump_with_duplicate(data: dict, key: str, shown: object) -> str:
    """JSON text where ``key`` appears twice: ``shown`` first, the real value last."""
    text = json.dumps(data, indent=2)
    needle = f'  "{key}": '
    assert text.count(needle) == 1
    return text.replace(needle, f"{needle}{json.dumps(shown)},\n{needle}", 1)


def test_trials_cli_refuses_duplicate_keys_in_results(tmp_path: Path) -> None:
    data = _results()
    results = tmp_path / "results.json"
    # A reviewer reading top-down sees an unblinded run; the parser kept the last value.
    results.write_text(_dump_with_duplicate(data, "blind", False), encoding="utf-8")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    result = _run(TRIALS_SCRIPT, "--results", str(results), "--policy", str(policy))
    assert result.returncode == 2, result.stdout
    assert "duplicate" in result.stderr


def test_trials_cli_refuses_duplicate_keys_in_policy(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(json.dumps(_results()), encoding="utf-8")
    loose = dict(POLICY, max_case_regression=1)
    policy = tmp_path / "policy.json"
    policy.write_text(_dump_with_duplicate(loose, "max_case_regression", 0.05), encoding="utf-8")
    result = _run(TRIALS_SCRIPT, "--results", str(results), "--policy", str(policy))
    assert result.returncode == 2, result.stdout
    assert "duplicate" in result.stderr


def test_trials_cli_exit_codes_unchanged(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(POLICY), encoding="utf-8")
    for origin, code, status in (
        ("reported_real", 0, "REPORTED_REVIEW_CANDIDATE"),
        ("synthetic", 3, "SANDBOX_ONLY"),
    ):
        results = tmp_path / f"{origin}.json"
        results.write_text(json.dumps(_results(origin)), encoding="utf-8")
        result = _run(TRIALS_SCRIPT, "--results", str(results), "--policy", str(policy))
        assert result.returncode == code, result.stderr
        assert json.loads(result.stdout)["status"] == status
