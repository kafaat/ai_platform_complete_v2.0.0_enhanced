from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / ".github/workflows/runtime-verification-promotion.yml"
PATH3 = ROOT / ".github/workflows/path3-runtime-verification.yml"


def text(p):
    return p.read_text(encoding="utf-8")


def test_workflow_is_pr_only_and_protected():
    s = text(P)
    assert "environment: runtime-verification-approval" in s
    assert "gh pr create" in s
    assert "--confirm RUNTIME_VERIFIED_ONLY" in s
    assert 'git push origin "$branch"' in s
    assert "git push origin HEAD:" not in s


def test_exact_target_sha_is_checked_out_and_enforced():
    s = text(P)
    assert s.count("ref: ${{ inputs.target_sha }}") >= 3
    assert '--current-head "$(git rev-parse HEAD)"' in s
    assert "Bind application checkout to exact tested SHA" in s
    assert "ref: ${{ github.event.repository.default_branch }}" not in s


def test_environment_controls_are_api_certified_fail_closed():
    s = text(P)
    assert "certify-environment-controls" in s
    assert "RUNTIME_VERIFICATION_ENV_AUDITOR_TOKEN" in s
    assert "required_reviewers" in s
    assert "deployment_branch_policy" in s


def test_attestation_chain_is_committed():
    s = text(P)
    assert "candidate-attestation.json" in s
    assert "approval-attestation.json" in s
    assert "promotion-verification-receipt.json" in s
    assert "--candidate-attestation" in s
    assert "--approval-attestation" in s


def test_duplicate_pr_guard_exists():
    s = text(P)
    assert "gh pr list" in s
    assert "promotion PR already exists" in s


def test_status_and_production_certification_forbidden():
    s = text(P)
    assert "status taxonomy and production_certified are unchanged" in s
    assert "status_taxonomy_changes" in s


def test_path3_attests_expiring_candidate():
    s = text(PATH3)
    assert "runtime_verification_apply.py prepare" in s
    assert "subject-path: runtime-verification-candidate.json" in s
    assert "path3-runtime-candidate-${{ github.sha }}" in s


def test_actions_are_immutable_sha_pinned():
    for p in (P, PATH3):
        for line in text(p).splitlines():
            if "uses:" in line:
                ref = line.split("@", 1)[1].split()[0]
                assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref)


def test_yaml_parses_and_has_four_promotion_boundaries():
    d = yaml.safe_load(text(P))
    assert list(d["jobs"]) == [
        "certify-environment-controls",
        "verify-candidate",
        "approval-receipt",
        "apply-as-pull-request",
    ]
