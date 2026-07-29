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
    for name in ["sahool-edge", "sahool-sam2-inference", "sahool-video-processor"]:
        assert "devices" in str(services[name].get("deploy", {}))
    assert env(services["sahool-edge"])["EDGE_DEVICE"] == "${EDGE_DEVICE:-rtx5090}"
    seg_env = env(services["sahool-field-segmentation"])
    assert seg_env["SEGMENTATION_BACKEND"] == "sam2"
    assert seg_env["SEGMENTATION_INFERENCE_URL"] == "http://sahool-sam2-inference:8080/predict"


def test_sam2_dockerfile_defaults_to_cuda_128_image():
    text = (ROOT / "services/sam2-inference/Dockerfile").read_text(encoding="utf-8")
    assert "PYTORCH_CUDA_IMAGE" in text
    assert "cuda12.8" in text


def test_edge_detector_accepts_rtx5090_cuda_device():
    text = (ROOT / "services/edge-inference/models/pest_detector.py").read_text(encoding="utf-8")
    assert "rtx5090" in text
    assert "CUDAExecutionProvider" in text


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
    import subprocess
    import sys

    p = subprocess.run(
        [sys.executable, "scripts/ci/v9_gpu_contract_gate.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "PASS" in p.stdout
