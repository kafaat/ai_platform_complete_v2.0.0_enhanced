"""`A-RUNBOOK-THAT-DESCRIBES-UNBUILT-CAPABILITY-01` — الوثيقةُ تصف ما يفعله الكود.

**أصلُ هذا الملفّ حادثةٌ مقيسة.** رَكْضةُ تشغيلٍ قالت «**The workflow now:** يبني
بـ`provenance=mode=max` وSBOM · يُثبّت Trivy ببصمة · يفشل على HIGH/CRITICAL · يُصدِر
مُسنَدين ويتحقّق منهما · ويربط أربعَ بصماتِ أدلّة». والمقيسُ يومَها على `main`:
`provenance: false` · **صفرُ ذكرٍ لـTrivy** · لا SBOM · لا تحقّق · لا بصمات.

**والخطرُ ليس هفوةً توثيقيّة:** مشغّلٌ يتبع الرَّكْضة يُطلِق، فيرى أخضر، فيسجّل أنّ
الصورة فُحِصت وأنّ الجردَ صدر. **فتُصنَع طمأنينةٌ كاذبةٌ داخل سلسلة التوريد التي
وُجِدت الوثيقةُ لحمايتها** — وهو `ATTESTED-IS-NOT-CERTIFIED-01` مقلوباً.

فبعد تنفيذ §٥ و§٦، **تُثبَّت البنودُ هنا واحداً واحداً**: نزعُ أيٍّ منها يُحمِّر،
فتعود الرَّكْضةُ وصفاً لِما يقع لا وعداً بما يُرجى.

**وحدُّ صدقٍ يُقال صراحةً:** المقيسُ هنا **العقدُ في الـYAML** — أنّ الخطوة معلنةٌ
بمعاملاتها الصحيحة. **ولا يُقاس أنّ التشغيل الحقيقيّ نجح**: ذلك يحتاج عدّاءً
موثوقاً وسجلَّ حاويات، وهما خارج ما يفرضه ملفٌّ في الشجرة. الادّعاءُ الصحيح:
«الخطوةُ موجودةٌ ومُعامَلةٌ كما وُصِفت»، لا «الصورةُ فُحِصت».

فحص صرف — ``pytest -m unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
IMAGE_WORKFLOW = ROOT / ".github/workflows/runtime-image-provenance.yml"
PATH3_WORKFLOW = ROOT / ".github/workflows/path3-runtime-verification.yml"

PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
SBOM_PREDICATE = "https://cyclonedx.org/bom"

REQUIRED_EVIDENCE = (
    "scan_sha256",
    "sbom_sha256",
    "provenance_verification_sha256",
    "sbom_verification_sha256",
)


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(path: Path, job: str) -> list[dict]:
    jobs = _workflow(path).get("jobs") or {}
    assert job in jobs, f"وظيفةُ `{job}` اختفت من {path.name} — العقدُ يشير إلى لا شيء"
    return [s for s in (jobs[job].get("steps") or []) if isinstance(s, dict)]


def _build_step(steps: list[dict]) -> dict:
    for step in steps:
        if "build-push-action" in str(step.get("uses") or ""):
            return step
    pytest.fail("خطوةُ البناء اختفت — لا موضوعَ للقياس")


# ── §٥ ② البناءُ يُنتِج منشأً وجرداً ─────────────────────────────────────────
def test_the_build_emits_full_provenance_and_an_sbom():
    """`provenance: false` كان **ينقض اسمَ الـworkflow نفسِه**.

    الملفُّ اسمُه «Runtime Image Provenance» ويوقّع بصمةً، لكنّ BuildKit لم يكن
    يُنتِج مُسنَدَ منشأٍ أصلاً: الشهادةُ تربط البايتات بالتشغيل **ولا تقول كيف
    بُنِيت**.
    """
    parameters = _build_step(_steps(IMAGE_WORKFLOW, "build-and-attest")).get("with") or {}

    assert parameters.get("provenance") == "mode=max", (
        f"`provenance` = {parameters.get('provenance')!r} — يجب `mode=max`؛ "
        "و`false` تُبقي الـworkflow يَعِد بما لا يفعل"
    )
    assert parameters.get("sbom") is True, "`sbom` غير مُفعَّل — الفحصُ بلا جردٍ لا يقول ما فُحِص"


def test_the_image_is_pushed_and_never_only_loaded():
    """**`load: true` يُسقِط المُسنَدات** — فتُبنى صورةٌ تبدو موثَّقةً بلا توثيقٍ في السجلّ."""
    parameters = _build_step(_steps(IMAGE_WORKFLOW, "build-and-attest")).get("with") or {}
    assert parameters.get("push") is True, "الصورةُ لا تُدفَع — لا بصمةَ سجلٍّ يُوقَّع عليها"
    assert parameters.get("load") is not True, "`load: true` يُسقِط المُسنَدات"


# ── §٥ ③④⑤ الفحصُ مثبَّتٌ وحاجبٌ، والجردُ CycloneDX ────────────────────────
def test_trivy_is_installed_from_a_digest_pinned_release():
    """**`--version` ليس مرجعَ ثقة** — المرجعُ رابطُ الإصدار وبصمتُه، ويُطابَقان قبل الفكّ."""
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    step = next((s for s in steps if "Install pinned Trivy" in str(s.get("name") or "")), None)
    assert step is not None, "خطوةُ تثبيت Trivy اختفت"

    script = str(step.get("run") or "")
    environment = step.get("env") or {}
    assert "sha256sum -c -" in script, "لا مطابقةَ بصمةٍ — أداةٌ غيرُ مُثبَّتة تُشغَّل"
    digest = str(environment.get("TRIVY_SHA256") or "")
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (
        f"بصمةُ Trivy غيرُ صالحة: {digest!r}"
    )
    assert "aquasecurity/trivy/releases/download" in script, "المصدرُ ليس إصداراً رسميّاً"


def test_a_missing_vulnerability_database_fails_instead_of_reading_as_clean():
    """**قاعدةٌ غائبةٌ ليست صفرَ ثغرات** — وهو تحويلُ غيابِ البيانات إلى نجاح."""
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    warm = next((s for s in steps if "--download-db-only" in str(s.get("run") or "")), None)
    assert warm is not None, "لا خطوةَ تحميلِ قاعدةٍ تفشل عند تعذّرها"


def test_the_scan_blocks_on_high_and_critical_and_reads_the_digest():
    """يُفحَص بالبصمة لا بالوسم: **الوسمُ قد يُعاد توجيهه بين الفحص والترقية**."""
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    scan = next((s for s in steps if "--severity HIGH,CRITICAL" in str(s.get("run") or "")), None)
    assert scan is not None, "بوّابةُ الفحص اختفت"

    script = str(scan.get("run") or "")
    assert "--exit-code 1" in script, "الفحصُ لا يحجب — يُنتِج تقريراً ويمضي"
    # **المرجعُ قالبٌ يُصيَّر وقتَ التشغيل**، فلا يظهر `@sha256:` نصّاً هنا.
    # المقيسُ الصحيح: يُبنى بـ`@` من **مخرَج البناء** لا بـ`:` من وسم.
    # (أوّلُ صياغةٍ بحثت عن `@sha256:` حرفيّاً فحمّرت على شيفرةٍ صحيحة — قارئٌ
    # نصّيٌّ يقيس ما لا يقصده، وهو الصنفُ نفسُه الذي أمسكني في نداءِ التوسيع.)
    reference = str((scan.get("env") or {}).get("IMAGE_REF") or "")
    assert "@${{ steps.build.outputs.digest }}" in reference, (
        f"الفحصُ يقرأ وسماً لا بصمة: {reference!r}"
    )


def test_a_cyclonedx_sbom_is_generated_for_the_same_digest():
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    sbom = next((s for s in steps if "--format cyclonedx" in str(s.get("run") or "")), None)
    assert sbom is not None, "جردُ CycloneDX اختفى — وهو ما يتحقّق منه PATH-3 بالنوع"


# ── §٥ ⑥⑦ الشهادتان تُصدَران **ويُتحقَّق منهما** ──────────────────────────────
def test_both_predicate_types_are_attested_against_the_digest():
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    uses = " ".join(str(s.get("uses") or "") for s in steps)
    assert "actions/attest-build-provenance" in uses, "لا شهادةَ منشأ"
    assert "actions/attest-sbom" in uses, "لا شهادةَ جرد"

    for step in steps:
        if "attest" in str(step.get("uses") or ""):
            parameters = step.get("with") or {}
            assert "subject-digest" in parameters, "الشهادةُ لا تُثبَّت على بصمة"


def test_issuing_an_attestation_is_not_verifying_it():
    """**`ATTESTED-IS-NOT-CERTIFIED-01`:** حزمةٌ صحيحةٌ تشفيريّاً خرجت من تشغيلٍ فاشل.

    فيُطلَب **كلا النوعين** صراحةً: صورةٌ تحمل منشأً بلا جردٍ تمرّ بفحصٍ واحدٍ
    وتبدو موثَّقة.
    """
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    verify = next((s for s in steps if "gh attestation verify" in str(s.get("run") or "")), None)
    assert verify is not None, "لا تحقّقَ بعد الإصدار — وجودُ الوسم ليس دليلَ منشأ"

    script = str(verify.get("run") or "")
    assert PROVENANCE_PREDICATE in script, "لم يُطلَب نوعُ مُسنَد المنشأ صراحةً"
    assert SBOM_PREDICATE in script, "لم يُطلَب نوعُ مُسنَد الجرد صراحةً"
    assert "--signer-workflow" in script, "التحقّقُ بلا هويّةِ مُوقِّعٍ متوقَّعة"


# ── §٥ ⑧ البصماتُ الأربعُ مربوطةٌ بالبيان ───────────────────────────────────
def test_the_four_evidence_digests_are_bound_into_the_manifest():
    """**مصنوعةٌ بجانب البيان تُستبدَل بلا أن يتغيّر البيان.** والبصمةُ داخله تُحمِّر."""
    steps = _steps(IMAGE_WORKFLOW, "build-and-attest")
    fragment = next(
        (s for s in steps if "image-manifest-fragments" in str(s.get("run") or "")), None
    )
    assert fragment is not None, "كاتبُ شظيّة البيان اختفى"

    script = str(fragment.get("run") or "")
    for key in REQUIRED_EVIDENCE:
        assert key in script, f"بصمةٌ غيرُ مربوطة بالبيان: `{key}`"


def test_the_assembled_manifest_refuses_a_fragment_without_its_evidence():
    """يُرفَض الناقصُ **عند التجميع** لا عند المستهلك — فالبيانُ المُجمَّع هو العقد."""
    steps = _steps(IMAGE_WORKFLOW, "publish-manifest")
    script = " ".join(str(s.get("run") or "") for s in steps)
    assert "REQUIRED_EVIDENCE" in script, "المُجمِّعُ يقبل شظيّةً بلا بصماتها"
    assert "evidence digests missing" in script


# ── §٦ PATH-3 يتحقّق مستقلّاً ويرفض الناقص ─────────────────────────────────
def test_path3_rejects_a_manifest_that_lacks_its_evidence_digests():
    steps = _steps(PATH3_WORKFLOW, "verify-images")
    script = " ".join(str(s.get("run") or "") for s in steps)
    assert "path3_image_evidence_guard.py" in script, (
        "PATH-3 يستهلك بياناً بلا فحصِ بصماته — والناقصُ يُقرأ خُلوّاً"
    )


def test_path3_verifies_both_predicate_types_independently():
    """**مُنتِجٌ يشهد لنفسه ليس شاهداً** — فيُعاد التحقّقُ من غير سياق البناء."""
    steps = _steps(PATH3_WORKFLOW, "verify-images")
    script = " ".join(str(s.get("run") or "") for s in steps)
    assert PROVENANCE_PREDICATE in script, "PATH-3 لا يطلب نوعَ المنشأ"
    assert SBOM_PREDICATE in script, "PATH-3 لا يطلب نوعَ الجرد"
    assert script.count("gh attestation verify") >= 2, "تحقّقٌ واحدٌ لنوعين"


def test_the_evidence_guard_is_falsifiable_without_a_workflow():
    """**الشاهدُ الموجب:** الحارسُ يقبل السليمَ ويرفض كلَّ صنفٍ من النقص.

    وبدونه تبقى البياناتُ أعلاه تأكيداتٍ على **نصٍّ في YAML** بلا دليلٍ على أنّ
    المنطقَ الذي تستدعيه يعمل.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_evidence_guard", ROOT / "scripts/ci/path3_image_evidence_guard.py"
    )
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    good_digest = "a" * 64
    sound = {
        "source_sha": "b" * 40,
        "images": {
            "svc": {
                "image": "ghcr.io/o/svc@sha256:" + "c" * 64,
                "evidence": dict.fromkeys(REQUIRED_EVIDENCE, good_digest),
            }
        },
    }
    assert guard.failures(sound, "b" * 40) == [], "العيّنةُ السليمة تُرفَض — المِقياسُ بلا طرفٍ موجب"

    missing = {"images": {"svc": {"image": sound["images"]["svc"]["image"], "evidence": {}}}}
    assert guard.failures(missing), "بيانٌ بكتلةِ أدلّةٍ فارغة مرّ"

    # **كتلةٌ غائبةٌ ليست كتلةً فارغة** — وطفرةٌ مُسجَّلة نجت من الصياغة الأولى
    # فكشفت ذلك: كان الجدولُ يحمل `evidence: {}` وحدَها، و`{}` **قاموسٌ** فلا
    # يبلغه فرعُ «ليست خريطة». فصفٌّ بلا الكتلة رأساً — وهو شكلُ بيانٍ أنتجه
    # مسارُ بناءٍ قديم — كان يمرّ بلا أن يُحمِّر شيئاً.
    absent = {"images": {"svc": {"image": sound["images"]["svc"]["image"]}}}
    assert guard.failures(absent), "صفٌّ بلا كتلةِ `evidence` رأساً مرّ"

    not_a_map = {"images": {"svc": {"image": sound["images"]["svc"]["image"], "evidence": []}}}
    assert guard.failures(not_a_map), "كتلةُ أدلّةٍ ليست خريطةً مرّت"

    malformed = {
        "images": {
            "svc": {
                "image": sound["images"]["svc"]["image"],
                "evidence": dict.fromkeys(REQUIRED_EVIDENCE, "z" * 64),
            }
        }
    }
    assert guard.failures(malformed), "**طولٌ ليس شكلاً** — أربعٌ وستّون محرفاً غيرَ ستّ عشريّة مرّت"

    tagged = {
        "images": {
            "svc": {
                "image": "ghcr.io/o/svc:latest",
                "evidence": dict.fromkeys(REQUIRED_EVIDENCE, good_digest),
            }
        }
    }
    assert guard.failures(tagged), "مرجعٌ بوسمٍ لا ببصمةٍ مرّ"

    assert guard.failures(sound, "d" * 40), "بيانٌ من لقطةٍ أخرى مرّ"
    assert guard.failures({"images": {}}), "بيانٌ بلا صورٍ مرّ — والخُضرةُ هنا «لم يُنظَر»"
