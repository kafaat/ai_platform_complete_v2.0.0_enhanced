import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def load(rel: str):
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def env(service):
    e = service.get("environment") or {}
    if isinstance(e, list):
        return dict(x.split("=", 1) for x in e if "=" in x)
    return e


def test_v9_has_zlmediakit_and_video_depends_on_it():
    d = load("docker-compose.v9.yml")
    services = d["services"]
    assert "sahool-zlmediakit" in services
    assert services["sahool-zlmediakit"].get("healthcheck")
    video = services["sahool-video-processor"]
    assert "sahool-zlmediakit" in (video.get("depends_on") or {})
    video_env = env(video)
    assert video_env["ZLMEDIA_API_URL"].startswith("http://sahool-zlmediakit")
    assert "ZLMEDIAKIT_API_SECRET" in video_env


def test_notification_agent_uses_real_tts_service():
    d = load("docker-compose.v9.yml")
    svc = d["services"]["sahool-notification-agent"]
    assert env(svc)["TTS_URL"] == "http://sahool-tts-service:8000"
    assert "sahool-tts-service" in (svc.get("depends_on") or {})


def test_gpu_overlay_enables_rtx5090_paths():
    d = load("docker-compose.v9.gpu.yml")
    services = d["services"]
    base = load("docker-compose.v9.yml")["services"]
    for name in ["sahool-sam2-inference", "sahool-vllm-jais"]:
        assert base[name]["deploy"]["resources"]["reservations"]["devices"] == [
            {"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}
        ]
        assert "devices" not in services[name].get("deploy", {}).get("resources", {}).get(
            "reservations", {}
        )
    assert env(services["sahool-edge"])["EDGE_DEVICE"] == "${EDGE_DEVICE:-rtx5090}"
    seg_env = env(services["sahool-field-segmentation"])
    assert seg_env["SEGMENTATION_BACKEND"] == "sam2"
    assert seg_env["SEGMENTATION_INFERENCE_URL"] == "http://sahool-sam2-inference:8080/v1/predict"


def test_video_processor_reserves_no_gpu_because_it_decodes_on_the_cpu():
    # video-processor: python:3.11-slim + PyPI opencv-python-headless (no CUDA/NVDEC); frames go to
    # sahool-edge over HTTP. A GPU reservation there only stopped the stack on GPU-less hosts.
    reqs = (ROOT / "services/video-processor/requirements.txt").read_text(encoding="utf-8")
    dockerfile = (ROOT / "services/video-processor/Dockerfile").read_text(encoding="utf-8")
    assert "opencv-python-headless" in reqs, "premise changed: re-check the GPU need"
    assert not re.search(r"torch|onnxruntime-gpu|cupy|nvidia|cuda", reqs, re.I), (
        "a GPU library appeared in video-processor; re-check the GPU reservation decision"
    )
    assert dockerfile.startswith("FROM python:3.11-slim"), "premise changed: not a CPU base image"
    overlay = load("docker-compose.v9.gpu.yml")["services"]["sahool-video-processor"]
    base = load("docker-compose.v9.yml")["services"]["sahool-video-processor"]
    for svc in (base, overlay):
        assert "devices" not in svc.get("deploy", {}).get("resources", {}).get(
            "reservations", {}
        ), "video-processor must not reserve a GPU"
    assert not {"NVIDIA_VISIBLE_DEVICES", "NVIDIA_DRIVER_CAPABILITIES"} & set(env(overlay)), (
        "no NVIDIA runtime env for a CPU-only service"
    )
    assert env(overlay)["VIDEO_STRICT_READY"] == "${VIDEO_STRICT_READY:-true}", overlay
    assert {"sahool-zlmediakit", "sahool-edge"} <= set(overlay["depends_on"]), overlay
    assert env(base)["EDGE_INFERENCE_URL"] == "http://sahool-edge:8100", "inference stays in edge"


def test_sam2_dockerfile_defaults_to_cuda_128_image():
    text = (ROOT / "services/sam2-inference/Dockerfile").read_text(encoding="utf-8")
    assert "PYTORCH_CUDA_IMAGE" in text
    assert "cuda12.8" in text


def test_edge_profile_selects_gpu_only_dependencies_and_inherits_device():
    edge = ROOT / "services/edge-inference"
    assert "EDGE_DEVICE=" in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    overlay = load("docker-compose.v9.gpu.yml")["services"]["sahool-edge"]
    gpu_reqs = edge / overlay["build"]["args"]["EDGE_REQUIREMENTS"]
    assert "onnxruntime-gpu[cuda,cudnn]==" in gpu_reqs.read_text(encoding="utf-8")
    assert "onnxruntime>=" in (edge / "requirements.txt").read_text(encoding="utf-8")
    assert "onnxruntime" not in (edge / "requirements-common.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("requirements", "target_arch", "native_arch", "allowed"),
    [
        ("requirements.txt", "arm64", "amd64", True),
        ("requirements.txt", "amd64", "arm64", True),
        ("requirements-gpu.txt", "amd64", "arm64", True),
        ("requirements-gpu.txt", "arm64", "amd64", False),
        ("requirements-gpu.txt", "arm", "amd64", False),
        ("./requirements-gpu.txt", "arm64", "amd64", False),
        ("requirements-gpu.txt", "", "amd64", True),
        ("requirements-gpu.txt", "", "arm64", False),
    ],
)
def test_edge_gpu_build_architecture_guard_executes_before_downloads(
    tmp_path, requirements, target_arch, native_arch, allowed
):
    """Run the Dockerfile's actual shell guard, not an equivalent Python predicate."""
    text = (ROOT / "services/edge-inference/Dockerfile.arm64").read_text(encoding="utf-8")
    guard = text.split("RUN ", 1)[1].split("\n\n", 1)[0].replace("\\\n", "")
    assert "EDGE_REQUIREMENTS" in guard and "TARGETARCH" in guard
    assert text.index(guard.splitlines()[0].split(";")[0]) < text.index("apt-get")
    dpkg = tmp_path / "dpkg"
    dpkg.write_text(f"#!/bin/sh\nprintf '%s\\n' '{native_arch}'\n", encoding="utf-8")
    dpkg.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", "-ec", guard],
        env={
            **os.environ,
            "PATH": str(tmp_path),
            "EDGE_REQUIREMENTS": requirements,
            "TARGETARCH": target_arch,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert (result.returncode == 0) is allowed, result.stderr
    if not allowed:
        assert "requires amd64" in result.stderr and "ARM64 CPU" in result.stderr


def test_sam2_readyz_exposes_actionable_reason():
    # صدق تشغيليّ: /readyz يُصنّف سبب عدم التحميل (weights_missing/…) + مسار الأوزان
    # المتوقّع، كي يعرف المُشغّل ما ينقص دون قراءة السجلّات (حالة «GPU جاهز بلا أوزان»).
    # تفكيك P2 نقل رموز الأسباب من main.py إلى sam2_runtime.py؛ القاعدة المحروسة
    # (/readyz يُصنّف سبب عدم التحميل) لم تتغيّر. نضمّ وحدات الخدمة بدل تسمية ملفّ.
    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((ROOT / "services/sam2-inference").glob("*.py"))
    )
    assert "reason_code" in text and "checkpoint_expected" in text
    for code in ("weights_missing", "cuda_unavailable", "library_missing", "load_failed"):
        assert code in text, f"reason_code مفقود: {code}"


def test_sam2_gpu_arch_list_targets_blackwell():
    # RTX 5090 = Blackwell sm_120 = arch "12.0"؛ صورة cuda12.8 تعمل مع سائق CUDA 13.x
    # (توافق خلفيّ للسائق). العتاد يُتحقَّق حيّاً عبر sam2_live_gpu_gate على الجهاز.
    gpu = load("docker-compose.v9.gpu.yml")
    sam2_env = env(gpu["services"]["sahool-sam2-inference"])
    assert "12.0" in sam2_env.get("TORCH_CUDA_ARCH_LIST", "")


def test_static_gpu_contract_gate_runs():
    import sys

    p = subprocess.run(
        [sys.executable, "scripts/ci/v9_gpu_contract_gate.py"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "PASS" in p.stdout


def test_sample_environment_preserves_sam2_build_and_predict_defaults():
    sample = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.startswith(("PYTORCH_CUDA_IMAGE=", "SEGMENTATION_INFERENCE_URL="))
    )
    dockerfile = (ROOT / "services/sam2-inference/Dockerfile").read_text(encoding="utf-8")
    image = next(
        line.split("=", 1)[1]
        for line in dockerfile.splitlines()
        if line.startswith("ARG PYTORCH_CUDA_IMAGE=")
    )
    overlay = load("docker-compose.v9.gpu.yml")["services"]["sahool-sam2-inference"]
    assert overlay["build"]["args"]["PYTORCH_CUDA_IMAGE"] == f"${{PYTORCH_CUDA_IMAGE:-{image}}}"
    assert sample["PYTORCH_CUDA_IMAGE"] == image
    service = load("docker-compose.v9.yml")["services"]["sahool-field-segmentation"]
    assert env(service)["SEGMENTATION_INFERENCE_URL"] == (
        "${SEGMENTATION_INFERENCE_URL:-" + sample["SEGMENTATION_INFERENCE_URL"] + "}"
    )


def _nvidia_reserving_services() -> set[str]:
    base = load("docker-compose.v9.yml")["services"]
    overlay = load("docker-compose.v9.gpu.yml")["services"]
    found = set()
    for name in set(base) | set(overlay):
        devices = None
        for layer in (base.get(name) or {}, overlay.get(name) or {}):
            layer_devices = (
                layer.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices")
            )
            if layer_devices is not None:
                devices = layer_devices
        if any(d.get("driver") == "nvidia" for d in devices or []):
            found.add(name)
    return found


def test_ci_gpu_reservation_step_matches_the_compose_files():
    # The compose-validate job checks effective reservations with jq; when a reservation moves in
    # the compose files that step must move with it (it was missed once for video-processor).
    workflow = load(".github/workflows/ci.yml")
    steps = workflow["jobs"]["compose-validate"]["steps"]
    run = next(
        (s["run"] for s in steps if s.get("name") == "Validate effective GPU reservations"), None
    )
    assert run, "compose-validate lost its 'Validate effective GPU reservations' step"
    listed = re.search(r'\[\.\[((?:"[^"]+",?\s*)+)\]', run)
    assert listed, f"could not find the jq service list in: {run}"
    names = re.findall(r'"([^"]+)"', listed.group(1))
    expected_counts = re.search(r"==\s*\[([\d,\s]+)\]", run)
    assert expected_counts, f"could not find the expected counts in: {run}"
    counts = [int(c) for c in expected_counts.group(1).split(",")]
    assert counts == [1] * len(names), f"one reservation per listed service: {names} vs {counts}"
    reserving = _nvidia_reserving_services()
    assert set(names) <= reserving, (
        f"CI jq list {sorted(names)} names services without an NVIDIA reservation "
        f"(reserving: {sorted(reserving)})"
    )
    assert "sahool-video-processor" not in names, "video-processor reserves no GPU"
    assert "sahool-video-processor" not in reserving, "video-processor must not reserve a GPU"
    assert '.["sahool-video-processor"]' in run and "length == 0" in run, (
        "CI must assert that video-processor carries no NVIDIA reservation"
    )


@pytest.mark.parametrize(
    ("requirements", "index", "failure", "expected_indexes", "succeeds"),
    [
        ("requirements-gpu.txt", "official", "", ["official"], True),
        ("./requirements-gpu.txt", "aliyun", "install", ["aliyun", "official"], True),
        ("requirements-gpu.txt", "aliyun", "bootstrap", ["official"], True),
        ("requirements-gpu.txt", "private", "install", ["private"], False),
        ("requirements-gpu.txt", "aliyun", "both_indexes", ["aliyun", "official"], False),
        ("requirements.txt", "private", "", ["private"], True),
    ],
)
def test_edge_dependency_install_resumes_gpu_downloads_and_respects_private_indexes(
    tmp_path, requirements, index, failure, expected_indexes, succeeds
):
    urls = {
        "official": "https://pypi.org/simple",
        "aliyun": "https://mirrors.aliyun.com/pypi/simple/",
        "private": "https://packages.example.test/simple",
    }
    dockerfile = (ROOT / "services/edge-inference/Dockerfile.arm64").read_text(encoding="utf-8")
    builder = dockerfile.split("ENV PYTHONUSERBASE=/opt/pylocal", 1)[1].replace("\\\n", "")
    install = next(
        line.removeprefix("RUN ") for line in builder.splitlines() if line.startswith("RUN ")
    )
    recorder = tmp_path / "python"
    recorder.write_text(
        "#!/bin/sh\n"
        'printf "%s|%s|%s|%s\\n" "$PIP_INDEX_URL" "$PIP_TRUSTED_HOST" '
        '"${PIP_RESUME_RETRIES:-}" "$*" >> calls\n'
        'case "$FAILURE:$*:$PIP_INDEX_URL" in\n'
        "  bootstrap:*pip==*:*/pypi/simple/) exit 1 ;;\n"
        '  install:*"--user "*|both_indexes:*"--user "*)\n'
        '    [ "$FAILURE" != both_indexes ] && [ "$PIP_INDEX_URL" = "$OFFICIAL" ] ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    recorder.chmod(0o755)
    # The pre-fix instruction calls the pip executable directly.
    (tmp_path / "pip").symlink_to(recorder)
    result = subprocess.run(
        ["/bin/sh", "-ec", install],
        cwd=tmp_path,
        env={
            "PATH": str(tmp_path),
            "EDGE_REQUIREMENTS": requirements,
            "PIP_INDEX_URL": urls[index],
            "PIP_TRUSTED_HOST": "mirror.example.test",
            "OFFICIAL": urls["official"],
            "FAILURE": failure,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert (result.returncode == 0) is succeeds, result.stderr
    lines = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    calls = [line.split("|", 3) for line in lines]
    installs = [call for call in calls if "--user " in call[3]]
    assert [call[0] for call in installs] == [urls[name] for name in expected_indexes]
    gpu = requirements.endswith("requirements-gpu.txt")
    if gpu:
        assert "pip==26.3" in calls[0][3]
    else:
        assert len(calls) == 1
    for url, trusted, resumes, args in installs:
        assert trusted == ("" if url != urls[index] else "mirror.example.test")
        assert args.endswith(f"--user -r {requirements}")
        assert resumes == ("10" if gpu else "")
