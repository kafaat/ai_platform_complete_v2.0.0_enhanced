#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

LEVELS = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
REASONS = {
    "MANIFEST_MISSING",
    "MANIFEST_NON_CANONICAL",
    "MANIFEST_CLOSURE_MISMATCH",
    "SUBJECT_DIGEST_MISMATCH",
    "MANIFEST_NOT_ATTESTED",
    "ATTESTATION_LOOKUP_UNAVAILABLE",
    "ATTESTATION_CRYPTO_INVALID",
    "TRUST_ROOT_INVALID",
    "SIGNER_REPOSITORY_MISMATCH",
    "SIGNER_WORKFLOW_MISMATCH",
    "OIDC_ISSUER_MISMATCH",
    "SOURCE_IDENTITY_MISMATCH",
    "RELEASE_BINDING_MISMATCH",
    "POLICY_MISMATCH",
    "TOOLCHAIN_MISMATCH",
    "VERIFIER_INTERNAL_ERROR",
    # ATTESTED-IS-NOT-CERTIFIED-01 — أسبابُ الاعتماد، لا أسبابُ المنشأ.
    "EXECUTION_OUTCOME_MISSING",
    "EXECUTION_OUTCOME_UNREADABLE",
    "EXECUTION_OUTCOME_FOREIGN_COMMIT",
    "EXECUTION_RUN_NOT_SUCCESSFUL",
    "EXECUTION_JOBS_UNDECLARED",
    "EXECUTION_JOB_NOT_SUCCESSFUL",
    "EXECUTION_OUTCOME_NOT_ENFORCED",
    # عقد الوظائف المطلوبة: required ⊆ observed، وكلّ مطلوبةٍ حاضرة ناجحة.
    "REQUIRED_JOBS_CONTRACT_INVALID",
    "EXECUTION_REQUIRED_JOB_MISSING",
    "EXECUTION_REQUIRED_JOB_NOT_SUCCESSFUL",
    # إغلاق هويّة التشغيل على الـtuple الكاملة بين هويّة الدليل وخلاصة التشغيل.
    "PRODUCER_IDENTITY_MISSING",
    "RUN_IDENTITY_MISMATCH",
    # عقد المصنوعة: exactly-one باسمٍ مشتقٍّ من head_sha مع artifact_id + digest.
    "ARTIFACT_CONTRACT_INVALID",
}


def require_mapping(value: object, reason: str) -> dict:
    """قاموسٌ أو سببٌ دقيق — لا `KeyError` يُبلَّغ عطلاً داخليّاً."""
    if not isinstance(value, dict):
        raise RuntimeError(reason)
    return value


def require_nonempty_str(mapping: dict, key: str, reason: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(reason)
    return value


def validate_policy(policy: dict) -> dict:
    """السياسة تُتحقَّق **قبل** بناء الأمر أو فحص الأداة.

    الفهرسة المباشرة تُحوِّل حقلاً ناقصاً إلى `KeyError` ⇒ `VERIFIER_INTERNAL_ERROR`،
    فيبحث قارئ السجلّ عن عطبٍ في المُصادِق بينما العطب في **السياسة**. والفشل
    مغلقٌ في الحالين، لكنّ السبب المبهم يُطيل التشخيص ويُخفي مَن يُصلِح.
    """
    require_mapping(policy, "POLICY_MISMATCH")
    for key in ("repository", "predicate_type", "signer_workflow", "oidc_issuer"):
        require_nonempty_str(policy, key, "POLICY_MISMATCH")
    gh_cli = require_mapping(policy.get("gh_cli"), "POLICY_MISMATCH")
    require_nonempty_str(gh_cli, "version", "POLICY_MISMATCH")
    return policy


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("document is not an object")
    return value


def canonical_manifest_bytes(doc: dict) -> bytes:
    return (
        json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def validate_manifest(manifest_path: Path, manifest: dict, artifact_files: list[Path]) -> None:
    if manifest.get("schema") != "sahool.evidence-manifest/v1":
        raise RuntimeError("POLICY_MISMATCH")
    if manifest_path.read_bytes() != canonical_manifest_bytes(manifest):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("MANIFEST_MISSING")
    expected_paths = set()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise RuntimeError("MANIFEST_NON_CANONICAL")
        path = Path(item["path"])
        expected_paths.add(path.as_posix())
        if not path.is_file():
            raise RuntimeError("MANIFEST_MISSING")
        actual_digest = sha256(path)
        expected_digest = item.get("sha256")
        if actual_digest != expected_digest:
            raise RuntimeError("SUBJECT_DIGEST_MISMATCH")
        if path.stat().st_size != item.get("size_bytes"):
            raise RuntimeError("SUBJECT_DIGEST_MISMATCH")
    # الإغلاق عقدٌ يُتحقَّق، لا حقلٌ يُقرأ بافتراض شكله: `.get("closure", {})`
    # يبتلع قاموساً مفقوداً، و`set(...)` على غير قائمةٍ نصّيّة يرمي `TypeError`
    # فيُبلَّغ عطلاً داخليّاً. والوضع نفسه لم يكن مفحوصاً أصلاً رغم أنّ السياسة
    # تفترضه `exact`.
    closure = require_mapping(manifest.get("closure"), "MANIFEST_NON_CANONICAL")
    if closure.get("mode") != "exact":
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")
    raw_exclusions = closure.get("transport_exclusions")
    if not isinstance(raw_exclusions, list):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    if any(not isinstance(x, str) or not x for x in raw_exclusions):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    if len(raw_exclusions) != len(set(raw_exclusions)):
        raise RuntimeError("MANIFEST_NON_CANONICAL")
    exclusions = set(raw_exclusions)
    # وملفٌّ لا يكون **موضوعاً موقَّعاً ومُستثنىً نقلاً** في آنٍ واحد: ذلك يُخرِج
    # بايتاته من الإغلاق بينما يُحسَب مُغطّىً.
    if exclusions & expected_paths:
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")
    allowed_paths = expected_paths | exclusions | {manifest_path.as_posix()}
    actual_paths = {p.as_posix() for p in artifact_files}
    if actual_paths != allowed_paths:
        raise RuntimeError("MANIFEST_CLOSURE_MISMATCH")


def build_gh_command(
    *,
    gh: str,
    subject: Path,
    bundle: Path,
    trusted_root: Path,
    policy: dict,
    tested_commit: str,
    source_ref: str,
) -> list[str]:
    return [
        gh,
        "attestation",
        "verify",
        str(subject),
        "--repo",
        policy["repository"],
        "--bundle",
        str(bundle),
        "--custom-trusted-root",
        str(trusted_root),
        "--predicate-type",
        policy["predicate_type"],
        "--signer-workflow",
        policy["signer_workflow"],
        "--cert-oidc-issuer",
        policy["oidc_issuer"],
        "--source-digest",
        tested_commit,
        "--source-ref",
        source_ref,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]


def verify_subject(
    subject: Path,
    *,
    gh: str,
    bundle: Path,
    trusted_root: Path,
    policy: dict,
    tested_commit: str,
    source_ref: str,
) -> dict:
    proc = subprocess.run(
        build_gh_command(
            gh=gh,
            subject=subject,
            bundle=bundle,
            trusted_root=trusted_root,
            policy=policy,
            tested_commit=tested_commit,
            source_ref=source_ref,
        ),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    returncode = proc.returncode
    if returncode != 0:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID") from exc
    if not isinstance(parsed, list) or not parsed:
        raise RuntimeError("ATTESTATION_CRYPTO_INVALID")
    return {"subject": str(subject), "gh_result_count": len(parsed)}


def release_bound(manifest: dict, policy: dict, source_ref: str) -> bool:
    """أهذا الدليل **مربوطٌ بإصدار**؟ — والمرجع شرطٌ أوّل لا تفصيلٌ أخير.

    الضمان دالّةٌ في **من أين** جاء الدليل، لا في اتّساق بصماته وحده. وكان هذا
    الفحص يقيس تطابق الالتزام/الشجرة ولا يسأل عن المرجع إطلاقاً، فبلغت دفعةٌ إلى
    فرع عملٍ غير محميّ المستوى **L5**: `push` + `exact_commit` + أدلّة حيّة ناجحة
    ⇒ L5، على `refs/heads/claude/…`. مقيسٌ بالحادثة لا مُفترَضاً:
    `attestation/40374289` على `ffc29415` (`UNPROTECTED-BRANCH-CAN-ATTAIN-L5-01`).

    والقائمة تُقرأ من **السياسة المُصدَّرة** لا من YAML: شرطٌ في `ci.yml` وحده
    يحرس مساراً واحداً، ويستطيع أيّ workflow آخر تمرير `exact_commit` من فرعٍ غير
    معتمد. والحكم داخل الحارس يسري على كلّ من يستدعيه.

    و`tested_merge_to_release` يُقاس بمرجعه المقبول لا بمصدره — لأنّ غرض الوضع أنّ
    المصدر **ليس** الإصدار. وغيابُ ذلك المرجع رفضٌ لا تساهُل: وضعٌ يعجز عن تسمية
    إصداره لا يُمنَح ضمانَ إصدار.
    """
    tested = manifest["tested_identity"]
    binding = manifest["release_binding"]
    mode = binding.get("mode")
    if mode == "pending_final_rerun":
        return False

    release_refs = policy.get("release_refs")
    if not isinstance(release_refs, list) or not release_refs:
        # سياسةٌ بلا قائمة مراجع لا تُقرَأ «كلّ المراجع مقبولة» — تُقرَأ عقداً ناقصاً.
        raise RuntimeError("RELEASE_REF_POLICY_MISSING")
    # **حقلٌ متقاطعٌ مخالف يُرفض ولو لم يُستعمَل في هذا الوضع.** بيانٌ يقول
    # «الالتزام مطابق» ويحمل شجرةً مخالفة متناقضٌ داخليّاً؛ وسكوتُ الحارس عنه
    # يجعل التناقض يمرّ لأنّه لا يقرأ ذلك الحقل — والمُصادِق لا يفترض أنّ البيان
    # جاء من الأداة الرسميّة.
    if mode in ("exact_commit", "exact_tree"):
        # هذان الوضعان يقولان «المصدر المُختبَر **هو** الإصدار» — فيُقاسان بمرجعه.
        if source_ref not in release_refs:
            return False
    if mode == "exact_commit":
        if binding.get("accepted_commit_sha") != tested.get("commit_sha"):
            return False
        other = binding.get("accepted_tree_sha")
        return other is None or other == tested.get("tree_sha")
    if mode == "exact_tree":
        if binding.get("accepted_tree_sha") != tested.get("tree_sha"):
            return False
        other = binding.get("accepted_commit_sha")
        return other is None or other == tested.get("commit_sha")
    if mode == "tested_merge_to_release":
        # غرض الوضع أنّ المصدر ليس الإصدار، فالمقياس مرجعُ الإصدار الذي يسمّيه هو.
        return bool(
            binding.get("accepted_ref") in release_refs
            and binding.get("accepted_commit_sha")
            and binding.get("accepted_tree_sha")
            and binding.get("binding_evidence")
        )
    raise RuntimeError("RELEASE_BINDING_MISMATCH")


# عقدُ وثيقة الخلاصة كما يُصدره `scripts/ci/run_outcome_guard.py`. مكرَّرٌ هنا لا
# مستورَد: السكربتان مستقلّان ولا يستورد أحدهما الآخر — ويحرس التطابقَ اختبارُ عقدٍ
# يقرأ الاثنين، فلا يبيت النصّان متباعدَين.
EXECUTION_OUTCOME_SCHEMA = "sahool.execution-outcome/v1"
REQUIRED_JOBS_SCHEMA = "sahool.execution-required-jobs/v1"
ARTIFACT_CONTRACT_SCHEMA = "sahool.certify-artifact-contract/v1"


def load_required_jobs_contract(path: Path) -> dict:
    """عقد الوظائف المطلوبة — ملفٌّ versioned يُتحقَّق شكلُه قبل أن يُقاس به.

    عقدٌ لا يُقرأ أو مكرَّرُ الأسماء أو متداخلُ القائمتين ليس عقداً أضعف — هو
    غيابُ عقد، والفشل مغلق: ``REQUIRED_JOBS_CONTRACT_INVALID`` لا حكمٌ جزئيّ.
    """
    try:
        contract = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID") from None
    if contract.get("schema") != REQUIRED_JOBS_SCHEMA:
        raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID")
    require_nonempty_str(contract, "workflow_path", "REQUIRED_JOBS_CONTRACT_INVALID")
    required = contract.get("required_jobs")
    tolerated = contract.get("tolerated_jobs")
    for names in (required, tolerated):
        if not isinstance(names, list) or any(not isinstance(x, str) or not x for x in names):
            raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID")
        if len(names) != len(set(names)):
            raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID")
    if not required:
        # قائمةُ مطلوبٍ فارغة تجعل `required ⊆ observed` صادقاً عن كلّ تشغيل —
        # عقدٌ يرضى بكلّ شيء ليس عقداً.
        raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID")
    if set(required) & set(tolerated):
        # وظيفةٌ مطلوبةٌ ومُتسامَحٌ معها في آنٍ تناقضٌ داخليّ: المطلوب يُشترَط نجاحُه.
        raise RuntimeError("REQUIRED_JOBS_CONTRACT_INVALID")
    return contract


def required_jobs_clean(outcome: dict, contract: dict) -> list[str]:
    """``required ⊆ observed`` وكلّ مطلوبةٍ ناجحة — والحضورُ «مرّةً واحدة» يفرضه
    المُنتِج برفض الأسماء المكرَّرة في الجرد قبل أن تبتلعها مفاتيحُ القاموس."""
    if contract.get("workflow_path") != outcome.get("workflow_path"):
        # عقدٌ عن workflow آخر لا يشهد لهذا التشغيل — ولا يُقرأ «لا قيد».
        return ["REQUIRED_JOBS_CONTRACT_INVALID"]
    jobs = outcome.get("job_conclusions")
    jobs = jobs if isinstance(jobs, dict) else {}
    reasons: set[str] = set()
    for name in contract["required_jobs"]:
        if name not in jobs:
            reasons.add("EXECUTION_REQUIRED_JOB_MISSING")
        elif jobs[name] != "success":
            reasons.add("EXECUTION_REQUIRED_JOB_NOT_SUCCESSFUL")
    return sorted(reasons)


def run_identity_clean(outcome: dict, manifest: dict, policy: dict) -> list[str]:
    """إغلاق هويّة التشغيل على الـtuple الكاملة — لا على SHA وحده.

    الدليل يحمل هويّة مُنتِجه **داخل الموضوع الموقَّع** (``producer_identity`` في
    البيان)، وخلاصةُ التشغيل تُقرأ من الواجهة بعد الاكتمال. والإغلاق يطابق:
    repository · workflow_path · run_id · run_attempt · head_sha · source_ref ·
    event بين الاثنين. فخلاصةُ تشغيلٍ آخر — ولو على الالتزام نفسه (إعادةُ تشغيل،
    محاولةٌ ثانية) — لا تشهد لهذا الدليل.
    """
    producer = manifest.get("producer_identity")
    if not isinstance(producer, dict):
        return ["PRODUCER_IDENTITY_MISSING"]
    tested = manifest.get("tested_identity")
    tested = tested if isinstance(tested, dict) else {}
    source = manifest.get("source_identity")
    source = source if isinstance(source, dict) else {}
    # `run_attempt` يصل من البيئة نصّاً ومن الواجهة عدداً — فيُطبَّع الطرفان نصّاً
    # قبل المطابقة، والغائب يصير "None" فلا يطابق شيئاً حقيقيّاً: فشلٌ مغلق.
    closures = (
        str(producer.get("repository")) == str(policy.get("repository")),
        str(outcome.get("repository")) == str(policy.get("repository")),
        str(producer.get("workflow_path")) == str(outcome.get("workflow_path")),
        str(producer.get("run_id")) == str(outcome.get("run_id")),
        str(producer.get("run_attempt")) == str(outcome.get("run_attempt")),
        str(producer.get("event")) == str(outcome.get("event")),
        str(outcome.get("head_sha")) == str(tested.get("commit_sha")),
        str(source.get("ref")) == f"refs/heads/{outcome.get('head_branch')}",
    )
    return [] if all(closures) else ["RUN_IDENTITY_MISMATCH"]


def load_artifact_provenance(path: Path, tested_commit: str) -> dict:
    """سجلُّ عقد المصنوعة كما أنتجه ``certify_artifact_contract.py`` — يُتحقَّق أنّه
    عن **هذه** اللقطة وبحالة ``present`` قبل أن يُضمَّن في سجلّ الاعتماد."""
    try:
        doc = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        raise RuntimeError("ARTIFACT_CONTRACT_INVALID") from None
    if doc.get("schema") != ARTIFACT_CONTRACT_SCHEMA:
        raise RuntimeError("ARTIFACT_CONTRACT_INVALID")
    if doc.get("status") != "present" or doc.get("head_sha") != tested_commit:
        raise RuntimeError("ARTIFACT_CONTRACT_INVALID")
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"evidence", "attestation"}:
        raise RuntimeError("ARTIFACT_CONTRACT_INVALID")
    for entry in artifacts.values():
        entry = require_mapping(entry, "ARTIFACT_CONTRACT_INVALID")
        if not isinstance(entry.get("artifact_id"), int):
            raise RuntimeError("ARTIFACT_CONTRACT_INVALID")
        require_nonempty_str(entry, "name", "ARTIFACT_CONTRACT_INVALID")
        require_nonempty_str(entry, "digest", "ARTIFACT_CONTRACT_INVALID")
    return doc


def outcome_unreadable(outcome: object) -> bool:
    """أهي وثيقةٌ **بالشكل المتعاقَد عليه**؟ — سؤالٌ سابقٌ على أيّ حكمٍ على التشغيل.

    رفعته مراجعةٌ آليّة على #844 وأصابت، والعطل أطروحةُ هذه الـPR مطبَّقةً على
    شيفرتها: وثيقةٌ مشوَّهة — ينقصها ``run_conclusion`` مثلاً — كانت تُبلَّغ
    ``EXECUTION_RUN_NOT_SUCCESSFUL``، وتلك **دعوى عن التشغيل** («انتهى فاشلاً») لا
    عن الوثيقة («تعذّر أن أقرأها»). والفرق ليس تجميلَ رسالة: رموزُ الأسباب هي سجلّ
    التدقيق، فيقرأ قارئُه أنّ تشغيلاً سقط بينما الواقع أنّ الدليل مشوَّه أو مُنتَجٌ
    بأداةٍ أخرى. وهو الصنف نفسه الذي أغلقته هذه الـPR في `changed.txt`: «تعذّر أن
    أعرف» يُكتَب بلغة «عرفتُ أنّه لا».

    والشقّ الثاني من الملاحظة مقيسٌ كذلك: بلا فحص ``schema`` تمرّ **أيّ** وثيقةٍ
    تصادف أن تحمل المفاتيح المفحوصة — فيصير المُنتِج غير مُلزِم، وتُقبَل حمولةٌ من
    أداةٍ لم تُكتَب لهذا العقد.

    الفراغُ ليس تشوّهاً: ``job_conclusions`` قاموسٌ فارغ **مقروء**، وحكمُه
    ``EXECUTION_JOBS_UNDECLARED`` — «لم تُقرأ» ليست «كلّها نجحت»، وذاك حكمٌ آخر.
    """
    if not isinstance(outcome, dict):
        return True
    if outcome.get("schema") != EXECUTION_OUTCOME_SCHEMA:
        return True
    if not isinstance(outcome.get("run_conclusion"), str):
        return True
    if not isinstance(outcome.get("head_sha"), str):
        return True
    # جردٌ غائب أو غير قاموسيّ **تشوّهُ وثيقة** لا حكمَ وظائف: قبولُه هنا كان
    # يُبلِّغه لاحقاً `EXECUTION_JOBS_UNDECLARED` — «تعذّر أن أقرأ» بلغة «قرأتُ
    # أنّها لم تُعلَن» — ويُدخِل وثيقةً مشوَّهة إلى عقد الوظائف المطلوبة.
    # القاموس الفارغ يبقى مقروءاً وحكمُه لنفسه (رفعته مراجعة آليّة وأصابت).
    jobs = outcome.get("job_conclusions")
    if not isinstance(jobs, dict):
        return True
    if any(not isinstance(v, str) for v in jobs.values()):
        return True
    return False


def execution_clean(
    outcome: object, tested_commit: str, tolerated: frozenset[str] = frozenset()
) -> tuple[bool, str]:
    """أنتجَ هذا الدليلَ تشغيلٌ **نجح**؟ — ``(نظيف، سببُ الرفض)``.

    **ولماذا وثيقةٌ منفصلة لا حقلٌ في البيان — تصحيحٌ لصياغتي الأولى:**
    ``live_pg_canonical_manifest.json`` **من الموضوعات الموقَّعة الأربعة**، فبصمتُه
    داخل الشهادة. وإضافةُ ``execution_outcome`` إليه بعد التشغيل تُغيّر تلك البصمة
    فتكسر التحقّق — أي أنّ التصميم الأوّل كان **غير قابل للتنفيذ** لا مجرّد أضعف.
    فالخلاصة تُقرأ من واجهة GitHub بعد اكتمال التشغيل وتُسلَّم ملفّاً مستقلّاً،
    ويبقى الرابطُ بينهما **الالتزامَ المُختبَر** لا مجاورةً في ملفّ.

    `ATTESTED-IS-NOT-CERTIFIED-01`. الشهادةُ تقول بصدق «GitHub Actions بهذا الـworkflow
    وهذه اللقطة أنتج هذه المصنوعات ووقّع منشأها». وهذا **لا** يقول إنّ اللقطة اجتازت
    البوّابة: تشغيلٌ تفشل فيه وظيفةُ اختبارات يُنتِج مصنوعاتٍ سليمة ويوقّعها، وتخرج
    الحزمة صحيحة تشفيريّاً بالكامل — توقيعٌ صالح، وربطُ payload بـRekor، وإثبات Merkle،
    وهويّة Fulcio متماسكة. فالتحقّق التشفيريّ يُثبِت **من قال ماذا وعن أيّ بايتات**؛
    وسياسةُ المشروع وحدها تقرّر هل ذلك كافٍ للاعتماد.

    **والحدّ الذي كان مفتوحاً هنا مقيس:** ``evidence_passes`` يقرأ حكمَي مصنوعتَي
    Live-PG ولا يقرأ **خلاصة التشغيل**. ولا شيء في ``scripts/`` كان يقرؤها (مقيس
    بمسحٍ على الشجرة كلّها: صفر موضع). فدليلٌ من تشغيلٍ خلاصتُه ``failure`` كان يبلغ
    L4/L5 ما دامت مصنوعتاه تقولان ``PASS`` — وهو بعينه «attested ⇒ certified»، أي
    خلطُ **دليل المنشأ** بـ**دليل الاعتماد**.

    **وغيابُ الكتلة لا يُقرأ نجاحاً:** بيانٌ لا يُعلِن خلاصة تشغيله لا يُمنَح ضمانَ
    إصدار — يبقى عند L3 ويُسمّى السببُ في السجلّ. و«لم يُقَس» ليس «مرّ».

    **والربط بالالتزام شرطٌ لا زينة:** خلاصةُ تشغيلٍ آخر — ولو ناجحاً — لا تشهد لهذه
    اللقطة. فيُطابَق ``head_sha`` بالالتزام المُختبَر.
    """
    if not isinstance(outcome, dict):
        return False, "EXECUTION_OUTCOME_MISSING"
    if outcome_unreadable(outcome):
        return False, "EXECUTION_OUTCOME_UNREADABLE"
    if outcome.get("run_conclusion") != "success":
        return False, "EXECUTION_RUN_NOT_SUCCESSFUL"
    jobs = outcome.get("job_conclusions")
    if not isinstance(jobs, dict) or not jobs:
        return False, "EXECUTION_JOBS_UNDECLARED"
    # `tolerated` من عقد الوظائف المطلوبة versioned لا من ثابتٍ مدفون: وظيفةٌ
    # مُسمّاة فيه لا يُدان التشغيل بعدم نجاحها — والقائمة المشحونة فارغة، فالحقل
    # يُقرأ فارغاً بوضوح بدل استثناءٍ صامت أوّلَ ما يُزعِج.
    if any(value != "success" for name, value in jobs.items() if name not in tolerated):
        return False, "EXECUTION_JOB_NOT_SUCCESSFUL"
    if outcome.get("head_sha") != tested_commit:
        return False, "EXECUTION_OUTCOME_FOREIGN_COMMIT"
    return True, ""


def evidence_passes() -> bool:
    try:
        ev = load_json(Path("live_pg_evidence.json"))
        role = load_json(Path("live_pg_role_closure.json"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return ev.get("verdict") == "PASS" and role.get("verdict") == "PASS"


def toolchain(gh: str, policy: dict) -> dict:
    proc = subprocess.run([gh, "--version"], text=True, encoding="utf-8", capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    first = proc.stdout.splitlines()[0] if proc.stdout else ""
    expected = policy["gh_cli"]["version"]
    if f"gh version {expected}" not in first:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    return {"gh_version": first, "gh_binary_sha256": sha256(Path(gh))}


def resolve_executable(value: str | None) -> str:
    """يحلّ الأداة إلى **مسارٍ فعليّ** مرّةً واحدة قبل أيّ استعمال.

    البصمة جزءٌ من سجلّ التحقّق، واسمُ أمرٍ لا يُبصَم: `--gh-bin gh` ينجح عبر
    `PATH` في `subprocess` ثمّ يسقط في `sha256(Path("gh"))`، فيُبلَّغ خطأً
    داخليّاً وسببُه أنّ الأداة لم تُحلَّ. و`resolve()` يفكّ الوصلات الرمزيّة
    فتصير **البايتات المُبصَمة عين ما استُدعي** — لا ملفّاً يشير إليه.
    """
    candidate = value or "gh"
    if "/" in candidate:
        path = Path(candidate).resolve()
        if not path.is_file():
            raise RuntimeError("TOOLCHAIN_MISMATCH")
        return str(path)
    resolved = shutil.which(candidate)
    if not resolved:
        raise RuntimeError("TOOLCHAIN_MISMATCH")
    return str(Path(resolved).resolve())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--trusted-root", required=True)
    ap.add_argument("--artifact-file", action="append", required=True)
    ap.add_argument("--required-assurance", choices=list(LEVELS), default="L3")
    ap.add_argument(
        "--execution-outcome",
        help=(
            "وثيقةُ خلاصة التشغيل (run_conclusion · job_conclusions · head_sha). "
            "تُقرأ من واجهة GitHub **بعد** اكتمال التشغيل — لا تُولَّد من داخله."
        ),
    )
    ap.add_argument(
        "--require-execution-outcome",
        action="store_true",
        help=(
            "افرِض خلاصةَ تشغيلٍ ناجحة لبلوغ L4/L5. تستعمله وظيفةُ الاعتماد بعد "
            "انتهاء التشغيل؛ والاستدعاءُ **داخل** التشغيل لا يستطيعها فيُسجّل الدَّين."
        ),
    )
    ap.add_argument(
        "--required-jobs-contract",
        help=(
            "ملفُّ عقد الوظائف المطلوبة versioned (required ⊆ observed، وكلّ مطلوبةٍ "
            "حاضرة مرّةً واحدة ناجحة). يُمرَّر في وظيفة الاعتماد حيث تُعرَف الوظائف."
        ),
    )
    ap.add_argument(
        "--artifact-provenance",
        help=(
            "سجلُّ عقد المصنوعة (exactly-one باسمٍ مشتقٍّ من head_sha، مع artifact_id "
            "وdigest). يُتحقَّق أنّه عن اللقطة المشهود لها ثمّ يُضمَّن في سجلّ الاعتماد."
        ),
    )
    ap.add_argument("--output", required=True)
    ap.add_argument("--gh-bin")
    args = ap.parse_args(argv)

    record = {"verdict": "BLOCKED", "reason_codes": [], "assurance_level": "L0"}
    try:
        manifest_path, policy_path = Path(args.manifest), Path(args.policy)
        bundle, trusted_root = Path(args.bundle), Path(args.trusted_root)
        if not manifest_path.is_file():
            raise RuntimeError("MANIFEST_MISSING")
        if not bundle.is_file():
            raise RuntimeError("ATTESTATION_LOOKUP_UNAVAILABLE")
        if not trusted_root.is_file() or trusted_root.stat().st_size == 0:
            raise RuntimeError("TRUST_ROOT_INVALID")
        manifest = load_json(manifest_path)
        policy = validate_policy(load_json(policy_path))
        validate_manifest(manifest_path, manifest, [Path(x) for x in args.artifact_file])
        tested = require_mapping(manifest.get("tested_identity"), "SOURCE_IDENTITY_MISMATCH")
        source = require_mapping(manifest.get("source_identity"), "SOURCE_IDENTITY_MISMATCH")
        require_nonempty_str(tested, "commit_sha", "SOURCE_IDENTITY_MISMATCH")
        source_ref = require_nonempty_str(source, "ref", "SOURCE_IDENTITY_MISMATCH")
        gh = resolve_executable(args.gh_bin)
        tc = toolchain(gh, policy)
        subjects = [Path(x["path"]) for x in manifest["files"]] + [manifest_path]
        verified = [
            verify_subject(
                s,
                gh=gh,
                bundle=bundle,
                trusted_root=trusted_root,
                policy=policy,
                tested_commit=tested["commit_sha"],
                source_ref=source_ref,
            )
            for s in subjects
        ]
        level = "L3"
        # ATTESTED-IS-NOT-CERTIFIED-01: الارتقاء إلى L4 يشترط **شرطين مستقلّين**:
        # مرجعاً معتمداً (من أين)، وتشغيلاً ناجحاً أنتج الدليل (بأيّ حال). وسقوطُ
        # الثاني ليس فساداً في الحزمة — هو رفضُ **اعتماد** لدليل منشأٍ صحيح.
        # الخلاصة تُقرأ من ملفّها المستقلّ. وغيابُ الملفّ المُمرَّر ليس «لم يُطلَب»:
        # رايةٌ تشير إلى ملفٍّ لا يُقرأ تعني أنّ الجلب لم يعمل، وقراءةُ ذلك سلامةً
        # هي بعينها «لم يُقَس ⇒ مرّ».
        outcome: object = None
        if args.execution_outcome:
            try:
                outcome = load_json(Path(args.execution_outcome))
            except (OSError, ValueError, json.JSONDecodeError):
                raise RuntimeError("EXECUTION_OUTCOME_UNREADABLE") from None
        jobs_contract = None
        if args.required_jobs_contract:
            jobs_contract = load_required_jobs_contract(Path(args.required_jobs_contract))
        tolerated = frozenset(jobs_contract["tolerated_jobs"]) if jobs_contract else frozenset()
        _, execution_reason = execution_clean(outcome, tested["commit_sha"], tolerated)
        # أسبابُ منع الارتقاء تُجمَع كلُّها لا أوّلُها: سجلٌّ يسمّي سبباً واحداً
        # من ثلاثة يجعل القارئ يُصلِحه ويظنّ الطريق خَلَت.
        promotion_reasons: list[str] = []
        if execution_reason:
            promotion_reasons.append(execution_reason)
        if isinstance(outcome, dict) and not outcome_unreadable(outcome):
            if jobs_contract is not None:
                promotion_reasons += required_jobs_clean(outcome, jobs_contract)
            # إغلاق الهويّة يُقاس متى وُجِدت خلاصةٌ مقروءة — عقد الوظائف اختياريٌّ
            # بالراية، أمّا الهويّة فمن الوثيقتين نفسيهما فلا تُعطَّل براية.
            promotion_reasons += run_identity_clean(outcome, manifest, policy)
        artifact_provenance = None
        if args.artifact_provenance:
            artifact_provenance = load_artifact_provenance(
                Path(args.artifact_provenance), tested["commit_sha"]
            )
        # **ولماذا الشرط مربوطٌ بالسياسة لا مفروضاً اليوم:** خلاصةُ التشغيل لا تُعرَف
        # **من داخله** — وظيفةٌ تعمل الآن لا تستطيع أن تقول كيف انتهى تشغيلُها. فالبيان
        # المُولَّد داخل التشغيل لا يستطيع إعلانها بصدق، وفرضُها اليوم كان يُحمِّر `main`
        # على غياب شيءٍ لا يملك المُنتِج إنتاجه — لا على عطل. والمُنتِج الصحيح وظيفةُ
        # اعتمادٍ **بعد** انتهاء التشغيل (`workflow_run`)، وهي الشريحة التالية.
        # فالقاعدة مكتوبة ومُكذَّبة بأربع طفرات، ومفتاحُها في السياسة سطرٌ واحد.
        require_execution = args.require_execution_outcome or bool(
            policy.get("require_execution_outcome")
        )
        if release_bound(manifest, policy, source_ref) and (
            not promotion_reasons or not require_execution
        ):
            level = "L4"
        if promotion_reasons:
            # تُسجَّل **دائماً**، فارضاً كان أو غير فارض: سجلٌّ يقول L5 ولا يقول
            # «وخلاصةُ التشغيل لم تُعلَن» يُقرَأ اعتماداً وهو ليس منه.
            record["reason_codes"].extend(promotion_reasons)
            if not require_execution:
                record["reason_codes"].append("EXECUTION_OUTCOME_NOT_ENFORCED")
        if level == "L4" and evidence_passes():
            level = "L5"
        if LEVELS[level] < LEVELS[args.required_assurance]:
            raise RuntimeError("RELEASE_BINDING_MISMATCH")
        record.update(
            {
                "verdict": "VERIFIED",
                # **لا تُمسَح الأسباب هنا.** الحكم قد يكون `VERIFIED` عند L3 لأنّ
                # الارتقاء رُفِض — والسببُ هو الخبر كلّه. وتفريغُها كان يجعل الرفض
                # صامتاً: سجلٌّ يقول «تُحقِّق» ولا يقول «ولم يُعتمَد، ولهذا السبب».
                "reason_codes": record["reason_codes"],
                "assurance_level": level,
                "manifest_sha256": sha256(manifest_path),
                "policy_sha256": sha256(policy_path),
                "trusted_root": {
                    "sha256": sha256(trusted_root),
                    "source": "gh attestation trusted-root",
                },
                "attestation_bundle_sha256": sha256(bundle),
                "verification_toolchain": tc,
                "verifier_sha256": sha256(Path(__file__)),
                "tested_identity": tested,
                "release_binding": manifest["release_binding"],
                "verified_subjects": verified,
                # هويّة المُنتِج وعقدا المصنوعة والوظائف يُكتَبون في السجلّ نفسه:
                # `null` يقول بصدق «لم يُمرَّر» — وغيابُ الحقل كان سيقول لا شيء.
                "producer_identity": manifest.get("producer_identity"),
                "artifact_provenance": artifact_provenance,
                "required_jobs_contract_sha256": (
                    sha256(Path(args.required_jobs_contract))
                    if args.required_jobs_contract
                    else None
                ),
            }
        )
    except RuntimeError as e:
        reason = str(e) if str(e) in REASONS else "VERIFIER_INTERNAL_ERROR"
        record["reason_codes"] = [reason]
    except Exception:
        record["reason_codes"] = ["VERIFIER_INTERNAL_ERROR"]

    Path(args.output).write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if record["verdict"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
