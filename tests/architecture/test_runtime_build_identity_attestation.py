from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def test_identity_reader_ignores_mutable_environment(tmp_path, monkeypatch):
    m = load_module(ROOT / "shared/runtime_identity.py", "runtime_identity_test")
    p = tmp_path / "meta.json"
    p.write_text(
        json.dumps(
            {
                "service": "weather-service",
                "git_sha": "a" * 40,
                "build_id": "build-1",
                "source_repository": "org/repo",
                "source_ref": "refs/heads/main",
            }
        )
    )
    monkeypatch.setenv("SAHOOL_GIT_SHA", "b" * 40)
    monkeypatch.setenv("SAHOOL_BUILD_ID", "spoofed")
    got = m.load_build_identity("weather-service", p)
    assert got["git_sha"] == "a" * 40 and got["build_id"] == "build-1"
    assert got["metadata_source"] == "immutable-image-file"


def test_identity_reader_rejects_bad_metadata(tmp_path):
    m = load_module(ROOT / "shared/runtime_identity.py", "runtime_identity_bad_test")
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({"service": "weather-service", "git_sha": "bad", "build_id": "x"}))
    with pytest.raises(m.BuildIdentityError):
        m.load_build_identity("weather-service", p)


def test_service_endpoints_do_not_read_identity_from_environment():
    # weather/soil declare the endpoint directly on their app; sahool-platform declares it
    # on the platform_health router (api/main.py must stay route-free per the P1
    # decomposition guard). Either decorator form is accepted — what matters is that the
    # identity comes from the read-only build metadata, never from mutable env.
    for rel, dec in [
        ("services/weather-service/main.py", '@app.get("/runtime-identity"'),
        ("services/soil-service/main.py", '@app.get("/runtime-identity"'),
        ("services/raster-service/main.py", '@app.get("/runtime-identity"'),
        (
            "services/sahool-platform/api/routers/platform_health.py",
            '@router.get("/runtime-identity"',
        ),
    ]:
        text = (ROOT / rel).read_text()
        block = text[text.index(dec) :]
        block = block[: block.find("\n\n", 1)]
        assert "os.getenv" not in block
        assert "load_build_identity" in block
    assert "/runtime-identity" not in (ROOT / "services/sahool-platform/api/main.py").read_text()


def test_dockerfiles_embed_immutable_metadata_and_oci_labels():
    for rel in [
        "services/weather-service/Dockerfile",
        "services/soil-service/Dockerfile",
        "services/raster-service/Dockerfile",
        "services/sahool-platform/Dockerfile",
    ]:
        text = (ROOT / rel).read_text()
        assert "ARG SAHOOL_GIT_SHA" in text
        assert "org.opencontainers.image.revision" in text
        assert "/app/.sahool-build-metadata.json" in text
        assert "chmod 0444" in text


def _identity_baking_dockerfiles() -> set[str]:
    """مسارات كلّ Dockerfile يخبز `.sahool-build-metadata.json` — فيفرض وسائط الهويّة fail-closed.

    يُشتقّ من محتوى الـDockerfiles لا من قائمة مُصلَّبة — القائمة المثبَّتة هي تحديداً
    كيف أفلت عاملا raster (`cache-invalidation` و`backfill-scan`): يبنيان **نفس**
    Dockerfile الذي صار يفرض الهويّة، وكتلتاهما في compose بلا وسائط، فانكسر البناء
    على الجهاز الحيّ بـ`SAHOOL_GIT_SHA must be full 40-char SHA` رغم خضرة كلّ الحرّاس.
    يُعاد **مجموعة مسارات** فقط: العضويّة هي المطلوبة، وإخراج محتوى Dockerfiles كاملةً
    في رسالة فشل يجعلها غير مقروءة.
    """
    found: set[str] = set()
    for dockerfile in (ROOT / "services").rglob("Dockerfile"):
        if ".sahool-build-metadata.json" in dockerfile.read_text(encoding="utf-8", errors="ignore"):
            found.add(dockerfile.relative_to(ROOT).as_posix())
    return found


def test_compose_requires_build_identity_args():
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text())
    dockerfiles = _identity_baking_dockerfiles()
    assert dockerfiles, "لا Dockerfile يخبز الهويّة؟ الاشتقاق عمي"
    # كلّ خدمة تبني Dockerfile يخبز الهويّة — خدمةً كانت أو عاملاً يشاركها الصورة —
    # يجب أن تمرّر الوسائط، وإلّا انكسر بناؤها fail-closed كما انكسر backfill-scan.
    offenders: list[str] = []
    checked = 0
    for name, service in compose["services"].items():
        build = service.get("build") or {}
        dockerfile = build.get("dockerfile")
        if dockerfile not in dockerfiles:
            continue
        checked += 1
        args = build.get("args") or {}
        if "TESTED_SHA required" not in str(args.get("SAHOOL_GIT_SHA", "")) or (
            "SAHOOL_BUILD_ID required" not in str(args.get("SAHOOL_BUILD_ID", ""))
        ):
            offenders.append(name)
    assert checked >= len(dockerfiles), f"بعض الـDockerfiles بلا خدمة تبنيها: {sorted(dockerfiles)}"
    assert not offenders, f"خدمات تبني Dockerfile يفرض الهويّة بلا وسائطها: {offenders}"


def test_build_provenance_args_use_one_convention():
    """**اصطلاحان لشيء واحد يُنتِجان نَسَباً فارغاً في نصف الصور.**

    الخدمات الأولى تقرأ `${GITHUB_REPOSITORY}`/`${GITHUB_REF}` — وActions تضبطهما
    تلقائيّاً، فتصل القيَم إلى وسم OCI وإلى ملفّ الهويّة. ثمّ أُضيفت خمس كتل تقرأ
    `${SAHOOL_SOURCE_REPOSITORY:-}` و`${SAHOOL_SOURCE_REF:-}` — ولا يضبطهما شيء في
    الخطّ، فالافتراضيّ الفارغ يمرّ صامتاً.

    والعطل **لا يُحمِّر بناءً**: الصورة تُبنى وتُوثَّق، وحقلا `source_repository`
    و`source_ref` فيها فارغان — أي نَسَبٌ ناقص يُقرأ نَسَباً. أمسكه
    `compose_env_contract_gate` بالمصادفة (المتغيّران غير مُعلَنين في أمثلة البيئة)،
    لا لأنّ أحداً كان يقيس الاتّساق. هذا الفحص يقيسه.
    """
    compose = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))
    sources: set[str] = set()
    for name, service in compose["services"].items():
        args = (service.get("build") or {}).get("args") or {}
        if "SAHOOL_GIT_SHA" not in args:
            continue
        for key in ("SAHOOL_SOURCE_REPOSITORY", "SAHOOL_SOURCE_REF"):
            assert key in args, f"{name}: كتلة هويّة بلا {key}"
            sources.add(str(args[key]).split(":-", 1)[0].lstrip("${"))

    assert sources == {"GITHUB_REPOSITORY", "GITHUB_REF"}, (
        "اصطلاحان لنَسَب البناء في نفس الملفّ: " + " · ".join(sorted(sources))
    )


def _services_exposing_runtime_identity() -> set[str]:
    """يُشتقّ من الشجرة لا من قائمة مصونة يدويّاً.

    قائمةٌ مكتوبة بيد تبقى صحيحة حتّى تُضاف الخدمة الخامسة وينساها كاتبها — وهو
    بالضبط كيف بقيت `raster-service` بهويّة موصولة **جزئيّاً**: الصورة والنقطة
    قائمتان، والصورة الموثَّقة والمِسبار غائبان، ولا شيء يُبلِّغ عن الفارق.

    الاسم يُؤخَذ من وسيط `load_build_identity("…")` لأنّه **هو** الاسم الذي تتحقّق
    منه الخدمة مقابل ملفّ الصورة (`service mismatch`)، فلا مجال لاسمين.
    """
    pattern = re.compile(r'load_build_identity\(\s*"([a-z0-9-]+)"')
    found: set[str] = set()
    for path in (ROOT / "services").rglob("*.py"):
        if "/tests/" in path.as_posix() or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "/runtime-identity" not in text:
            continue
        found.update(pattern.findall(text))
    return found


def test_every_identity_service_is_attested_and_probed():
    """**الفجوة كانت «موصولة جزئيّاً»، وهذا يمنع الجزئيّة لا الحالة الواحدة.**

    نقطة `/runtime-identity` وحدها لا تُثبِت شيئاً عن النشر: صورةٌ مبنيّة محلّيّاً
    تحمل SHA صحيحاً وتبقى **غير موثَّقة**. الربط الذي يقصده `TESTED_SHA` هو
    attestation على digest، وينتجه `runtime-image-provenance.yml` وحده؛ وفحصُه على
    البيئة الحيّة يمرّ من خطّة المِسبار (`identity_path`). فخدمةٌ تُعلن الهويّة
    وتغيب عن أيّ منهما تُنتج ثقةً لا سند لها.
    """
    services = _services_exposing_runtime_identity()
    assert len(services) >= 4, f"الاشتقاق عاد بأقلّ ممّا في الشجرة: {sorted(services)}"

    matrix = (ROOT / ".github/workflows/runtime-image-provenance.yml").read_text(encoding="utf-8")
    attested = set(re.findall(r"^\s*-\s*service:\s*([a-z0-9-]+)\s*$", matrix, re.M))
    missing_attestation = sorted(services - attested)
    assert not missing_attestation, (
        "خدمات تُعلن /runtime-identity ولا تُبنى لها صورة موثَّقة: " + " · ".join(missing_attestation)
    )

    # **والمصفوفة وحدها لا تكفي — انكشف بالقياس أثناء وصل raster.** وظيفة
    # `publish-manifest` تحمل مجموعة خدمات **مثبَّتة نصّاً** وتُفشِل التجميع إن
    # اختلفت عمّا وصل من شظايا. فصفٌّ يُضاف إلى المصفوفة بلا تحديثها يُنتج بناءً
    # ناجحاً وتوثيقاً ناجحاً ثمّ انهياراً في آخر خطوة — أي الجزئيّة نفسها، طبقةً أعمق.
    expected = re.search(r"expected\s*=\s*\{([^}]*)\}", matrix)
    assert expected, "لم يعد `publish-manifest` يُعلن مجموعة متوقَّعة — الحارس أعمى"
    declared = set(re.findall(r"'([a-z0-9-]+)'", expected.group(1)))
    assert declared == attested, (
        "مصفوفة البناء ومجموعة `publish-manifest` المتوقَّعة غير متطابقتين: "
        f"المصفوفة={sorted(attested)} · المتوقَّع={sorted(declared)}"
    )

    probe_dir = ROOT / "runtime-verification/functional_probes"
    for service in sorted(services):
        plan_path = probe_dir / f"{service}.json"
        assert plan_path.is_file(), f"لا خطّة مِسبار لـ{service} — الهويّة لا تُفحَص حيّاً"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        assert plan.get("identity_path") == "/runtime-identity", (
            f"{service}: خطّة المِسبار لا تُعلن identity_path"
        )


def test_path3_produces_transports_and_verifies_oidc_provenance():
    text = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert (
        "functional-runtime-verifier"
        in (ROOT / "scripts/ci/path3_runtime_activation.py").read_text()
    )
    assert (
        "functional_probe_runner.py"
        in (ROOT / "docker-compose.runtime-verification.yml").read_text()
    )
    # البصمة مثبَّتة عمداً: وسمٌ متحرّك (`@v4`) يسمح باستبدال **المُوقِّع** من تحت
    # الخطّ بلا تغيير سطر واحد هنا. فالتأكيد يتحرّك **مع** الترقية في نفس الالتزام،
    # ولا يُرخّى إلى `actions/attest@` مجرّداً — إرخاؤه يُبقي الاختبار أخضر ويُلغي
    # الخاصّيّة التي وُجِد لها.
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in text
    assert "gh attestation verify" in text
    assert "--signer-workflow" in text and "--source-digest" in text and "--source-ref" in text
    assert "verify-and-evaluate:" in text


def test_image_digest_and_run_formats_are_strict():
    text = (ROOT / "scripts/ci/runtime_identity_bridge.py").read_text()
    assert "^sha256:[0-9a-f]{64}$" in text
    assert "invalid_build_id" in text and "invalid_run_id" in text


def test_path3_uses_external_attested_images_and_protected_boundaries():
    text = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert "image_build_run_id" in text
    assert (
        "runtime-image-provenance.yml"
        in (ROOT / ".github/workflows/runtime-image-provenance.yml").read_text()
    )
    assert "runs-on: [self-hosted, linux, docker, sahool-path3-trusted]" in text
    assert "environment: staging-pg16" in text
    producer = text.split("runtime-producer:", 1)[1].split("trusted-signer:", 1)[0]
    assert "id-token: write" not in producer and "attestations: write" not in producer
    signer = text.split("trusted-signer:", 1)[1].split("verify-and-evaluate:", 1)[0]
    assert "runs-on: ubuntu-24.04" in signer
    assert "Attest evidence bundle in trusted signer boundary" in signer
    assert (
        "docker compose -f docker-compose.v9.yml -f verified-images/docker-compose.attested-images.yml pull"
        in text
    )
    assert 'gh attestation verify "oci://${image}"' in text


def test_bridge_requires_external_provenance_receipt_and_replay_guard():
    bridge = (ROOT / "scripts/ci/runtime_identity_bridge.py").read_text()
    workflow = (ROOT / ".github/workflows/path3-runtime-verification.yml").read_text()
    assert "external_provenance_receipt_required" in bridge
    assert "--provenance-receipt" in bridge
    assert "runtime_replay_guard.py" in workflow
    assert "path3-consumed-${{ env.BUNDLE_SHA256 }}" in workflow


def test_deployment_manifest_prefers_attested_registry_digest():
    text = (ROOT / "scripts/ci/runtime_deployment_manifest.py").read_text()
    assert "RepoDigests" in text
    assert "running image does not match attested pull-by-digest reference" in text
    assert '"docker_config_digest": image_id' in text


def test_every_attest_pin_anchor_agrees():
    """**بصمةُ المُوقِّع مثبَّتةٌ في أكثر من مرساة — فيُقاس اتّفاقُها لا وجودُها.**

    العطل وقع فعلاً: ترقيةُ `actions/attest` من `v4.2.1` إلى `v4.2.2` حرّكت ثمانية
    مواضع في خمسة workflows، وتركت مرساتين خلفها — `release_attestation_guard.py`
    والتوكيد أعلاه. ومرّت على `preflight --fast` وعلى بوّابة سياسة الأكشنز، لأنّ
    كلتيهما تسأل «هل التثبيت بـSHA؟» لا «هل كلّ المراسي تشير إلى **الواحد** نفسه؟».

    **والضرر ليس أحمرَ متأخّراً وحده:** حارسُ الإصدار يعدّ سطور `uses:` ببصمةٍ
    بعينها، فترقيةٌ نصفُ مُطبَّقة تجعله يقرأ «صفر مُصدِّق» على workflow يُصدِّق
    مرّتين — نتيجةٌ صحيحة عن سؤالٍ لم يعد مطروحاً.

    فالمقيس هنا **الاتّساق**: بصمةٌ واحدة عبر كلّ مرساة. ولا يُرخّى إلى `actions/attest@`
    مجرّداً — إرخاؤه يُبقي الاختبار أخضر ويُلغي الخاصّيّة التي وُجِد لها.
    """
    import re

    pin = re.compile(r"actions/attest@([0-9a-f]{40})")

    anchors: dict[str, set[str]] = {}
    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/path3-runtime-verification.yml",
        ".github/workflows/release-artifact-attestation.yml",
        ".github/workflows/runtime-image-provenance.yml",
        ".github/workflows/runtime-verification-promotion.yml",
        "scripts/ci/release_attestation_guard.py",
        "tests/architecture/test_runtime_build_identity_attestation.py",
    ):
        found = set(pin.findall((ROOT / relative).read_text(encoding="utf-8")))
        assert found, (
            f"{relative}: لا بصمة `actions/attest@<sha40>` — إمّا نُقِل الاستعمال "
            "وبقيت المرساة في القائمة، وإمّا أُرخي التثبيت إلى وسمٍ متحرّك. كلاهما "
            "يُبطِل القياس بدل أن يُظهِره."
        )
        anchors[relative] = found

    distinct = set().union(*anchors.values())
    assert len(distinct) == 1, (
        "بصماتٌ متعدّدة لـ`actions/attest` عبر المراسي ⇒ ترقيةٌ نصفُ مُطبَّقة:\n"
        + "\n".join(f"  {path}: {sorted(shas)}" for path, shas in sorted(anchors.items()))
    )
