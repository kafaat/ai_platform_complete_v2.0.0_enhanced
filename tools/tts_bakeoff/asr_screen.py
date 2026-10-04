"""فرزٌ آليّ **مساعد** بتعرّفٍ محلّيّ على الكلام (ASR) — لا يحكم، يرفع أعلاماً للمراجع البشريّ.

    python3 asr_screen.py runs/<تشغيل> --asr-config asr.json --out asr-001

لكلّ مقطعٍ مُسجَّلٍ في result.json (بعد مطابقة بصمته) يُفرَّغ الصوت محلّيّاً، ثمّ يُمرَّر التفريغ على
``semantic.check`` بحقائق الجملة. الناتج ``asr_screen.json`` يحفظ **لكلّ مقطع** إعدادَ المقيِّم كاملاً:
اسمه وإصداره وبصمةُ أوزانه وملفِّه التنفيذيّ ومعاملاتُ الفكّ واللغة والمفسِّر، والاستدعاءَ الفعليّ — فتُعاد القراءة أو يُعرف لماذا اختلفت.

ما **لا** يفعله، عمداً:
  • لا يدخل الحكم: ``score.py`` و``blind.py`` لا يقرآنه. علَمٌ = «استمع بعناية هنا»، وغيابُ العلم (``NO_FLAG_ON_DECLARED_CHECKS``) لا يعني
    سلامة — ASR قد «يُصحّح» خطأ المحرّك من سياق اللغة، أو يُخطئ هو في صوتٍ سليم.
  • لا يُمرَّر النصُّ المرجعيّ للمقيِّم: المقيِّم الذي يُعطى الجواب يردّده.
  • لا يُنزّل نموذجاً: ``model_path`` و``binary`` محلّيّان يُبصمان قبل الفرز وبعده. ومسبارُ الشبكة يُسجَّل
    كما هو (``proves_isolation: false``) — العزلُ يُثبت بـrun.py لا هنا.

التشغيل: **كلا المحوّلين في عمليّةٍ مستقلّة** بجلسةٍ ومجموعةٍ خاصّة؛ ``timeout_s`` لكلّ مقطع و``load_timeout_s``
للتحميل تُفرضان بقتل المجموعة كلّها (``EVALUATOR_TIMEOUT``). والمحتوى غيرُ المغطّى يُسجَّل (``uncovered_content``)
ويحمل حالةً تستدعي المراجعة (``REVIEW_UNCOVERED_CONTENT``) — لا يختفي تحت «بلا علَم».

المحوّلان (لا أمرٌ حرّ — v5 كان يقبل ``command`` حرّاً فمرّ فيه ``--initial-prompt`` بنصٍّ مرجعيّ):
  • ``whisper_cpp``: الأداةُ تبني سطرَ الأمر بنفسها من ``binary`` و``model_path`` واللغة والمعاملات
    المسموحة؛ لا يُقبل وسيطٌ إضافيّ.
  • ``faster_whisper``: الحزمة إن وُجدت، من مجلّدٍ محلّيّ فقط، بمعاملاتٍ مسموحة.
المعاملاتُ **قائمةٌ بيضاء بأنواعٍ ومدىً** (أعدادٌ وخياراتٌ مغلقة، لا نصوص حرّة)، فلا مدخلَ لنصٍّ مرجعيّ.
ويُسجَّل لكلّ مقطع **الاستدعاءُ الفعليّ** (argv أو kwargs)، و``reference_text_in_invocation`` **مقيسٌ**
عليه — لا قيمةٌ ثابتة.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import procs
import semantic
from semantic import HERE

CONFIG_KEYS = {
    "name",
    "version",
    "adapter",
    "model_path",
    "language",
    "params",
    "binary",
    "timeout_s",
    "load_timeout_s",
    "python",
    "isolate_net",
}
# لغةُ كلّ محوّلٍ كما يحملها نموذجُه فعلاً: PocketSphinx المضمَّن إنجليزيٌّ فقط — لا يُدّعى له عربيّة
LANGUAGES = {"whisper_cpp": {"ar"}, "faster_whisper": {"ar"}, "pocketsphinx": {"en"}}
# PocketSphinx: النموذجُ يُعطى بأجزائه الثلاثة صراحةً — بلا ذلك يستعمل Decoder() نموذجَه المضمَّن بصمت،
# فلا تطابق البصمةُ المسجَّلة ما فُكّ به فعلاً.
POCKETSPHINX_PARTS = {"hmm": "en-us", "lm": "en-us.lm.bin", "dict": "cmudict-en-us.dict"}
# (النوع، الأدنى، الأعلى) أو مجموعةُ خياراتٍ مغلقة
ALLOWED = {
    "whisper_cpp": {
        "beam_size": (int, 1, 16),
        "best_of": (int, 1, 16),
        "temperature": (float, 0.0, 1.0),
        "threads": (int, 1, 64),
    },
    "faster_whisper": {
        "beam_size": (int, 1, 16),
        "temperature": (float, 0.0, 1.0),
        "cpu_threads": (int, 1, 64),
        "compute_type": {"int8", "int8_float32", "float32"},
    },
    "pocketsphinx": {},  # لا معاملات: إعداداتُ الفكّ الافتراضيّة، والنموذجُ بأجزائه الصريحة
}
WHISPER_CPP_FLAGS = {"beam_size": "-bs", "best_of": "-bo", "temperature": "-tp", "threads": "-t"}
CONTROL_HOST = os.environ.get("BAKEOFF_CONTROL_HOST", "pypi.org")
# المحتوى غيرُ المغطّى **لا يُخفى** تحت «بلا علَم»: له حالةٌ تستدعي المراجعة
SCREENS = (
    "NO_FLAG_ON_DECLARED_CHECKS",
    "REVIEW_UNCOVERED_CONTENT",
    "FLAGGED",
    "EVALUATOR_FAILED",
    "EVALUATOR_TIMEOUT",
)


def _sha_path(path: Path) -> str:
    """بصمةُ ملفٍّ، أو بصمةٌ مركّبة لمجلّد (المسار النسبيّ + بصمةُ كلّ ملفّ، مرتّبة)."""
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(f"{f.relative_to(path)}\0{hashlib.sha256(f.read_bytes()).hexdigest()}\n".encode())
    return h.hexdigest()


def _network_probe() -> dict:
    """مسبارُ اتّصالٍ واحد يُسجَّل كما هو — **ليس إثباتَ عزل**. العزلُ يُثبت بـrun.py وضابطَيه."""
    try:
        socket.create_connection((CONTROL_HOST, 443), timeout=3).close()
        result = "reachable"
    except OSError:
        result = "unreachable"
    return {"host": f"{CONTROL_HOST}:443", "result": result, "proves_isolation": False}


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(cfg) - CONFIG_KEYS
    if unknown:
        raise SystemExit(
            f"مرفوض: مفاتيحُ غيرُ معروفة في إعداد المقيِّم {sorted(unknown)} — لا أمرَ حرّاً ولا وسائطَ إضافيّة"
        )
    for key in ("name", "version", "adapter", "model_path", "language", "params"):
        if key not in cfg:
            raise SystemExit(f"إعدادُ المقيِّم ناقص: {key}")
    if cfg["adapter"] not in ALLOWED:
        raise SystemExit(f"محوّلٌ غير معروف: {cfg['adapter']} (المسموح {sorted(ALLOWED)})")
    if cfg["language"] not in LANGUAGES[cfg["adapter"]]:
        raise SystemExit(
            f"لغةٌ غير مسموحة: {cfg['language']!r} للمحوّل {cfg['adapter']} "
            f"(نموذجُه يحمل {sorted(LANGUAGES[cfg['adapter']])})"
        )
    if "python" in cfg and not (
        Path(cfg["python"]).is_file() and os.access(cfg["python"], os.X_OK)
    ):
        raise SystemExit(f"python غيرُ موجود أو غيرُ قابلٍ للتنفيذ: {cfg['python']}")
    if "isolate_net" in cfg and not isinstance(cfg["isolate_net"], bool):
        raise SystemExit(f"مرفوض: isolate_net={cfg['isolate_net']!r} ليس true/false")
    allowed = ALLOWED[cfg["adapter"]]
    for key, value in cfg["params"].items():
        rule = allowed.get(key)
        if rule is None:
            raise SystemExit(
                f"مرفوض: معاملٌ غيرُ مسموح {key!r} للمحوّل {cfg['adapter']} (المسموح {sorted(allowed)})"
            )
        if isinstance(rule, set):
            if value not in rule:
                raise SystemExit(f"مرفوض: {key}={value!r} خارج {sorted(rule)}")
        else:
            kind, lo, hi = rule
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (kind is int and not isinstance(value, int))
                or not lo <= value <= hi
            ):
                raise SystemExit(f"مرفوض: {key}={value!r} ليس {kind.__name__} في [{lo}, {hi}]")
    for key in ("timeout_s", "load_timeout_s"):
        v = cfg.get(key)
        if v is not None and (
            isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 3600
        ):
            raise SystemExit(f"مرفوض: {key}={v!r} ليس عدداً في (0, 3600]")
    for key in ("model_path",) + (("binary",) if cfg["adapter"] == "whisper_cpp" else ()):
        if key not in cfg or not Path(cfg[key]).exists():
            raise SystemExit(f"{key} غير موجود محلّيّاً: {cfg.get(key)} — لا تنزيل من هنا")
    if cfg["adapter"] == "faster_whisper":
        # faster-whisper 1.2.1 (transcribe.py:703-711): مجلّدٌ بلا tokenizer.json يجلب openai/whisper-tiny من الشبكة
        # بصمت. فالمجلّدُ يجب أن يحمله، ويُشغَّل العاملُ بـHF_HUB_OFFLINE=1.
        model_dir = Path(cfg["model_path"])
        if not model_dir.is_dir() or not (model_dir / "tokenizer.json").is_file():
            raise SystemExit(
                f"مرفوض: model_path لـfaster_whisper يجب أن يكون مجلّداً فيه tokenizer.json ({model_dir}) — "
                "وإلّا جلبت المكتبةُ مُرمِّزاً من الشبكة بصمت"
            )
    if cfg["adapter"] == "pocketsphinx":
        model_dir = Path(cfg["model_path"])
        missing = [
            f"{k}={v}" for k, v in POCKETSPHINX_PARTS.items() if not (model_dir / v).exists()
        ]
        if missing or not (model_dir / POCKETSPHINX_PARTS["hmm"] / "mdef").is_file():
            raise SystemExit(
                f"مرفوض: model_path لـpocketsphinx يجب أن يحمل hmm وlm وdict صراحةً ({missing or 'mdef'}) — "
                "وإلّا فكّ Decoder() بنموذجه المضمَّن لا بالمُبصَم"
            )
    if cfg.get("isolate_net") and not shutil.which("unshare"):
        raise SystemExit("BLOCKED: isolate_net=true ولا unshare هنا — لا يُدّعى عزلُ شبكة المقيِّم")
    return cfg


class EvaluatorTimeout(Exception):
    pass


live_in_group = procs.live_in_group  # تبقى للاختبار المصطنع؛ الحكمُ عبر procs.group_status


def _kill_group(proc: subprocess.Popen) -> dict:
    """يقتل مجموعةَ عمليّات المقيِّم كلَّها (الأبناءَ أيضاً) ويتحقّق أنّ أحداً منها لم يبقَ حيّاً — **في فضاء PID
    هذه العمليّة**: ``killpg(pgid, 0)`` ⇒ ESRCH قاطع، و``/proc`` لا يُقرأ إلّا إن ثبت أنّه لفضائنا. الأيتامُ يتبنّاهم
    المُفرِز (subreaper) فيحصدهم هنا، فلا يبقى زومبي يُبقي المجموعةَ «موجودة». ``group_gone=None`` = تعذّر الإثبات."""
    pgid = proc.pid
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()
    for _ in range(100):
        procs.reap_group(pgid)
        state, alive, why = procs.group_status(pgid)
        if state == "gone":
            return {"killed_pgid": pgid, "group_gone": True, "evidence": why}
        time.sleep(0.02)
    if state == "unverifiable":
        return {"killed_pgid": pgid, "group_gone": None, "unverifiable": why}
    return {"killed_pgid": pgid, "group_gone": False, "alive": alive, "evidence": why}


class _PersistentWorker:
    """مقيِّمٌ (faster_whisper أو pocketsphinx) في **عمليّةٍ مستقلّة** (جلسةٌ ومجموعةُ عمليّاتٍ خاصّة): مهلةُ الطلب
    تُفرض بقتل المجموعة، لا برجاء أن تعود المكتبة. يُعاد تشغيلُه للمقطع التالي بعد أيّ قتل. مفسّرُه من ``python``
    في الإعداد (بيئةُ المقيِّم المنفصلة)، و``isolate_net`` يشغّله داخل ``unshare -n`` ويُثبت العزلَ بمسبارٍ داخله."""

    def __init__(self, cfg_path: Path, cfg: dict):
        self.cfg_path, self.cfg, self.proc, self.kwargs = cfg_path, cfg, None, None
        self.ready: dict = {}
        self.stderr = tempfile.TemporaryFile()
        self.buf = b""

    def _readline(self, timeout: float) -> dict:
        """سطرٌ JSON **كامل** قبل موعدٍ نهائيٍّ واحد. قراءةٌ غيرُ حاجبة (``os.read`` على الواصف بعد ``select``)
        تُراكم البايتات حتّى ``\\n``: ``readline()`` بعد نجاح ``select`` كان يحجب على حرفٍ بلا نهاية سطر فيتجاوز
        المهلة (v8: مهلةُ 0.1s دامت 5s). ما بعد السطر يبقى في المخزن للطلب التالي."""
        deadline = time.monotonic() + timeout
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EvaluatorTimeout(
                    f"لم يكتمل سطرُ الردّ خلال {timeout}s (وصل {len(self.buf)} بايت)"
                )
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                self.stderr.seek(0)
                raise RuntimeError(
                    f"انتهت عمليّةُ المقيِّم: {self.stderr.read().decode(errors='replace')[-200:]}"
                )
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))

    def _start(self) -> None:
        env = dict(
            os.environ, HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", TRANSFORMERS_OFFLINE="1"
        )
        self.buf = b""
        argv = [
            self.cfg.get("python", sys.executable),
            str(Path(__file__).resolve()),
            "--asr-worker",
            self.cfg["adapter"],
            str(self.cfg_path),
        ]
        if self.cfg.get("isolate_net"):
            argv = ["unshare", "-n", "--", *argv]
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            bufsize=0,
            start_new_session=True,
            env=env,
        )
        try:
            ready = self._readline(self.cfg.get("load_timeout_s", 600))
        except EvaluatorTimeout as exc:
            info = self.kill()
            raise EvaluatorTimeout(
                json.dumps(
                    info | {"reason": f"تحميلُ النموذج تجاوز load_timeout_s: {exc}"},
                    ensure_ascii=False,
                )
            ) from exc
        self.kwargs, self.ready = ready["kwargs"], ready
        if self.cfg.get("isolate_net") and ready.get("network_probe") != "unreachable":
            self.kill()
            raise SystemExit(
                f"مرفوض: isolate_net=true والمسبارُ داخل المقيِّم {ready.get('network_probe')!r} — لا عزل"
            )

    def kill(self) -> dict:
        info = _kill_group(self.proc) if self.proc else {}
        self.proc = None
        return info

    def __call__(self, wav: Path):
        if self.proc is None:
            self._start()
        self.proc.stdin.write((json.dumps({"wav": str(wav)}) + "\n").encode())
        try:
            reply = self._readline(self.cfg.get("timeout_s", 120))
        except EvaluatorTimeout as exc:
            raise EvaluatorTimeout(
                json.dumps(self.kill() | {"reason": str(exc)}, ensure_ascii=False)
            ) from exc
        except (ValueError, RuntimeError):
            self.kill()  # سطرٌ غيرُ JSON أو عاملٌ انتهى: لا يُعاد استعمالُ عاملٍ حالتُه مجهولة
            raise
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply["text"], {
            "kwargs": self.kwargs,
            "process": "subprocess",
            "pid": self.proc.pid,
            "worker_python": self.cfg.get("python", sys.executable),
            "isolate_net": bool(self.cfg.get("isolate_net")),
        }


def _serve(adapter: str, cfg_path: str) -> int:
    """داخل العمليّة المستقلّة: يُحمّل النموذج مرّة، ويُبلغ مسبارَ الشبكة من داخله، ثمّ سطرٌ JSON لكلّ طلب."""
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    p = cfg["params"]
    probe = _network_probe()["result"]
    if adapter == "faster_whisper":
        from faster_whisper import WhisperModel  # noqa: PLC0415 — اختياريّة

        model = WhisperModel(
            cfg["model_path"],
            device="cpu",
            compute_type=p.get("compute_type", "int8"),
            cpu_threads=p.get("cpu_threads", 0),
            local_files_only=True,
        )
        kwargs = {
            "language": cfg["language"],
            "beam_size": p.get("beam_size", 5),
            "temperature": p.get("temperature", 0.0),
            "condition_on_previous_text": False,
            "vad_filter": False,
            "initial_prompt": None,
        }

        def transcribe(wav: str) -> str:
            segments, _ = model.transcribe(wav, **kwargs)
            return " ".join(s.text.strip() for s in segments)
    else:  # pocketsphinx — الأجزاءُ الثلاثة صريحة، بلا نحوٍ ولا قاموسٍ مخصّصٍ ولا نصٍّ مرجعيّ
        import wave  # noqa: PLC0415

        from pocketsphinx import Decoder  # noqa: PLC0415 — اختياريّة

        model_dir = Path(cfg["model_path"])
        kwargs = {k: str(model_dir / v) for k, v in POCKETSPHINX_PARTS.items()} | {
            "loglevel": "FATAL"
        }
        decoder = Decoder(**kwargs)
        rate = int(decoder.config["samprate"])
        # ما يستعمله المفكِّكُ **فعلاً** (لا ما مرّرناه): يكشف الرجوعَ الصامت إلى النموذج المضمَّن
        actual = {k: decoder.config[k] for k in ("hmm", "lm", "dict")}

        def transcribe(wav: str) -> str:
            with wave.open(wav) as w:
                if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, rate):
                    raise ValueError(
                        f"يلزم PCM16 أحاديّ {rate}Hz لا {w.getnchannels()}ch/{8 * w.getsampwidth()}bit/"
                        f"{w.getframerate()}Hz"
                    )
                pcm = w.readframes(w.getnframes())
            decoder.start_utt()
            decoder.process_raw(pcm, full_utt=True)
            decoder.end_utt()
            return decoder.hyp().hypstr if decoder.hyp() else ""

        kwargs["full_utt"] = True
    actual_config = locals().get("actual")  # pocketsphinx وحده يعرّفه
    from importlib import metadata  # noqa: PLC0415

    dist = {"faster_whisper": "faster-whisper", "pocketsphinx": "pocketsphinx"}[adapter]
    try:
        version = metadata.version(dist)
    except metadata.PackageNotFoundError:
        version = None
    print(
        json.dumps(
            {
                "ready": True,
                "kwargs": kwargs,
                "decoder_config_actual": actual_config,
                "network_probe": probe,
                "library": dist,
                "library_version": version,
                "python": sys.version.split()[0],
            }
        ),
        flush=True,
    )
    for line in sys.stdin:
        try:
            print(
                json.dumps({"text": transcribe(json.loads(line)["wav"])}, ensure_ascii=False),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False),
                flush=True,
            )
    return 0


def make_transcriber(cfg: dict, cfg_path: Path):
    """يُعيد ``run(wav) -> (transcript, invocation)``. **كلا المحوّلين في عمليّةٍ مستقلّة** بمهلةٍ تُفرض بالقتل:
    ``timeout_s`` لكلّ مقطع، و``load_timeout_s`` لتحميل faster_whisper."""
    p = cfg["params"]
    if cfg["adapter"] == "whisper_cpp":

        def run(wav: Path):
            argv = [
                cfg["binary"],
                "-m",
                cfg["model_path"],
                "-l",
                cfg["language"],
                "-nt",
                "-np",
                "-f",
                str(wav),
            ]
            for key in sorted(p):
                argv += [WHISPER_CPP_FLAGS[key], str(p[key])]
            if cfg.get("isolate_net"):
                argv = ["unshare", "-n", "--", *argv]
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=cfg.get("timeout_s", 120))
            except subprocess.TimeoutExpired as exc:
                raise EvaluatorTimeout(json.dumps(_kill_group(proc))) from exc
            if proc.returncode != 0:
                raise RuntimeError(f"rc={proc.returncode}: {stderr.strip()[:200]}")
            return stdout.strip(), {"argv": argv}

        run.close = lambda: None
        return run
    worker = _PersistentWorker(cfg_path, cfg)
    worker.close = worker.kill
    return worker


def _invocation_values(obj) -> list[str]:
    """قيمُ الاستدعاء النصّيّة **عدا المسارات** (ملفّ النموذج والمقطع) — فكلمةٌ إنجليزيّة في مسارٍ مؤقّت لا تُعدّ تسريباً."""
    if isinstance(obj, dict):
        return [v for x in obj.values() for v in _invocation_values(x)]
    if isinstance(obj, (list, tuple)):
        return [v for x in obj for v in _invocation_values(x)]
    text = str(obj)
    return [] if text.startswith("/") or os.path.exists(text) else [text]


def reference_in(invocation: dict, text: str) -> bool:
    """هل يظهر النصُّ المرجعيّ — أو أيُّ كلمةٍ منه من ثلاثة أحرفٍ فأكثر، **بأيّ خطّ** — في الاستدعاء الفعليّ؟
    (v9 كان يتجاوز الكلماتِ اللاتينيّة، فلا يرى تسريبَ نصٍّ إنجليزيّ.)"""
    blob = " ".join(semantic.normalize(v) for v in _invocation_values(invocation)).split()
    words = {w for w in semantic.normalize(text).split() if len(w) >= 3}
    return any(w in blob for w in words)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--asr-config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--facts", default=str(HERE / "semantic_facts.json"))
    args = ap.parse_args()
    # مشغّلٌ ورّث SIGCHLD=SIG_IGN يجعل النواةَ تحصد الأبناءَ فوراً: waitpid ⇒ ECHILD ⇒ returncode = 0 لكلِّ ابن،
    # فيضيع فشلُه (مقيسٌ: 13 حالةَ رفضٍ صارت rc=0). يُعاد إلى الافتراضيّ قبل أيِّ عمليّةٍ فرعيّة، ويُسجَّل الموروث.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    # الأحفادُ الأيتام بعد قتل المقيِّم يتبنّاهم المُفرِزُ فيحصدهم (لا PID 1 الذي قد لا يحصد)، ويُسجَّل فضاءُ /proc:
    # في فضاءٍ آخر لا يُقرأ منه حالُ عمليّاتنا (مراجعةُ المالك على v13: /proc/172 كانت عمليّةً أخرى).
    supervision = {
        "subreaper": procs.become_subreaper(),
        "proc_matches_pid_namespace": procs.proc_namespace()[0],
        "proc_namespace_evidence": procs.proc_namespace()[1],
    }

    out, run = Path(args.out), Path(args.run)
    if out.exists():
        print(f"مرفوض: {out} موجود — كلّ فرزٍ في مجلّدٍ جديد", file=sys.stderr)
        return 5
    cfg = load_config(Path(args.asr_config))
    model_sha = _sha_path(Path(cfg["model_path"]))
    binary_sha = _sha_path(Path(cfg["binary"])) if cfg.get("binary") else None
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    facts = semantic.load_facts(Path(args.facts))
    transcribe = make_transcriber(cfg, Path(args.asr_config).resolve())
    evaluator = {
        "name": cfg["name"],
        "version": cfg["version"],
        "adapter": cfg["adapter"],
        "binary": cfg.get("binary"),
        "binary_sha256": binary_sha,
        "model_path": cfg["model_path"],
        "model_sha256": model_sha,
        "language": cfg["language"],
        "params": cfg["params"],
        "python": sys.version.split()[0],
        "timeout_s": cfg.get("timeout_s", 120),
        "load_timeout_s": cfg.get("load_timeout_s", 600),
        "isolation": "subprocess with own session; timeout enforced by killing the process group",
        "worker_python": cfg.get("python", sys.executable),
        "isolate_net": bool(cfg.get("isolate_net")),
        "semantic_py_sha256": _sha_path(HERE / "semantic.py"),
        "facts_sha256": _sha_path(Path(args.facts)),
    }
    with (HERE / "corpus.tsv").open(encoding="utf-8") as fh:
        import csv

        texts = {r["id"]: r["text"] for r in csv.DictReader(fh, delimiter="\t")}

    clips, network = [], _network_probe()
    for row in (r for r in result.get("sentences", []) if r.get("ok")):
        wav = run / "wav" / f"{row['id']}.wav"
        digest = hashlib.sha256(wav.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise SystemExit(f"مرفوض: بصمةُ {wav.name} لا تطابق result.json")
        t0 = time.perf_counter()
        timeout_info = None
        try:
            (transcript, invocation), error = transcribe(wav), None
        except EvaluatorTimeout as exc:
            transcript, invocation, error = (
                None,
                None,
                f"EvaluatorTimeout: > {cfg.get('timeout_s', 120)}s",
            )
            timeout_info = (
                json.loads(str(exc)) if str(exc).startswith("{") else {"detail": str(exc)}
            )
        except Exception as exc:  # noqa: BLE001 — فشلُ المقيِّم يُسجَّل علَماً، لا يُسقط الفرز
            transcript, invocation, error = None, None, f"{type(exc).__name__}: {exc}"
        leaked = reference_in(invocation, texts.get(row["id"], "")) if invocation else False
        if leaked:
            raise SystemExit(
                f"مرفوض: النصُّ المرجعيّ لـ{row['id']} ظهر في استدعاء المقيِّم {invocation}"
            )
        v = semantic.verdict(transcript, facts[row["id"]]) if transcript is not None else None
        if timeout_info is not None:
            screen = "EVALUATOR_TIMEOUT"
        elif error:
            screen = "EVALUATOR_FAILED"
        else:
            screen = {
                "FAILED_DECLARED_CHECKS": "FLAGGED",
                "REVIEW_UNCOVERED_CONTENT": "REVIEW_UNCOVERED_CONTENT",
                "PASSED_DECLARED_CHECKS": "NO_FLAG_ON_DECLARED_CHECKS",
            }[v["status"]]
        clips.append(
            {
                "sentence_id": row["id"],
                "clip_sha256": digest,
                "evaluator": evaluator,
                "invocation": invocation,
                "reference_text_in_invocation": leaked,
                "seconds": round(time.perf_counter() - t0, 3),
                "transcript": transcript,
                "evaluator_error": error,
                "timeout": timeout_info,
                "flags": v["errors"] if v else [],
                "uncovered_content": v["uncovered_content"] if v else [],
                "screen": screen,
            }
        )
    transcribe.close()
    if _sha_path(Path(cfg["model_path"])) != model_sha:
        raise SystemExit("مرفوض: تغيّرت أوزانُ المقيِّم أثناء الفرز")
    if binary_sha and _sha_path(Path(cfg["binary"])) != binary_sha:
        raise SystemExit("مرفوض: تغيّر ملفُّ المقيِّم التنفيذيّ أثناء الفرز")

    report = {
        "kind": "auxiliary ASR screen — not a verdict; not read by score.py",
        "run_id": result.get("run_id"),
        "engine": result.get("engine"),
        "network_probe": network,
        "clips": clips,
        "process_supervision": supervision,
        # ما أبلغه المقيِّمُ من داخل عمليّته: إصدارُ المكتبة الفعليّ، ومسبارُ الشبكة **حيث يعمل**
        "evaluator_runtime": {
            k: v for k, v in getattr(transcribe, "ready", {}).items() if k != "ready"
        },
        # العزلُ مُثبتٌ فقط إن بلغ المنسّقُ الهدفَ **خارج** المقيِّم ولم يبلغه المقيِّمُ داخله (ضابطٌ سلبيّ)
        "evaluator_network_isolation": (
            "NOT_REQUESTED"
            if not cfg.get("isolate_net")
            else "NOT_PROBED (whisper_cpp: unshare -n بلا مسبارٍ داخليّ)"
            if cfg["adapter"] == "whisper_cpp"
            else "BLOCKED (الهدفُ غيرُ مبلوغٍ خارجاً أيضاً — لا يميّز المسبارُ شيئاً)"
            if network["result"] != "reachable"
            else "PROVEN"
            if getattr(transcribe, "ready", {}).get("network_probe") == "unreachable"
            else "NOT_STARTED"
        ),
        "summary": {s: sum(c["screen"] == s for c in clips) for s in SCREENS},
    }
    out.mkdir(parents=True)
    (out / "asr_screen.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"network_probe": network["result"]} | report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--asr-worker":
        sys.exit(_serve(sys.argv[2], sys.argv[3]))
    sys.exit(main())
