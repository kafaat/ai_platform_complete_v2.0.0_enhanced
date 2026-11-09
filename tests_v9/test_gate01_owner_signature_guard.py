"""Falsification of the GATE-01 owner-signature guard (GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01).

Every case builds a throwaway git repository and throwaway Ed25519 keys in tmp
(``ssh-keygen``), signs the DSSE PAE bytes exactly as the runbook tells the owner to,
and asks the verifier. No key used here is committed anywhere; the repository's own
``owner_allowed_signers`` holds no key and is checked to stay that way.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import io
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sig = _load("gate01_owner_signature_guard", "scripts/ci/gate01_owner_signature_guard.py")
prep = _load("prepare_gate01_authorization", "scripts/gates/prepare_gate01_authorization.py")
g01 = _load("g01_for_owner_signature", "scripts/ci/gate01_frozen_path_guard.py")

NS = sig.NAMESPACE_DEFAULT
OWNER = "owner-test"
REPO_NAME, REPO_ID, PR = "kafaat/test-repo", 4242, 7
NOT_BEFORE = datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=UTC)
FROZEN = "services/actuator-service/actuator_runtime.py"
POLICY = sig.POLICY_PATH
CFG = dict(sig.DEFAULT_CONFIG)
AUTH_DIR = CFG["authorizations_dir"]
LEDGER = CFG["consumed_ledger_path"]
REVOKED = CFG["revocations_path"]
SIGNERS = CFG["allowed_signers_path"]
EVIDENCE = "docs/evidence/phase0_manifest.json"


# ── keys (throwaway, generated per session in tmp) ──────────────────────────────
def _keygen(directory: Path, name: str) -> Path:
    key = directory / name
    subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-t",
            "ed25519",
            "-N",
            "",
            "-C",
            f"throwaway-test-{name}",
            "-f",
            str(key),
        ],
        check=True,
        capture_output=True,
    )
    return key


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("throwaway_keys")
    return {"owner": _keygen(directory, "owner"), "agent": _keygen(directory, "agent")}


def _signer_line(principal: str, key: Path) -> str:
    return f'{principal} namespaces="{NS}" {key.with_suffix(".pub").read_text(encoding="utf-8").strip()}\n'


def _ssh_sign(key: Path, data: bytes, namespace: str, workdir: Path) -> bytes:
    msg = workdir / "to_sign.pae"
    msg.write_bytes(data)
    sigfile = Path(str(msg) + ".sig")
    sigfile.unlink(missing_ok=True)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", namespace, str(msg)],
        check=True,
        capture_output=True,
    )
    return sigfile.read_bytes()


# ── a throwaway repository ──────────────────────────────────────────────────────
def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _write(repo: Path, rel: str, data) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-verify", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _base_policy() -> dict:
    return {
        "schema": "sahool.gate01_policy/v2",
        "gate": {
            "id": "GATE-01",
            "gap_id": "GAP-X",
            "state": "CLOSED",
            "owner_ruling_on": "2026-08-09",
            "ruling_source": "sahool-brain/gaps/registry.md",
        },
        "phase0_baseline": {
            "commit_sha": "6ba0bef56f47926ce657515fe1717019522f868b",
            "tree_sha": "ac25432304025877477eb5096272027b3213ced3",
            "evidence_run_id": "31701614219",
            "evidence_conclusion": "success",
            "evidence_status": "FROZEN",
            "artifact_digests": {"live-pg-evidence": "sha256:" + "27" * 32},
        },
        "frozen_paths": [FROZEN],
        "owner_signature": {k: v for k, v in CFG.items()},
    }


@pytest.fixture
def repo(tmp_path, keys):
    """A repo whose ``main`` trusts the throwaway owner key; checked out on branch ``pr``."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, POLICY, _base_policy())
    _write(r, SIGNERS, "# test trust root\n" + _signer_line(OWNER, keys["owner"]))
    _write(r, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": []})
    _write(r, REVOKED, {"schema": sig.REVOCATION_SCHEMA, "revoked": []})
    _write(r, EVIDENCE, {"evidence_run_id": "31701614219", "conclusion": "success"})
    _write(r, FROZEN, "print('frozen v1')\n")
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", "pr")
    return r


def _open_policy(decision_id: str, mutate=None) -> dict:
    pol = _base_policy()
    pol["gate"]["state"] = "OPEN"
    pol["gate"]["owner_ruling_on"] = "2026-11-09"
    pol["gate"]["ruling_source"] = f"{AUTH_DIR}/{decision_id}{sig.ENVELOPE_SUFFIX}"
    if mutate:
        mutate(pol)
    return pol


def _transition_commit(
    repo: Path, decision_id: str = "GATE01-AUTH-2026-11-09-001", mutate=None
) -> str:
    _write(repo, POLICY, _open_policy(decision_id, mutate))
    return _commit(repo, "open GATE-01")


def _authorize(
    repo: Path,
    keys,
    *,
    head: str,
    action: str = "state_transition",
    decision_id: str = "GATE01-AUTH-2026-11-09-001",
    key: str = "owner",
    signer: str = OWNER,
    namespace: str = NS,
    override=None,
    reserve: bool = True,
    commit: bool = True,
) -> dict:
    """Owner flow: prepare → sign the PAE → envelope → reserve → trailer commit."""
    payload = prep.build_payload(
        repo,
        base_ref="main",
        head=head,
        action=action,
        decision_id=decision_id,
        repository=REPO_NAME,
        repository_id=REPO_ID,
        pr_number=PR,
        signer=signer,
        evidence_manifest=EVIDENCE,
        not_before=NOT_BEFORE,
        valid_days=3,
        nonce="ab" * 16,
    )
    if override:
        override(payload)
    body = sig.canonical_json(payload)
    armored = _ssh_sign(keys[key], sig.pae(sig.PAYLOAD_TYPE, body), namespace, repo.parent)
    envelope = sig.build_envelope(body, armored, signer)
    rel = f"{AUTH_DIR}/{decision_id}{sig.ENVELOPE_SUFFIX}"
    _write(repo, rel, envelope)
    if reserve:
        sig.reserve_consumption(
            repo / LEDGER, sig.ledger_entry(payload, envelope, "2026-11-09T11:00:00Z")
        )
    pr_head = _commit(repo, "authorization") if commit else None
    return {"payload": payload, "envelope": envelope, "rel": rel, "pr_head": pr_head}


def _findings(repo: Path, *, pr_head: str | None = None, frozen_touched=(), now=NOW, **ctx):
    pr_head = pr_head or _git(repo, "rev-parse", "HEAD")
    changed = _git(repo, "diff", "--name-only", f"main...{pr_head}").splitlines()
    head_policy = json.loads((repo / POLICY).read_text(encoding="utf-8"))
    kwargs = {
        "base_ref": "main",
        "pr_head": pr_head,
        "repository": REPO_NAME,
        "repository_id": REPO_ID,
        "pr_number": PR,
        "now": now,
    }
    kwargs.update(ctx)
    return sig.owner_signature_findings(repo, changed, head_policy, set(frozen_touched), **kwargs)


def _blocked(errors: list[str], needle: str) -> None:
    assert errors, "expected the guard to block"
    assert any(needle in e for e in errors), errors


# ── the happy path ──────────────────────────────────────────────────────────────
def test_a_valid_owner_signature_authorizes_the_transition(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    errors, notes = _findings(repo)
    assert errors == [], errors


def test_the_cli_verifies_a_valid_envelope_and_refuses_others(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head)
    common = [
        "--root",
        str(repo),
        "--base-ref",
        "main",
        "--repository",
        REPO_NAME,
        "--repository-id",
        str(REPO_ID),
        "--pr-number",
        str(PR),
        "--now",
        "2026-11-09T12:00:00Z",
    ]
    assert sig.main([auth["rel"], *common]) == 0
    assert sig.main([auth["rel"], *common[:-2], "--now", "2026-11-20T12:00:00Z"]) == 1


# ── signature, key, namespace, signer ───────────────────────────────────────────
def test_a_signature_by_another_key_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, key="agent")  # agent key, claiming the owner principal
    errors, _ = _findings(repo)
    _blocked(errors, "signature does not verify")
    _blocked(errors, "CLOSED→OPEN refused")


def test_an_unknown_signer_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, key="agent", signer="agent-test")
    errors, _ = _findings(repo)
    _blocked(errors, "unknown signer")


def test_a_wrong_namespace_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, namespace="git")
    errors, _ = _findings(repo)
    _blocked(errors, "signature does not verify")


def test_a_tampered_payload_byte_is_refused(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head, commit=False)
    env = json.loads(auth["envelope"])
    body = base64.b64decode(env["payload"])
    tampered = body.replace(b'"nonce":"abab', b'"nonce":"abac', 1)
    assert tampered != body
    env["payload"] = base64.b64encode(tampered).decode()
    _write(repo, auth["rel"], sig.canonical_json(env))
    _commit(repo, "tampered")
    errors, _ = _findings(repo)
    _blocked(errors, "signature does not verify")


def test_a_non_canonical_or_duplicate_key_payload_is_refused():
    good = {"a": 1}
    for body in (b'{"a": 1}\n', b'{"a":1,"a":2}\n'):
        env = {
            "payloadType": sig.PAYLOAD_TYPE,
            "payload": base64.b64encode(body).decode(),
            "signatures": [{"keyid": "k", "sig": base64.b64encode(b"x").decode()}],
        }
        with pytest.raises(sig.AuthorizationError):
            sig.parse_envelope(sig.canonical_json(env))
    assert sig.canonical_json(good) == b'{"a":1}\n'


def test_a_missing_signature_is_refused_where_required(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head, commit=False)
    env = json.loads(auth["envelope"])
    env["signatures"] = []
    _write(repo, auth["rel"], sig.canonical_json(env))
    _commit(repo, "unsigned envelope")
    errors, _ = _findings(repo)
    _blocked(errors, "exactly one signature")
    _blocked(errors, "CLOSED→OPEN refused")


# ── subject binding ─────────────────────────────────────────────────────────────
def test_a_tampered_scope_digest_is_refused(repo, keys):
    head = _transition_commit(repo)

    def bad_digest(p):
        p["subject"]["scope"][0]["after_sha256"] = "f" * 64

    _authorize(repo, keys, head=head, override=bad_digest)
    errors, _ = _findings(repo)
    _blocked(errors, "signed scope differs from the actual change set")


def test_a_signed_head_that_is_not_the_tested_commit_is_refused(repo, keys):
    head = _transition_commit(repo)
    other = _git(repo, "rev-parse", "main")
    _authorize(repo, keys, head=head, override=lambda p: p["subject"].update(head_sha=other))
    errors, _ = _findings(repo)
    _blocked(errors, "INVALID owner authorization")


def test_a_signed_base_that_is_not_the_merge_base_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, override=lambda p: p["subject"].update(base_sha=head))
    errors, _ = _findings(repo)
    _blocked(errors, "base changed after approval")


def test_a_signed_tree_that_is_not_the_head_tree_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, override=lambda p: p["subject"].update(tree_sha="1" * 40))
    errors, _ = _findings(repo)
    _blocked(errors, "signed tree_sha is not the tree")


def test_base_changed_after_approval_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    _git(repo, "checkout", "-q", "main")
    _write(repo, "README.md", "main moved\n")
    _commit(repo, "main moves")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@e", "merge", "-q", "--no-edit", "main")
    errors, _ = _findings(repo)
    _blocked(errors, "base changed after approval")


# ── history rewritten after signing: every rewrite fails closed (owner re-signs) ──
# The ancestry check compares a = subject.head_sha (the commit the owner signed) with
# b = the PR head (github.event.pull_request.head.sha). A rewrite of the PR branch gives b
# a history that no longer contains a, even when the bytes are identical, so the
# authorization is refused rather than carried onto commits the owner never saw.
_GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@e")


def test_a_rebase_after_signing_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    _git(repo, "checkout", "-q", "main")
    _write(repo, "README.md", "main moved\n")
    _commit(repo, "main moves")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, *_GIT_ID, "rebase", "-q", "main")
    errors, _ = _findings(repo)
    _blocked(errors, "is not an ancestor of the PR head")
    _blocked(errors, "base changed after approval")


def test_a_squash_of_the_pr_branch_after_signing_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    tree_before = _git(repo, "rev-parse", "HEAD^{tree}")
    _git(repo, "reset", "-q", "--soft", "main")
    _git(repo, *_GIT_ID, "commit", "-q", "-m", "squashed")
    assert _git(repo, "rev-parse", "HEAD^{tree}") == tree_before  # same bytes, new history
    errors, _ = _findings(repo)
    _blocked(errors, "is not an ancestor of the PR head")


def test_amending_the_signed_commit_with_identical_bytes_is_refused(repo, keys):
    head = _transition_commit(repo)
    _git(repo, *_GIT_ID, "commit", "-q", "--amend", "-m", "reworded, same tree")
    assert _git(repo, "rev-parse", "HEAD^{tree}") == _git(repo, "rev-parse", f"{head}^{{tree}}")
    _authorize(repo, keys, head=head)  # the signature names the pre-amend commit
    errors, _ = _findings(repo)
    _blocked(errors, "is not an ancestor of the PR head")


def test_a_commit_after_the_signed_head_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    _write(repo, FROZEN, "print('slipped in after the signature')\n")
    _commit(repo, "sneaky")
    errors, _ = _findings(repo)
    _blocked(errors, "commits after the signed head change more than the authorization files")


def test_a_valid_signature_over_a_different_subject_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, override=lambda p: p["identity"].update(pr_number=PR + 1))
    errors, _ = _findings(repo)
    _blocked(errors, f"signed for PR #{PR + 1}")


def test_an_envelope_from_another_repository_id_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo, repository_id=REPO_ID + 1)
    _blocked(errors, "repository_id")


# ── validity, revocation, single use ────────────────────────────────────────────
def test_an_expired_decision_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo, now=datetime(2026, 11, 13, 0, 0, 0, tzinfo=UTC))
    _blocked(errors, "expired")


def test_a_not_yet_valid_decision_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo, now=datetime(2026, 11, 8, 0, 0, 0, tzinfo=UTC))
    _blocked(errors, "not yet valid")


def test_a_validity_window_longer_than_policy_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(
        repo,
        keys,
        head=head,
        override=lambda p: p["validity"].update(expires_at="2026-12-30T00:00:00Z"),
    )
    errors, _ = _findings(repo)
    _blocked(errors, "validity window longer")


def test_a_revoked_decision_is_refused(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head, commit=False)
    _write(
        repo,
        REVOKED,
        {
            "schema": sig.REVOCATION_SCHEMA,
            "revoked": [
                {
                    "decision_id": auth["payload"]["decision_id"],
                    "revoked_at": "2026-11-09T11:30:00Z",
                    "reason": "test",
                }
            ],
        },
    )
    _commit(repo, "authorization + revocation")
    errors, _ = _findings(repo)
    _blocked(errors, "decision is revoked")


def test_an_already_consumed_decision_is_refused(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head)
    # The very same reservation lands on main first (consumed there); the PR is not
    # rebased, so its merge-base, subject and ledger reservation all still match —
    # the only thing that changed is that the trusted base already consumed it.
    ledger = (repo / LEDGER).read_bytes()
    _git(repo, "checkout", "-q", "main")
    _write(repo, LEDGER, ledger)
    _commit(repo, "consumed on main")
    _git(repo, "checkout", "-q", "pr")
    assert auth["payload"]["decision_id"] in (repo / LEDGER).read_text(encoding="utf-8")
    errors, _ = _findings(repo)
    _blocked(errors, "already consumed")
    assert not any("base changed" in e or "another subject" in e for e in errors), errors


def test_a_reused_decision_id_for_another_subject_is_refused(repo, keys):
    head = _transition_commit(repo)
    first = _authorize(repo, keys, head=head, reserve=False, commit=False)
    entry = sig.ledger_entry(first["payload"], first["envelope"], "2026-11-09T11:00:00Z")
    entry["subject_sha256"] = "e" * 64  # an earlier use of the same id for something else
    _write(repo, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": [entry]})
    _commit(repo, "authorization reserved for another subject")
    errors, _ = _findings(repo)
    _blocked(errors, "ledger reservation is for another subject")


def test_an_unreserved_decision_is_refused(repo, keys):
    head = _transition_commit(repo)
    _authorize(repo, keys, head=head, reserve=False)
    errors, _ = _findings(repo)
    _blocked(errors, "reserved exactly once")


def test_removing_a_ledger_entry_is_refused(repo, keys):
    _git(repo, "checkout", "-q", "main")
    _write(
        repo,
        LEDGER,
        {"schema": sig.LEDGER_SCHEMA, "entries": [{"decision_id": "GATE01-AUTH-2026-02-03-004"}]},
    )
    _commit(repo, "ledger on main")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    _write(repo, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": []})
    _commit(repo, "erase history")
    errors, _ = _findings(repo)
    _blocked(errors, "append-only")


def test_exactly_one_of_concurrent_reservations_wins(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"schema": sig.LEDGER_SCHEMA, "entries": []}), encoding="utf-8")
    real_loads = sig.strict_loads

    def slow_loads(raw):  # widen the read-check-append window so a missing lock shows
        import time

        time.sleep(0.05)
        return real_loads(raw)

    monkeypatch.setattr(sig, "strict_loads", slow_loads)
    results, failures = [], []
    barrier = threading.Barrier(8)

    def attempt(n):
        try:
            barrier.wait()
            results.append(
                sig.reserve_consumption(
                    ledger, {"decision_id": "GATE01-AUTH-2026-11-09-009", "n": n}
                )
            )
        except Exception as exc:  # noqa: BLE001 - every failure is a test failure
            failures.append(repr(exc))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures == []
    assert sorted(results) == [False] * 7 + [True]
    assert len(json.loads(ledger.read_text(encoding="utf-8"))["entries"]) == 1


def test_exactly_one_of_concurrent_reservation_processes_wins(repo, keys):
    head = _transition_commit(repo)
    auth = _authorize(repo, keys, head=head, reserve=False, commit=False)
    env_path = repo / auth["rel"]
    script = str(_ROOT / "scripts" / "gates" / "prepare_gate01_authorization.py")
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                script,
                "reserve",
                "--envelope",
                str(env_path),
                "--ledger",
                str(repo / LEDGER),
                "--reserved-at",
                "2026-11-09T11:00:00Z",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(6)
    ]
    codes = [p.wait(timeout=60) for p in procs]
    assert sorted(codes) == [0] + [1] * 5, [p.stderr.read() for p in procs]
    assert len(json.loads((repo / LEDGER).read_text(encoding="utf-8"))["entries"]) == 1


# ── fail closed without a trusted key ───────────────────────────────────────────
def test_no_trusted_key_is_unverified_and_fails_closed_for_a_transition(tmp_path, keys):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, POLICY, _base_policy())
    _write(r, SIGNERS, (_ROOT / SIGNERS).read_text(encoding="utf-8"))  # the committed template
    _write(r, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": []})
    _write(r, REVOKED, {"schema": sig.REVOCATION_SCHEMA, "revoked": []})
    _write(r, EVIDENCE, "{}\n")
    _write(r, FROZEN, "x\n")
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", "pr")
    head = _transition_commit(r)
    _authorize(r, keys, head=head)  # a perfectly signed envelope — but nothing is trusted
    errors, notes = _findings(r)
    _blocked(errors, sig.NOT_CONFIGURED)
    assert any("UNVERIFIED" in n for n in notes), notes


def test_a_key_added_in_the_pr_itself_is_not_trusted(tmp_path, keys):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, POLICY, _base_policy())
    _write(r, SIGNERS, "# empty trust root\n")
    _write(r, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": []})
    _write(r, REVOKED, {"schema": sig.REVOCATION_SCHEMA, "revoked": []})
    _write(r, EVIDENCE, "{}\n")
    _write(r, FROZEN, "x\n")
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", "pr")
    # The agent installs its own key and signs its own transition in one PR.
    _write(r, SIGNERS, _signer_line(OWNER, keys["agent"]))
    head = _transition_commit(r)
    _authorize(r, keys, head=head, key="agent")
    errors, _ = _findings(r)
    _blocked(errors, sig.NOT_CONFIGURED)


# ── first trust-root installation: pinned out of band (GATE01-INITIAL-TRUST-ROOT-IS-TOFU-01) ──
def _empty_trust_root_repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, POLICY, _base_policy())
    _write(r, SIGNERS, "# empty trust root\n")
    _write(r, LEDGER, {"schema": sig.LEDGER_SCHEMA, "entries": []})
    _write(r, REVOKED, {"schema": sig.REVOCATION_SCHEMA, "revoked": []})
    _write(r, EVIDENCE, "{}\n")
    _write(r, FROZEN, "x\n")
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", "pr")
    return r


def _ssh_fingerprint(key: Path) -> str:
    out = subprocess.run(
        ["ssh-keygen", "-lf", str(key.with_suffix(".pub"))],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return out[1]


def test_the_fingerprint_form_is_what_ssh_keygen_prints(keys):
    line = _signer_line(OWNER, keys["owner"])
    assert sig.key_fingerprints(sig.parse_allowed_signers(line)) == {
        _ssh_fingerprint(keys["owner"])
    }


def test_an_initial_key_without_an_owner_pin_is_refused(tmp_path, keys, monkeypatch):
    monkeypatch.delenv(sig.OWNER_KEY_FINGERPRINT_ENV, raising=False)
    r = _empty_trust_root_repo(tmp_path)
    # The agent shares the owner's GitHub account and installs a key it holds.
    _write(r, SIGNERS, _signer_line(OWNER, keys["agent"]))
    _commit(r, "install a key")
    errors, _ = _findings(r)
    _blocked(errors, "INITIAL trust-root installation refused")


def test_an_initial_key_that_differs_from_the_owner_pin_is_refused(tmp_path, keys):
    r = _empty_trust_root_repo(tmp_path)
    _write(r, SIGNERS, _signer_line(OWNER, keys["agent"]))
    _commit(r, "install the wrong key")
    errors, _ = _findings(r, owner_key_fingerprint=_ssh_fingerprint(keys["owner"]))
    _blocked(errors, "do not equal exactly the owner-pinned")


def test_an_extra_key_beside_the_pinned_one_is_refused(tmp_path, keys):
    r = _empty_trust_root_repo(tmp_path)
    _write(r, SIGNERS, _signer_line(OWNER, keys["owner"]) + _signer_line(OWNER, keys["agent"]))
    _commit(r, "install two keys")
    errors, _ = _findings(r, owner_key_fingerprint=_ssh_fingerprint(keys["owner"]))
    _blocked(errors, "do not equal exactly the owner-pinned")


def test_an_initial_key_that_matches_the_owner_pin_is_accepted(tmp_path, keys, monkeypatch):
    r = _empty_trust_root_repo(tmp_path)
    _write(r, SIGNERS, _signer_line(OWNER, keys["owner"]))
    _commit(r, "install the owner key")
    monkeypatch.setenv(sig.OWNER_KEY_FINGERPRINT_ENV, _ssh_fingerprint(keys["owner"]))
    errors, notes = _findings(r)
    assert errors == []
    assert any("matches the owner-pinned fingerprint" in n for n in notes), notes


def test_the_workflow_passes_the_owner_pin_from_a_repository_variable():
    wf = (_ROOT / ".github/workflows/no-report-only-change.yml").read_text(encoding="utf-8")
    assert "GATE01_OWNER_KEY_FINGERPRINT: ${{ vars.GATE01_OWNER_KEY_FINGERPRINT }}" in wf


def test_the_committed_trust_root_holds_no_key():
    text = (_ROOT / SIGNERS).read_text(encoding="utf-8")
    assert sig.parse_allowed_signers(text) == {}
    policy = json.loads((_ROOT / POLICY).read_text(encoding="utf-8"))
    block = policy["owner_signature"]
    assert block["required_for"] == ["state_transition"]
    assert block["required_for_bounded"] is False
    assert block["allowed_signers_path"] == SIGNERS
    assert policy["gate"]["state"] == "CLOSED"


@pytest.mark.parametrize(
    "line",
    [
        f"owner cert-authority ssh-ed25519 {'A' * 68}",
        f"owner ssh-rsa {'A' * 68}",
        "owner ssh-ed25519 not*base64",
    ],
)
def test_unsafe_trust_root_lines_are_rejected(line):
    with pytest.raises(sig.AuthorizationError):
        sig.parse_allowed_signers(line)


# ── the three spike cases + unsigned OPEN ───────────────────────────────────────
def _spike_fabricated_ruling(pol):
    pol["gate"]["ruling_source"] = "sahool-brain/gaps/registry.md"


def _spike_zero_digests(pol):
    pol["phase0_baseline"]["artifact_digests"] = {"live-pg-evidence": "sha256:" + "0" * 64}


def _spike_deleted_field(pol):
    del pol["phase0_baseline"]["evidence_status"]


@pytest.mark.parametrize(
    "spike", [_spike_fabricated_ruling, _spike_zero_digests, _spike_deleted_field]
)
def test_spike_cases_are_refused_without_an_owner_signature(repo, keys, spike):
    _transition_commit(repo, mutate=spike)
    errors, _ = _findings(repo)
    _blocked(errors, "CLOSED→OPEN refused")


@pytest.mark.parametrize(
    "spike", [_spike_fabricated_ruling, _spike_zero_digests, _spike_deleted_field]
)
def test_spike_cases_are_refused_when_signed_by_the_agent(repo, keys, spike):
    head = _transition_commit(repo, mutate=spike)
    _authorize(repo, keys, head=head, key="agent")
    errors, _ = _findings(repo)
    _blocked(errors, "CLOSED→OPEN refused")


def test_spike_fabricated_ruling_source_is_refused_even_when_signed(repo, keys):
    head = _transition_commit(repo, mutate=_spike_fabricated_ruling)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo)
    _blocked(errors, "ruling_source must name the signed decision envelope")


def test_spike_zero_digests_are_refused_even_when_signed(repo, keys):
    head = _transition_commit(repo, mutate=_spike_zero_digests)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo)
    _blocked(errors, "is not a real sha256")


def test_spike_deleted_field_is_refused_even_when_signed(repo, keys):
    head = _transition_commit(repo, mutate=_spike_deleted_field)
    _authorize(repo, keys, head=head)
    errors, _ = _findings(repo)
    _blocked(errors, "evidence_status")


def test_unsigned_open_transition_is_refused(repo):
    _transition_commit(repo)
    errors, _ = _findings(repo)
    _blocked(errors, "CLOSED→OPEN refused")


def test_without_a_base_ref_an_open_policy_change_fails_closed(repo):
    _transition_commit(repo)
    errors, _ = _findings(repo, base_ref=None)
    _blocked(errors, "cannot be ruled out")


def test_closing_or_keeping_closed_needs_no_signature(repo):
    _write(repo, "README.md", "unrelated\n")
    _commit(repo, "unrelated")
    errors, _ = _findings(repo)
    assert errors == []


# ── bounded adjudications: verified if present, advisory if absent ──────────────
def test_an_unsigned_bounded_change_is_advisory_by_default(repo):
    _write(repo, FROZEN, "print('frozen v2')\n")
    _commit(repo, "bounded change")
    errors, notes = _findings(repo, frozen_touched={FROZEN})
    assert errors == []
    assert any("advisory until required_for_bounded=true" in n for n in notes), notes


def test_an_unsigned_bounded_change_blocks_once_required(repo):
    _git(repo, "checkout", "-q", "main")
    pol = _base_policy()
    pol["owner_signature"]["required_for_bounded"] = True
    _write(repo, POLICY, pol)
    _commit(repo, "owner flips required_for_bounded")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "rebase", "-q", "main")
    _write(repo, FROZEN, "print('frozen v2')\n")
    _commit(repo, "bounded change")
    errors, _ = _findings(repo, frozen_touched={FROZEN})
    _blocked(errors, "carries no verified owner signature")


def test_a_signed_bounded_change_is_verified(repo, keys):
    _write(repo, FROZEN, "print('frozen v2')\n")
    head = _commit(repo, "bounded change")
    _authorize(repo, keys, head=head, action="bounded_change")
    errors, notes = _findings(repo, frozen_touched={FROZEN})
    assert errors == []
    assert any("owner-signed" in n for n in notes), notes


def test_a_present_but_invalid_bounded_signature_blocks(repo, keys):
    _write(repo, FROZEN, "print('frozen v2')\n")
    head = _commit(repo, "bounded change")
    _authorize(repo, keys, head=head, action="bounded_change", key="agent")
    errors, _ = _findings(repo, frozen_touched={FROZEN})
    _blocked(errors, "INVALID owner authorization")


# ── the mechanism protects itself ───────────────────────────────────────────────
def test_weakening_the_owner_signature_block_is_refused(repo):
    pol = _base_policy()
    pol["owner_signature"]["required_for"] = []
    _write(repo, POLICY, pol)
    _commit(repo, "weaken")
    errors, _ = _findings(repo)
    _blocked(errors, "owner_signature weakened")


def test_strengthening_the_owner_signature_block_needs_no_signature(repo):
    pol = _base_policy()
    pol["owner_signature"]["required_for_bounded"] = True
    _write(repo, POLICY, pol)
    _commit(repo, "strengthen")
    errors, _ = _findings(repo)
    assert errors == []


def test_rotating_an_installed_owner_key_needs_the_trusted_key(repo, keys):
    _write(repo, SIGNERS, _signer_line(OWNER, keys["agent"]))
    _commit(repo, "replace the owner key")
    errors, _ = _findings(repo)
    _blocked(errors, "rotating the owner key")


def test_the_frozen_path_guard_blocks_an_unsigned_transition(repo, monkeypatch, capsys):
    _transition_commit(repo)
    changed = _git(repo, "diff", "--name-only", "main...HEAD")
    monkeypatch.setattr(g01, "ROOT", repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(changed + "\n"))
    rc = g01.main(
        [
            "--stdin",
            "--policy",
            str(repo / POLICY),
            "--adjudications",
            str(repo / "none"),
            "--base-ref",
            "main",
            "--pr-head-sha",
            _git(repo, "rev-parse", "HEAD"),
            "--pr-number",
            str(PR),
            "--repository",
            REPO_NAME,
            "--repository-id",
            str(REPO_ID),
            "--now",
            "2026-11-09T12:00:00Z",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 1, out
    assert "CLOSED→OPEN refused" in out


def test_schema_rejects_missing_unknown_and_malformed_fields():
    base = {
        "schema": sig.SCHEMA,
        "decision_id": "GATE01-AUTH-2026-11-09-001",
        "action": "state_transition",
        "identity": {
            "repository": REPO_NAME,
            "repository_id": REPO_ID,
            "pr_number": PR,
            "signer": OWNER,
            "signer_role": "owner",
        },
        "subject": {
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "tree_sha": "c" * 40,
            "scope": [
                {
                    "path": POLICY,
                    "change": "modify",
                    "before_sha256": "1" * 64,
                    "after_sha256": "2" * 64,
                }
            ],
        },
        "evidence": {"manifest_path": EVIDENCE, "manifest_sha256": "3" * 64},
        "validity": {"not_before": "2026-11-09T10:00:00Z", "expires_at": "2026-11-10T10:00:00Z"},
        "use": {"max_uses": 1, "single_use": True},
        "nonce": "ab" * 16,
    }
    assert sig.payload_schema_errors(base) == []
    for mutate in (
        lambda p: p.pop("nonce"),
        lambda p: p.update(extra=1),
        lambda p: p["identity"].update(signer_role="agent"),
        lambda p: p["identity"].update(repository_id="4242"),
        lambda p: p["evidence"].update(manifest_sha256="0" * 64),
        lambda p: p["use"].update(max_uses=2),
        lambda p: p["use"].update(single_use=False),
        lambda p: p.update(action="open_everything"),
        lambda p: p["subject"]["scope"][0].update(change="chmod"),
    ):
        p = copy.deepcopy(base)
        mutate(p)
        assert sig.payload_schema_errors(p), p
