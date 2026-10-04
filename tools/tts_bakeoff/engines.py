"""محوّلات المحرّكات — كلٌّ يُحمَّل مرّةً من مساراتٍ محلّيّة صريحة، ويُرجِع بايتاتِ WAV.

الفحصُ (``audio.validate_wav``) والقياسُ في ``worker.py``؛ المحوّلُ لا يحكم على مخرجه.
كلُّ مسارٍ في ``settings`` يجب أن يقع تحت ملفٍّ أو مجلّدٍ مُعلنٍ ببصمته في البيان
(``worker.verify_manifest``)، فلا يُحمَّل شيءٌ لم يُثبَّت.
"""

from __future__ import annotations

import io
import math
import os
import struct
import threading
import time
import wave


def _require_version(dist: str, target: str) -> str:
    import importlib.metadata

    installed = importlib.metadata.version(dist)
    if installed != target:
        raise RuntimeError(f"{dist} {installed} ≠ الإصدار المثبّت {target}")
    return installed


class FakeEngine:
    """محرّكٌ اصطناعيّ لفحص الأداة وحدها — **لا يُقارَن**. أنماطُه تحقن الأعطال المعروفة:

    ``ok`` نغمة · ``header_only`` ترويسةٌ بلا عيّنات · ``silent`` صمت · ``truncated`` ترويسةٌ تكذب
    · ``fail_concurrent`` يفشل خارج الخيط الرئيسيّ · ``hang`` يتوقّف · ``net_on_load`` يتّصل عند التحميل
    (يمسكه حارسُ بايثون) · ``net_native_on_load`` عمليّةُ curl أصليّة (لا يراها إلّا عزلُ النظام).
    """

    name = "fake"
    version = "selftest"

    def __init__(self, cfg: dict) -> None:
        self.mode = cfg.get("mode", "ok")
        self.rate = 16000
        if self.mode == "tamper":
            # يحاول تعديلَ نموذجٍ مُثبَّت بعد التثبيت — يجب أن يرفضه التركيبُ للقراءة فقط.
            with open(cfg["model"], "ab") as fh:
                fh.write(b"tampered")
        if self.mode == "hang_with_child":
            import subprocess

            from procs import starttime

            self.child_pid = subprocess.Popen(["sleep", "100000"]).pid  # ابنٌ يجب أن يُقتل مع العامل
            self.child_start = starttime(self.child_pid)  # هويّتُه، أو None إن لم يكن /proc لفضائنا
        if self.mode == "reads_undeclared":
            with open(cfg["undeclared_path"], "rb") as fh:  # اعتمادٌ خارج الملفّات المُثبَّتة
                fh.read()
        if self.mode == "alloc":
            # يحجز ذاكرةً فعليّة (يلمس الصفحات) لإثبات أنّ حدّ cgroup يقتل لا يُسجَّل فقط.
            self._ballast = bytearray(int(cfg.get("alloc_mb", 512)) * 2**20)
            for i in range(0, len(self._ballast), 4096):
                self._ballast[i] = 1
        if self.mode == "net_on_load":
            import socket

            socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        if self.mode == "net_native_on_load":
            # عمليّةٌ أصليّة لا يراها حارسُ بايثون: إن وصلت فالعزلُ مثقوب ⇒ فشلُ التحميل باسمه.
            import subprocess

            host = os.environ.get("BAKEOFF_CONTROL_HOST", "pypi.org")
            probe = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--noproxy",
                    "*",
                    "-o",
                    "/dev/null",
                    "--max-time",
                    "5",
                    f"https://{host}/",
                ],
                capture_output=True,
                text=True,
            )
            if probe.returncode == 0:
                raise RuntimeError(f"native process REACHED the network (curl → {host})")
            self.native_probe = f"curl rc={probe.returncode}: {probe.stderr.strip()[:80]}"

    def _tone(self, seconds: float, amplitude: int = 8000) -> bytes:
        n = int(self.rate * seconds)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(
                b"".join(struct.pack("<h", int(amplitude * math.sin(i / 8))) for i in range(n))
            )
        return buf.getvalue()

    _inflight = 0
    _lock = threading.Lock()

    def synthesize(self, text: str) -> bytes:
        cls = type(self)
        with cls._lock:
            cls._inflight += 1
            parallel = cls._inflight > 1
        try:
            return self._synthesize(text, parallel)
        finally:
            with cls._lock:
                cls._inflight -= 1

    def _synthesize(self, text: str, parallel: bool) -> bytes:
        if self.mode == "fail_when_parallel" and parallel:
            raise RuntimeError("injected failure only under parallel load")
        if self.mode == "hang_when_parallel" and parallel:
            time.sleep(10**6)
        if self.mode == "sleep":
            time.sleep(0.3)
        if self.mode == "slow_when_parallel" and parallel:
            time.sleep(0.35)  # يكتمل بين جولتَي مراقبة (كلّ 0.2ث) لكن بعد مهلةٍ قدرها 0.25ث
        if self.mode in ("hang_with_child",):
            time.sleep(10**6)
        if self.mode == "busy":
            end = time.perf_counter() + 0.25
            while time.perf_counter() < end:  # حِملُ معالجٍ حقيقيّ لقياس التباطؤ بالحصّة
                pass
        if self.mode == "hang":
            time.sleep(10**6)
        if (
            self.mode == "fail_concurrent"
            and threading.current_thread() is not threading.main_thread()
        ):
            raise RuntimeError("injected concurrency failure")
        if self.mode == "header_only":
            return self._tone(0)
        if self.mode == "silent":
            return self._tone(0.08 * len(text), amplitude=0)
        data = self._tone(0.08 * len(text))
        if self.mode == "truncated":
            return data[: 44 + (len(data) - 44) // 3]
        return data


class PiperEngine:
    """Piper عبر ``synthesize_wav`` — piper-tts 1.8.0 مفروض، والنموذج وإعداده مساران صريحان."""

    name = "piper"
    DIST, TARGET = "piper-tts", "1.8.0"

    def __init__(self, cfg: dict) -> None:
        self.version = _require_version(self.DIST, self.TARGET)
        import onnxruntime
        from piper import PiperVoice

        self.voice = PiperVoice.load(cfg["model"], config_path=cfg["config"])
        # ``PiperVoice.load`` (1.8.0، voice.py 193-196) يبني الجلسة بـ``SessionOptions()`` افتراضيّة: خيوطٌ
        # بعدد الأنوية وspinning مفعّل، ولا تقرأ متغيّرات البيئة. لذا تُعاد الجلسة بخياراتٍ صريحة مُسجَّلة.
        opts = onnxruntime.SessionOptions()
        opts.intra_op_num_threads = int(cfg.get("ort_intra_threads", 1))
        opts.inter_op_num_threads = 1
        opts.add_session_config_entry(
            "session.intra_op.allow_spinning", "1" if cfg.get("ort_spinning") else "0"
        )
        self.voice.session = onnxruntime.InferenceSession(
            cfg["model"], sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.ort = {
            "intra_op_num_threads": opts.intra_op_num_threads,
            "allow_spinning": bool(cfg.get("ort_spinning")),
            "note": "التشكيلُ العربيّ (piper/tashkeel/model.onnx) جلسةٌ منفصلة بخياراتٍ افتراضيّة",
        }
        # التشكيلُ العربيّ مفعّلٌ افتراضاً (use_tashkeel=True) ويُنشأ عند **أوّل** جملةٍ عربيّة من ملفّاتٍ
        # داخل الحزمة — يُحمَّل هنا مسبقاً كي لا يدخل زمنَ «الطلب البارد» ولا يُفاجئ العزل.
        if (
            self.voice.config.espeak_voice == "ar"
            and self.voice.use_tashkeel
            and self.voice.tashkeel_diacritizier is None
        ):
            from piper.tashkeel import TashkeelDiacritizer

            self.voice.tashkeel_diacritizier = TashkeelDiacritizer()

    def synthesize(self, text: str) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            self.voice.synthesize_wav(text, w)
        return buf.getvalue()


class SilmaEngine:
    """SILMA TTS v1 بمساراتٍ محلّيّة صريحة — **لا** عبر ``SilmaTTS()``.

    ``SilmaTTS.__init__`` (silma-tts 1.0.5، ``api.py`` 89-94) يتجاهل ``ckpt_file``/``vocab_file``
    ويطلب ``hf://silma-ai/silma-tts`` دائماً. لذا يُعاد هنا بناءُ ما يفعله بنفس دوالّه الداخليّة
    لكن بمساراتٍ صريحة: ``load_model(ckpt, vocab)``، ``load_vocoder(is_local=True)``، ونموذج التشكيل
    ``CATTEncoderOnly(encoder_path, decoder_path)`` يُحقن في ``utils_infer.tashkeel_model`` قبل أن
    يُستدعى ``load_tashkeel_model`` (الذي يُنزِّل من GitHub Releases عند غيابه).

    **غيرُ مُجرَّب على الأوزان الحقيقيّة بعد** (Hugging Face محجوب في بيئة الإعداد). التوافقُ مع
    هذه الدوالّ الداخليّة مقيسٌ على مصدر 1.0.5 فقط، ولذلك الإصدارُ مفروض.
    """

    name = "silma"
    DIST, TARGET = "silma-tts", "1.0.5"

    def __init__(self, cfg: dict) -> None:
        self.version = _require_version(self.DIST, self.TARGET)
        for key in (
            "ckpt_file",
            "vocab_file",
            "vocoder_dir",
            "tashkeel_encoder",
            "tashkeel_decoder",
            "ref_audio",
            "ref_text",
        ):
            if not cfg.get(key):
                raise ValueError(f"silma: {key} مطلوب (لا مسارَ ضمنيّ)")
        from importlib.resources import files

        from catt_tashkeel import CATTEncoderOnly
        from hydra.utils import get_class
        from omegaconf import OmegaConf
        from silma_tts.infer import utils_infer as ui

        ui.tashkeel_model = CATTEncoderOnly(
            encoder_path=cfg["tashkeel_encoder"], decoder_path=cfg["tashkeel_decoder"]
        )
        model_cfg = OmegaConf.load(str(files("silma_tts").joinpath("config.yaml")))
        model_cls = get_class(f"silma_tts.model.{model_cfg.model.backbone}")
        self.mel_spec_type = model_cfg.model.mel_spec.mel_spec_type
        self.device = cfg.get("device", "cpu")
        self.enable_normalizer = bool(cfg.get("enable_normalizer", True))
        if self.enable_normalizer:
            ui.load_nemo_text_normalizer("عربي")
        self.vocoder = ui.load_vocoder(
            self.mel_spec_type, True, cfg["vocoder_dir"], self.device, None
        )
        self.model = ui.load_model(
            model_cls,
            model_cfg.model.arch,
            cfg["ckpt_file"],
            self.mel_spec_type,
            cfg["vocab_file"],
            "euler",
            False,
            self.device,
        )
        self.ui = ui
        self.ref_audio, self.ref_text = cfg["ref_audio"], cfg["ref_text"]
        self.speed = float(cfg.get("speed", 1.0))
        self.seed = int(cfg.get("seed", 1234))
        self.nfe_step = int(cfg.get("nfe_step", 16))  # افتراضُ ``SilmaTTS.infer``؛ RTF يتبعه مباشرة
        self._lock = threading.Lock()  # seed_everything عامّ للعمليّة: لا تداخل بين الطلبات

    def synthesize(self, text: str) -> bytes:
        import soundfile as sf
        from silma_tts.model.utils import seed_everything

        ui = self.ui
        with self._lock:
            seed_everything(self.seed)
            ref_file, ref_text = ui.preprocess_ref_audio_text(
                self.ref_audio, self.ref_text, show_info=lambda *a, **k: None
            )
            gen = ui.normalize_text(text) if self.enable_normalizer else text
            wav, sr, _ = ui.infer_process(
                ref_file,
                ref_text,
                gen,
                self.model,
                self.vocoder,
                self.mel_spec_type,
                show_info=lambda *a, **k: None,
                nfe_step=self.nfe_step,
                speed=self.speed,
                device=self.device,
                force_tashkeel=True,
            )
        buf = io.BytesIO()
        sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()


ENGINES = {cls.name: cls for cls in (FakeEngine, PiperEngine, SilmaEngine)}
#: إعداداتٌ تحمل مساراتٍ يجب أن تغطّيها البصمات.
PATH_SETTINGS = {
    "piper": ("model", "config"),
    "silma": (
        "ckpt_file",
        "vocab_file",
        "vocoder_dir",
        "tashkeel_encoder",
        "tashkeel_decoder",
        "ref_audio",
    ),
    "fake": ("model",),  # اختياريّ للمحرّك الاصطناعيّ: يُفحص إن وُجد
}
