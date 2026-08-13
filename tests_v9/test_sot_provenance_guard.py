from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/ci/sot_provenance_guard.py"
spec = importlib.util.spec_from_file_location("sot_provenance_guard", PATH)
assert spec is not None and spec.loader is not None
MOD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MOD)


def _policy():
    return {
        "repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "signer_workflow": "kafaat/ai_platform_complete_v2.0.0_enhanced/.github/workflows/ci.yml",
        "predicate_type": "https://slsa.dev/provenance/v1",
        "oidc_issuer": "https://token.actions.githubusercontent.com",
        "gh_cli": {"version": "2.93.0"},
        "release_refs": ["refs/heads/main"],
    }


def test_gh_command_requires_exact_signer_workflow_and_oidc(tmp_path):
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=tmp_path / "r",
        policy=_policy(),
        tested_commit="a" * 40,
        source_ref="refs/pull/829/merge",
    )
    assert cmd[cmd.index("--signer-workflow") + 1] == _policy()["signer_workflow"]
    assert cmd[cmd.index("--cert-oidc-issuer") + 1] == _policy()["oidc_issuer"]


def test_gh_command_requires_source_digest_and_ref(tmp_path):
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=tmp_path / "r",
        policy=_policy(),
        tested_commit="b" * 40,
        source_ref="refs/pull/829/merge",
    )
    assert cmd[cmd.index("--source-digest") + 1] == "b" * 40
    assert cmd[cmd.index("--source-ref") + 1] == "refs/pull/829/merge"


def test_gh_command_denies_self_hosted_and_uses_trusted_root(tmp_path):
    root = tmp_path / "trusted.jsonl"
    cmd = MOD.build_gh_command(
        gh="gh",
        subject=tmp_path / "a",
        bundle=tmp_path / "b",
        trusted_root=root,
        policy=_policy(),
        tested_commit="c" * 40,
        source_ref="refs/heads/main",
    )
    assert "--deny-self-hosted-runners" in cmd
    assert cmd[cmd.index("--custom-trusted-root") + 1] == str(root)


def _manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = pathlib.Path("subject.json")
    p.write_text("{}", encoding="utf-8")
    m = {
        "schema": "sahool.evidence-manifest/v1",
        "closure": {"mode": "exact", "transport_exclusions": ["transport.json"]},
        "files": [
            {"path": "subject.json", "sha256": MOD.sha256(p), "size_bytes": p.stat().st_size}
        ],
    }
    mp = pathlib.Path("manifest.json")
    mp.write_bytes(MOD.canonical_manifest_bytes(m))
    return p, mp, m


def test_digest_mismatch_is_rejected(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    m["files"][0]["sha256"] = "0" * 64
    mp.write_bytes(MOD.canonical_manifest_bytes(m))
    with pytest.raises(RuntimeError, match="SUBJECT_DIGEST_MISMATCH"):
        MOD.validate_manifest(mp, m, [p, mp, pathlib.Path("transport.json")])


def test_unmanifested_file_is_rejected_by_exact_closure(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="MANIFEST_CLOSURE_MISMATCH"):
        MOD.validate_manifest(
            mp, m, [p, mp, pathlib.Path("transport.json"), pathlib.Path("evil.bin")]
        )


def test_missing_manifested_file_is_rejected(tmp_path, monkeypatch):
    p, mp, m = _manifest(tmp_path, monkeypatch)
    p.unlink()
    with pytest.raises(RuntimeError, match="MANIFEST_MISSING"):
        MOD.validate_manifest(mp, m, [p, mp, pathlib.Path("transport.json")])


def test_failed_gh_verification_never_becomes_pass(tmp_path, monkeypatch):
    """**ومخرَجُه JSON سليم عمداً.**

    كان يُموِّه بـ`stdout=""`، فلمّا صار `JSONDecodeError` يُنتِج السبب نفسه لم
    تعد طفرةُ «نزع فحص رمز الخروج» تُميّز شيئاً — أمسكه `guard_mutation_guard`.
    والخاصّيّة المقصودة أقوى: **رمزُ خروجٍ فاشل يحجب ولو كان المخرَج مفهوماً**.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, '[{"verified": true}]', "bad"),
    )
    with pytest.raises(RuntimeError, match="ATTESTATION_CRYPTO_INVALID"):
        MOD.verify_subject(
            tmp_path / "s",
            gh="gh",
            bundle=tmp_path / "b",
            trusted_root=tmp_path / "r",
            policy=_policy(),
            tested_commit="d" * 40,
            source_ref="refs/heads/main",
        )


def test_pending_pr_binding_cannot_reach_release_bound():
    assert (
        MOD.release_bound(
            {
                "tested_identity": {"commit_sha": "a" * 40, "tree_sha": "b" * 40},
                "release_binding": {"mode": "pending_final_rerun"},
            },
            _policy(),
            "refs/heads/main",
        )
        is False
    )


def test_exact_commit_binding_requires_same_commit():
    m = {
        "tested_identity": {"commit_sha": "a" * 40, "tree_sha": "b" * 40},
        "release_binding": {"mode": "exact_commit", "accepted_commit_sha": "c" * 40},
    }
    assert MOD.release_bound(m, _policy(), "refs/heads/main") is False


def test_unparsable_gh_output_is_a_crypto_reason_not_an_internal_error(tmp_path, monkeypatch):
    """مخرَجٌ لا يُحلَّل من الأداة الرسميّة عطبُ **تحقّق** لا عطبُ مُصادِق.

    خلطُهما يُضيع الإشارة: قارئ السجلّ يبحث في المُصادِق بينما العطب في مخرَج
    `gh`. أمسكه فحصٌ خارجيّ.
    """

    class _Proc:
        returncode = 0
        stdout = "not json at all"
        stderr = ""

    monkeypatch.setattr(MOD.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RuntimeError) as err:
        MOD.verify_subject(
            pathlib.Path("x"),
            gh="/usr/bin/gh",
            bundle=tmp_path / "b",
            trusted_root=tmp_path / "t",
            policy={
                "repository": "r",
                "predicate_type": "p",
                "signer_workflow": "w",
                "oidc_issuer": "o",
            },
            tested_commit="c",
            source_ref="refs/heads/main",
        )
    assert str(err.value) == "ATTESTATION_CRYPTO_INVALID"


def test_the_manifest_builder_offers_no_unreachable_binding_mode():
    """خيارٌ يَعِد بضمانٍ لا يُمنَح أسوأ من غيابه.

    `tested_merge_to_release` كان يشترطه الحارس بـ`binding_evidence` والأداة لا
    تُنتِجه قطّ — فكان الوضع غير قابل لبلوغ L4/L5 أصلاً.
    """
    # **يُقاس الخيار المُعلَن لا ورودُ الكلمة.** أوّل صياغةٍ فحصت النصّ كلّه
    # فأحمرّها **التعليقُ الذي يشرح النزع** — نصٌّ يحرس تهجئةً لا خاصّيّة، وهو
    # الصنف المُسجَّل في `TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01`.
    import ast

    tree = ast.parse((ROOT / "scripts/ci/sot_evidence_manifest.py").read_text(encoding="utf-8"))
    offered: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "choices" and isinstance(kw.value, ast.List):
                    offered |= {
                        e.value
                        for e in kw.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    }
    assert offered, "لم يُعثَر على أيّ `choices` — تغيّرت الأداة، راجع الاختبار"
    assert "tested_merge_to_release" not in offered, (
        "الوضع غير قابل للبلوغ ما دامت الأداة لا تُنتِج `binding_evidence`؛ "
        "إعادتُه تتطلّب تصميم دليل الربط أوّلاً."
    )


def test_a_bare_command_name_resolves_through_path():
    """`--gh-bin gh` اسمُ أمرٍ — يُحلّ إلى مسارٍ مطلقٍ يُبصَم، لا يُمرَّر كما هو."""
    resolved = MOD.resolve_executable("sh")
    assert pathlib.Path(resolved).is_absolute()
    assert pathlib.Path(resolved).is_file()


def test_an_unresolvable_tool_is_a_toolchain_reason(tmp_path):
    """تعذّرُ الحلّ عطلُ **أداة** لا عطلٌ داخليّ — بالاسم وبالمسار معاً."""
    for candidate in ("definitely-not-a-real-binary-xyz", str(tmp_path / "nope")):
        with pytest.raises(RuntimeError) as err:
            MOD.resolve_executable(candidate)
        assert str(err.value) == "TOOLCHAIN_MISMATCH"


def test_the_hashed_bytes_are_the_invoked_executable(tmp_path):
    """وصلةٌ رمزيّة تُفكّ: البصمة لِما يُنفَّذ لا لِما يشير إليه.

    وإلّا سجّلنا بصمة الوصلة وشغّلنا هدفها — نَسَبٌ يصف غير ما جرى.
    """
    real = tmp_path / "real_tool"
    real.write_text("#!/bin/sh\necho x\n", encoding="utf-8")
    real.chmod(0o755)
    link = tmp_path / "linked_tool"
    link.symlink_to(real)
    assert MOD.resolve_executable(str(link)) == str(real.resolve())


def test_an_empty_gh_result_list_is_a_crypto_reason(tmp_path, monkeypatch):
    """`rc=0` وقائمةٌ فارغة ليست نجاحاً: تحقّقٌ بلا نتيجةٍ واحدة لا يُثبِت شيئاً."""

    class _Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr(MOD.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RuntimeError) as err:
        MOD.verify_subject(
            pathlib.Path("x"),
            gh="/usr/bin/gh",
            bundle=tmp_path / "b",
            trusted_root=tmp_path / "t",
            policy={
                "repository": "r",
                "predicate_type": "p",
                "signer_workflow": "w",
                "oidc_issuer": "o",
            },
            tested_commit="c",
            source_ref="refs/heads/main",
        )
    assert str(err.value) == "ATTESTATION_CRYPTO_INVALID"


# ── تصنيفُ الأسباب: نقصٌ في السياسة أو الهويّة ليس عطلاً داخليّاً ──────────


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("repository"), id="missing-repository"),
        pytest.param(lambda p: p.pop("predicate_type"), id="missing-predicate"),
        pytest.param(lambda p: p.pop("signer_workflow"), id="missing-signer"),
        pytest.param(lambda p: p.pop("oidc_issuer"), id="missing-issuer"),
        pytest.param(lambda p: p.__setitem__("gh_cli", "not-an-object"), id="gh_cli-not-object"),
        pytest.param(lambda p: p["gh_cli"].pop("version"), id="gh_cli-no-version"),
        pytest.param(lambda p: p.__setitem__("repository", ""), id="empty-repository"),
    ],
)
def test_a_broken_policy_is_a_policy_reason(mutate):
    """سببٌ يسمّي **السياسة** لا المُصادِق — وإلّا بحث المُصلِح في المكان الخطأ."""
    policy = {
        "repository": "o/r",
        "predicate_type": "p",
        "signer_workflow": "w",
        "oidc_issuer": "i",
        "gh_cli": {"version": "2.93.0"},
    }
    mutate(policy)
    with pytest.raises(RuntimeError) as err:
        MOD.validate_policy(policy)
    assert str(err.value) == "POLICY_MISMATCH"


def test_a_valid_policy_passes_through_unchanged():
    """البند الموجب: التحقّق لا يُعدّل ولا يُضيف افتراضات."""
    policy = {
        "repository": "o/r",
        "predicate_type": "p",
        "signer_workflow": "w",
        "oidc_issuer": "i",
        "gh_cli": {"version": "2.93.0"},
    }
    assert MOD.validate_policy(policy) is policy


@pytest.mark.parametrize(
    "value",
    [None, "text", 5, []],
    ids=["none", "string", "number", "list"],
)
def test_a_non_mapping_identity_is_a_source_identity_reason(value):
    with pytest.raises(RuntimeError) as err:
        MOD.require_mapping(value, "SOURCE_IDENTITY_MISMATCH")
    assert str(err.value) == "SOURCE_IDENTITY_MISMATCH"


@pytest.mark.parametrize("value", [None, "", 5, {}], ids=["none", "empty", "number", "dict"])
def test_a_non_string_ref_is_a_source_identity_reason(value):
    with pytest.raises(RuntimeError) as err:
        MOD.require_nonempty_str({"ref": value}, "ref", "SOURCE_IDENTITY_MISMATCH")
    assert str(err.value) == "SOURCE_IDENTITY_MISMATCH"


# ── الإغلاق: بنيةٌ تُتحقَّق لا حقلٌ يُقرأ بافتراض ──────────────────────────


def _manifest_with_closure(tmp_path, closure):
    subject = tmp_path / "subject.txt"
    subject.write_bytes(b"payload")
    doc = {
        "schema": "sahool.evidence-manifest/v1",
        "closure": closure,
        "tested_identity": {"commit_sha": "c", "tree_sha": "t"},
        "source_identity": {"ref": "refs/heads/main"},
        "release_binding": {"mode": "pending_final_rerun"},
        "files": [
            {
                "path": str(subject),
                "sha256": MOD.sha256(subject),
                "size_bytes": subject.stat().st_size,
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_bytes(MOD.canonical_manifest_bytes(doc))
    return path, doc, subject


@pytest.mark.parametrize(
    ("closure", "reason"),
    [
        pytest.param("not-an-object", "MANIFEST_NON_CANONICAL", id="closure-not-object"),
        pytest.param(
            {"mode": "loose", "transport_exclusions": []},
            "MANIFEST_CLOSURE_MISMATCH",
            id="mode-not-exact",
        ),
        pytest.param(
            {"mode": "exact", "transport_exclusions": "x"},
            "MANIFEST_NON_CANONICAL",
            id="exclusions-not-list",
        ),
        pytest.param(
            {"mode": "exact", "transport_exclusions": [{"a": 1}]},
            "MANIFEST_NON_CANONICAL",
            id="exclusion-not-string",
        ),
        pytest.param(
            {"mode": "exact", "transport_exclusions": [""]},
            "MANIFEST_NON_CANONICAL",
            id="exclusion-empty",
        ),
        pytest.param(
            {"mode": "exact", "transport_exclusions": ["a", "a"]},
            "MANIFEST_NON_CANONICAL",
            id="exclusion-duplicated",
        ),
    ],
)
def test_a_malformed_closure_is_rejected_with_its_own_reason(tmp_path, closure, reason):
    path, doc, subject = _manifest_with_closure(tmp_path, closure)
    with pytest.raises(RuntimeError) as err:
        MOD.validate_manifest(path, doc, [subject, path])
    assert str(err.value) == reason


def test_a_subject_cannot_also_be_transport_metadata(tmp_path):
    """ملفٌّ موقَّعٌ ومُستثنىً معاً يُخرِج بايتاته من الإغلاق ويُحسَب مُغطّىً."""
    subject = tmp_path / "subject.txt"
    subject.write_bytes(b"payload")
    closure = {"mode": "exact", "transport_exclusions": [str(subject)]}
    path, doc, subject = _manifest_with_closure(tmp_path, closure)
    with pytest.raises(RuntimeError) as err:
        MOD.validate_manifest(path, doc, [subject, path])
    assert str(err.value) == "MANIFEST_CLOSURE_MISMATCH"


# ── اتّساق الربط: الحقل غير المستعمَل ليس حرّاً ────────────────────────────


@pytest.mark.parametrize(
    ("binding", "bound"),
    [
        pytest.param({"mode": "exact_commit", "accepted_commit_sha": "c"}, True, id="commit-only"),
        pytest.param(
            {"mode": "exact_commit", "accepted_commit_sha": "c", "accepted_tree_sha": "t"},
            True,
            id="commit-with-matching-tree",
        ),
        pytest.param(
            {"mode": "exact_commit", "accepted_commit_sha": "c", "accepted_tree_sha": "WRONG"},
            False,
            id="commit-with-conflicting-tree",
        ),
        pytest.param({"mode": "exact_tree", "accepted_tree_sha": "t"}, True, id="tree-only"),
        pytest.param(
            {"mode": "exact_tree", "accepted_tree_sha": "t", "accepted_commit_sha": "c"},
            True,
            id="tree-with-matching-commit",
        ),
        pytest.param(
            {"mode": "exact_tree", "accepted_tree_sha": "t", "accepted_commit_sha": "WRONG"},
            False,
            id="tree-with-conflicting-commit",
        ),
    ],
)
def test_the_verifier_rejects_a_manifest_that_contradicts_itself(binding, bound):
    """المُصادِق لا يفترض أنّ البيان جاء من الأداة الرسميّة."""
    manifest = {"tested_identity": {"commit_sha": "c", "tree_sha": "t"}, "release_binding": binding}
    assert MOD.release_bound(manifest, _policy(), "refs/heads/main") is bound


# ── الأداة المُنتِجة: ترفض ما يرفضه الحارس، فلا يُولَد بيانٌ متناقض أصلاً ────

# بصماتٌ كاملة (٤٠ خانة): الأداة ترفض المختصر بـ`SOURCE_IDENTITY_MISMATCH`،
# فقيمةٌ قصيرة كانت ستجعل اختبار **الربط** يخضرّ لسببٍ غير سببه المُعلَن.
_C = "c" * 40
_T = "d" * 40
_WRONG = "e" * 40

_BUILDER_PATH = ROOT / "scripts/ci/sot_evidence_manifest.py"
_builder_spec = importlib.util.spec_from_file_location("sot_evidence_manifest", _BUILDER_PATH)
assert _builder_spec is not None and _builder_spec.loader is not None
BUILDER = importlib.util.module_from_spec(_builder_spec)
_builder_spec.loader.exec_module(BUILDER)


def _builder_argv(tmp_path, subject, **extra):
    argv = [
        "--output",
        str(tmp_path / "m.json"),
        "--file",
        str(subject),
        "--tested-commit",
        _C,
        "--tested-tree",
        _T,
        "--source-ref",
        "refs/heads/main",
    ]
    for key, value in extra.items():
        argv += [f"--{key.replace('_', '-')}", value]
    return argv


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(
            {
                "binding_mode": "exact_commit",
                "accepted_commit_sha": _C,
                "accepted_tree_sha": _WRONG,
            },
            id="exact_commit-conflicting-tree",
        ),
        pytest.param(
            {
                "binding_mode": "exact_tree",
                "accepted_tree_sha": _T,
                "accepted_commit_sha": _WRONG,
            },
            id="exact_tree-conflicting-commit",
        ),
        pytest.param(
            {"binding_mode": "pending_final_rerun", "accepted_commit_sha": _C},
            id="pending-with-commit",
        ),
        pytest.param(
            {"binding_mode": "pending_final_rerun", "accepted_tree_sha": _T},
            id="pending-with-tree",
        ),
        pytest.param(
            {"binding_mode": "exact_commit", "accepted_commit_sha": _WRONG},
            id="exact_commit-wrong-commit",
        ),
        pytest.param(
            {"binding_mode": "exact_tree", "accepted_tree_sha": _WRONG}, id="exact_tree-wrong-tree"
        ),
    ],
)
def test_the_builder_refuses_to_emit_a_contradictory_manifest(tmp_path, extra):
    subject = tmp_path / "s.txt"
    subject.write_bytes(b"x")
    with pytest.raises(SystemExit) as err:
        BUILDER.main(_builder_argv(tmp_path, subject, **extra))
    assert "RELEASE_BINDING_MISMATCH" in str(err.value)


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"binding_mode": "pending_final_rerun"}, id="pending-bare"),
        pytest.param(
            {"binding_mode": "exact_commit", "accepted_commit_sha": _C}, id="exact_commit-clean"
        ),
        pytest.param(
            {"binding_mode": "exact_commit", "accepted_commit_sha": _C, "accepted_tree_sha": _T},
            id="exact_commit-consistent-tree",
        ),
        pytest.param(
            {"binding_mode": "exact_tree", "accepted_tree_sha": _T}, id="exact_tree-clean"
        ),
    ],
)
def test_the_builder_emits_consistent_manifests(tmp_path, extra):
    """البند الموجب: التشديد لم يمنع الحالات المشروعة."""
    subject = tmp_path / "s.txt"
    subject.write_bytes(b"x")
    assert BUILDER.main(_builder_argv(tmp_path, subject, **extra)) == 0


# ── نطاق المرجع: من أين جاء الدليل، لا اتّساق بصماته وحده ────────────────────
# `UNPROTECTED-BRANCH-CAN-ATTAIN-L5-01` — كانت `release_bound` تقيس تطابق الالتزام
# والشجرة ولا تسأل عن المرجع، فبلغت دفعةٌ إلى فرع عملٍ غير محميّ المستوى L5.
# الحادثة مقيسة لا مفترَضة: `attestation/40374289` على `ffc29415`.

_FEATURE_REF = "refs/heads/claude/project-exploration-dtjw3p"


def _exact_commit_manifest(commit="a" * 40, tree="b" * 40):
    return {
        "tested_identity": {"commit_sha": commit, "tree_sha": tree},
        "release_binding": {
            "mode": "exact_commit",
            "accepted_commit_sha": commit,
            "accepted_tree_sha": tree,
        },
    }


def test_a_feature_branch_with_exact_commit_binding_is_not_release_bound():
    """الحالة التي وقعت: ربطٌ سليمٌ تماماً على فرعٍ غير معتمد ⇒ ليس إصداراً.

    كلّ ما في البيان صحيح — الالتزام يطابق والشجرة تطابق — والناقص أنّ المصدر
    فرعُ عمل. فالضمان دالّةٌ في المصدر أيضاً، لا في الاتّساق وحده.
    """
    assert MOD.release_bound(_exact_commit_manifest(), _policy(), _FEATURE_REF) is False


def test_the_same_manifest_on_an_authorised_ref_is_release_bound():
    """والمقابلة تُثبِت أنّ الفحص يقيس المرجع لا يرفض الجميع."""
    assert MOD.release_bound(_exact_commit_manifest(), _policy(), "refs/heads/main") is True


@pytest.mark.parametrize(
    "ref",
    [
        "refs/heads/main-backup",  # بادئةٌ تتشبّه بـmain
        "refs/heads/mainline",
        "refs/tags/v9.1.0",  # وسمٌ غير مُعلَن في السياسة
        "refs/pull/835/merge",
    ],
    ids=["main-prefix-lookalike", "mainline", "undeclared-tag", "pr-merge-ref"],
)
def test_refs_that_merely_resemble_a_release_ref_are_rejected(ref):
    """المطابقة تامّة لا بادئة — وإلّا صار `main-backup` إصداراً."""
    assert MOD.release_bound(_exact_commit_manifest(), _policy(), ref) is False


def test_exact_tree_binding_is_also_scoped_by_ref():
    """الوضع الثاني الذي يقول «المصدر هو الإصدار» يخضع للقاعدة نفسها."""
    m = {
        "tested_identity": {"commit_sha": "c", "tree_sha": "t"},
        "release_binding": {"mode": "exact_tree", "accepted_tree_sha": "t"},
    }
    assert MOD.release_bound(m, _policy(), _FEATURE_REF) is False
    assert MOD.release_bound(m, _policy(), "refs/heads/main") is True


def test_merge_to_release_is_measured_by_the_release_ref_it_names():
    """غرضُ هذا الوضع أنّ المصدر **ليس** الإصدار، فيُقاس بمرجعه المقبول لا بمصدره."""
    base = {
        "tested_identity": {"commit_sha": "c", "tree_sha": "t"},
        "release_binding": {
            "mode": "tested_merge_to_release",
            "accepted_commit_sha": "c",
            "accepted_tree_sha": "t",
            "binding_evidence": "merge-preview",
        },
    }
    # بلا تسمية الإصدار ⇒ رفضٌ لا تساهُل.
    assert MOD.release_bound(base, _policy(), _FEATURE_REF) is False
    named = {
        **base,
        "release_binding": {**base["release_binding"], "accepted_ref": "refs/heads/main"},
    }
    assert MOD.release_bound(named, _policy(), _FEATURE_REF) is True
    astray = {**base, "release_binding": {**base["release_binding"], "accepted_ref": _FEATURE_REF}}
    assert MOD.release_bound(astray, _policy(), _FEATURE_REF) is False


def test_a_policy_without_a_release_ref_list_is_an_incomplete_contract_not_a_permissive_one():
    """سياسةٌ بلا قائمة لا تُقرَأ «كلّ المراجع مقبولة» — تفشل مغلقةً."""
    policy = {k: v for k, v in _policy().items() if k != "release_refs"}
    with pytest.raises(RuntimeError, match="RELEASE_REF_POLICY_MISSING"):
        MOD.release_bound(_exact_commit_manifest(), policy, "refs/heads/main")


def test_the_shipped_policy_declares_its_release_refs():
    """العقد بياناتٌ في السياسة المُصدَّرة لا شرطٌ في YAML — وإلّا حرس مساراً واحداً."""
    shipped = json.loads(
        (ROOT / "docs" / "architecture" / "sot_provenance_policy.json").read_text(encoding="utf-8")
    )
    assert shipped["release_refs"] == ["refs/heads/main"]
