"""مراجعةُ Copilot على #1133 لحزمة ``tools/tts_bakeoff`` — حالةٌ لكلّ عيبٍ أُصلِح، بلا root ولا namespace فتعمل في CI.

- بيئةُ العامل قائمةُ سماح: لا تصل أسرارُ المضيف إلى شيفرة النموذج.
- البصمةُ المقيسةُ عند التنزيل ليست «موثوقة»: ``trusted_sha256`` لا يُملأ بها.
- PCM8 بلا إشارة يُفحص ولا ينهار.
- ماسحُ المجموعة يعدّ ``X`` ميّتاً كما يعدّه ``pid_status``.
- التقديرات «1-5» منتهيةٌ داخل مداها، و``--min-reviewers`` لا يقلّ عن 1.
- مقارنةُ الأداء تتطلّب جذراً فارغاً (bwrap): سجلٌّ بـunshare يُرفض بسببه.

ومن مراجعة Copilot الثانية (على رأس ``ab675a8e``):

- عمّالُ ASR (``faster_whisper``/``pocketsphinx`` المستمرّ و``whisper_cpp``) يرثون قائمةَ السماح لا بيئةَ المضيف.
- كلُّ ربطٍ في صندوق bwrap يُفحص بنفسه: ``rw:/`` أو ربطُ ``/home`` لا يمرّان لمجرّد أنّ القائمة غيرُ فارغة.
- بصمةُ الحِمل بين التشغيلات تشمل عددَ طلبات كلّ مستوى تزامن.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
import wave
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PKG = Path(__file__).resolve().parents[1] / "tools" / "tts_bakeoff"
sys.path.insert(0, str(PKG))

import asr_screen  # noqa: E402
import audio  # noqa: E402
import perf  # noqa: E402
import procs  # noqa: E402
import run  # noqa: E402
import score  # noqa: E402


def test_worker_env_is_an_allowlist_that_drops_host_secrets():
    host = {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "AWS_SECRET_ACCESS_KEY": "s",
        "DATABASE_URL": "postgres://u:p@h/db",
        "SMTP_PASSWORD": "p",
        "GITHUB_TOKEN": "t",
        "HTTPS_PROXY": "http://proxy",
    }
    env = run.worker_env(host)
    assert env == {"PATH": "/usr/bin", "LANG": "C.UTF-8"}
    assert set(env) <= set(run.WORKER_ENV_ALLOW)


def test_measured_download_hash_is_not_marked_trusted():
    sources = json.loads((PKG / "sources.example.json").read_text(encoding="utf-8"))
    entries = [e for e in sources["files"] if "measured_sha256_unverified" in e]
    assert entries, "مدخلُ catt ذو البصمة المقيسة غيرِ المُطابَقة مفقود"
    for entry in entries:
        assert entry["trusted_sha256"] is None
        assert entry["measured_sha256_unverified"] != entry["trusted_sha256"]


def _pcm8_wav(seconds: float = 0.5, rate: int = 16000) -> bytes:
    frames = bytes(
        int(128 + 100 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(int(seconds * rate))
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_unsigned_pcm8_is_validated_not_crashed():
    data = _pcm8_wav()
    assert any(b < 128 for b in data[44:])  # عيّناتٌ تحت المركز هي ما كان يُسقط bytes()
    check = audio.validate_wav(data)
    assert check is not None


def test_pcm8_silence_is_still_rejected():
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(16000)
        w.writeframes(bytes([128]) * 8000)
    with pytest.raises(audio.AudioRejected):
        audio.validate_wav(buf.getvalue())


def test_group_scan_treats_state_x_as_dead(tmp_path):
    for pid, state in ((201, "X"), (202, "Z"), (203, "S")):
        (tmp_path / str(pid)).mkdir()
        (tmp_path / str(pid) / "stat").write_text(
            f"{pid} (p) {state} 1 777 777 0 -1", encoding="utf-8"
        )
    assert procs.live_in_group(777, tmp_path) == [203]
    assert set(procs.DEAD_STATES) == {"Z", "X"}


@pytest.mark.parametrize(
    "value", ["nan", "NaN", "inf", "-Infinity", "1e309", "0", "5.5", "7", "abc"]
)
def test_rating_outside_declared_range_rejects_the_sheet(value):
    with pytest.raises(SystemExit):
        score._rating(value, "sheet.csv: C1 «الوضوح (1-5)»")


@pytest.mark.parametrize(
    ("value", "expected"), [("", None), ("  ", None), ("1", 1.0), ("3.5", 3.5), ("5", 5.0)]
)
def test_rating_inside_range_or_empty(value, expected):
    assert score._rating(value, "w") == expected


@pytest.mark.parametrize("minimum", ["0", "-1"])
def test_min_reviewers_below_one_is_refused(monkeypatch, tmp_path, minimum):
    monkeypatch.setattr(
        sys, "argv", ["score.py", str(tmp_path), "a.csv", "--min-reviewers", minimum]
    )
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert "min-reviewers" in str(exc.value)


def test_comparability_requires_an_empty_root_sandbox():
    fixture = json.loads((PKG / "fixtures" / "comparable_result.json").read_text(encoding="utf-8"))
    assert not [p for p in perf.evidence_problems(fixture) if "sandbox" in p]
    for kind, binds in (("unshare", None), ("bwrap", [])):
        record = json.loads(json.dumps(fixture))
        record["coordinator"]["sandbox"] = {
            "kind": kind,
            **({} if binds is None else {"binds": binds}),
        }
        assert [p for p in perf.evidence_problems(record) if "sandbox" in p], kind
        assert perf.why_not_comparable(record)


def test_fixture_is_still_schema_valid_and_comparable():
    pytest.importorskip("jsonschema")
    fixture = json.loads((PKG / "fixtures" / "comparable_result.json").read_text(encoding="utf-8"))
    assert perf.schema_problems(fixture) == []
    assert perf.why_not_comparable(fixture) == []


class _Captured(Exception):
    pass


HOST_SECRETS = {
    "PATH": "/usr/bin",
    "AWS_SECRET_ACCESS_KEY": "s",
    "DATABASE_URL": "postgres://u:p@h/db",
    "HF_TOKEN": "t",
}


@pytest.mark.parametrize("adapter", ["faster_whisper", "pocketsphinx", "whisper_cpp"])
def test_asr_workers_inherit_the_allowlist_not_the_host_environment(monkeypatch, tmp_path, adapter):
    for k in list(asr_screen.os.environ):
        monkeypatch.delenv(k, raising=False)
    for k, v in HOST_SECRETS.items():
        monkeypatch.setenv(k, v)
    seen = {}

    def fake_popen(argv, **kw):
        seen["env"] = kw.get("env")
        raise _Captured

    monkeypatch.setattr(asr_screen.subprocess, "Popen", fake_popen)
    cfg = {
        "adapter": adapter,
        "params": {},
        "binary": "whisper-cli",
        "model_path": "m.bin",
        "language": "ar",
    }
    run = asr_screen.make_transcriber(cfg, tmp_path / "cfg.json")
    with pytest.raises(_Captured):
        if adapter == "whisper_cpp":
            run(tmp_path / "a.wav")
        else:
            run._start()
    env = seen["env"]
    assert env is not None, "Popen بلا env يرث بيئةَ المضيف كلَّها"
    assert not set(env) & {"AWS_SECRET_ACCESS_KEY", "DATABASE_URL", "HF_TOKEN"}
    assert env.get("PATH") == "/usr/bin"
    assert set(env) - {"HF_HUB_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "TRANSFORMERS_OFFLINE"} <= set(
        asr_screen.ASR_ENV_ALLOW
    )
    assert set(asr_screen.ASR_ENV_ALLOW) - set(procs.WORKER_ENV_ALLOW) == {
        "PYTHONPATH",
        "BAKEOFF_CONTROL_HOST",
    }


def _fixture():
    return json.loads((PKG / "fixtures" / "comparable_result.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b, out: ["rw:/"],
        lambda b, out: b + ["rw:/home"],
        lambda b, out: [x for x in b if not x.startswith("rw:")] + ["rw:/tmp/other-run"],
        lambda b, out: b + ["ro:/"],
        lambda b, out: b + ["ro:/home"],
        lambda b, out: b + ["ro:/root"],
        lambda b, out: b + ["ro:/usr/lib/../../etc"],
        lambda b, out: b + ["link:/usr/local/bin/python3->/home/user/evil"],
        lambda b, out: b + ["bind:/etc"],
    ],
    ids=[
        "rw-root",
        "second-rw",
        "rw-other-run",
        "ro-root",
        "ro-home",
        "ro-root-home",
        "ro-dotdot",
        "link-out",
        "bad-kind",
    ],
)
def test_comparability_validates_every_bind_not_only_non_empty(mutate):
    fixture = _fixture()
    binds = fixture["coordinator"]["sandbox"]["binds"]
    out = next(x[3:] for x in binds if x.startswith("rw:"))
    record = json.loads(json.dumps(fixture))
    record["coordinator"]["sandbox"]["binds"] = mutate(list(binds), out)
    problems = [p for p in perf.evidence_problems(record) if p.startswith("sandbox")]
    assert problems, record["coordinator"]["sandbox"]["binds"][-1]
    assert perf.why_not_comparable(record)


def test_real_bwrap_binds_are_all_accepted():
    fixture = _fixture()
    assert (
        perf.sandbox_bind_problems(fixture["coordinator"]["sandbox"]["binds"], fixture["run_id"])
        == []
    )


def test_workload_signature_includes_requests_per_level(tmp_path, monkeypatch, capsys):
    a, b = _fixture(), _fixture()
    b["run_id"] = a["run_id"]  # الصندوقُ نفسُه؛ الفرقُ في الحِمل وحده
    level = sorted(b["concurrency"])[0]
    b["concurrency"][level]["requests"] += 1
    paths = []
    for i, rec in enumerate((a, b)):
        run_dir = tmp_path / f"run{i}"
        run_dir.mkdir()
        (run_dir / "result.json").write_text(json.dumps(rec), encoding="utf-8")
        paths.append(str(run_dir))
    monkeypatch.setattr(sys, "argv", ["perf.py", *paths])
    assert perf.main() == 2
    assert "عدد الطلبات" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["perf.py", paths[0], paths[0]])
    assert perf.main() == 0


# ── محوّل Kokoro (الشهادة الإنجليزيّة) — بلا أوزانٍ ولا onnxruntime: الوحدتان مُستبدَلتان ─────────
#
# الشاهدُ يثبت ما يعد به المحوّل: الإصدارُ مفروض، الجلسةُ تُبنى بخياراتٍ صريحة وتُمرَّر بـfrom_session،
# الصوتُ غيرُ الموجود يُرفض عند التحميل لا عند أوّل طلب، والمخرجُ WAV PCM16 أحاديّ مقصوصٌ إلى [-1, 1].


class _FakeSessionOptions:
    def __init__(self):
        self.intra_op_num_threads = 0
        self.inter_op_num_threads = 0
        self.entries = {}

    def add_session_config_entry(self, key, value):
        self.entries[key] = value


class _FakeKokoro:
    created = []

    def __init__(self, session, voices_path):
        self.session, self.voices_path = session, voices_path

    @classmethod
    def from_session(cls, session, voices_path):
        inst = cls(session, voices_path)
        cls.created.append(inst)
        return inst

    def get_voices(self):
        return ["af_heart", "am_adam"]

    def create(self, text, voice, speed, lang):
        import numpy as np

        self.last = (text, voice, speed, lang)
        return np.array([0.0, 0.5, 2.0, -3.0], dtype=np.float32), 24000


def _stub_kokoro(monkeypatch, version="0.6.1"):
    import importlib.metadata
    import types

    sessions = []
    ort = types.ModuleType("onnxruntime")
    ort.SessionOptions = _FakeSessionOptions
    ort.InferenceSession = lambda path, sess_options, providers: (
        sessions.append((path, sess_options, providers)) or ("session", path)
    )
    kmod = types.ModuleType("kokoro_onnx")
    kmod.Kokoro = _FakeKokoro
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    monkeypatch.setitem(sys.modules, "kokoro_onnx", kmod)
    real = importlib.metadata.version
    monkeypatch.setattr(
        importlib.metadata, "version", lambda d: version if d == "kokoro-onnx" else real(d)
    )
    _FakeKokoro.created = []
    return sessions


_KOKORO_CFG = {"model": "m.onnx", "voices": "v.bin", "voice": "af_heart"}


def test_kokoro_builds_its_own_pinned_session(monkeypatch):
    import engines

    sessions = _stub_kokoro(monkeypatch)
    eng = engines.ENGINES["kokoro"](dict(_KOKORO_CFG, ort_intra_threads=2))
    ((path, opts, providers),) = sessions
    assert path == "m.onnx" and providers == ["CPUExecutionProvider"]
    assert opts.intra_op_num_threads == 2 and opts.inter_op_num_threads == 1
    assert opts.entries["session.intra_op.allow_spinning"] == "0"
    assert _FakeKokoro.created[0].session == ("session", "m.onnx")
    assert eng.version == "0.6.1" and "espeak-ng" in eng.g2p["backend"]


def test_kokoro_rejects_an_unpinned_version_or_an_unknown_voice(monkeypatch):
    import engines

    _stub_kokoro(monkeypatch, version="0.7.0")
    with pytest.raises(RuntimeError, match="0.6.1"):
        engines.ENGINES["kokoro"](dict(_KOKORO_CFG))
    _stub_kokoro(monkeypatch)
    with pytest.raises(ValueError, match="bf_missing"):
        engines.ENGINES["kokoro"](dict(_KOKORO_CFG, voice="bf_missing"))
    with pytest.raises(ValueError, match="voice"):
        engines.ENGINES["kokoro"]({"model": "m.onnx", "voices": "v.bin"})


def test_kokoro_output_is_clipped_mono_pcm16_wav(monkeypatch):
    import engines

    _stub_kokoro(monkeypatch)
    eng = engines.ENGINES["kokoro"](dict(_KOKORO_CFG, speed=1.1))
    data = eng.synthesize("Irrigate in the early morning.")
    assert _FakeKokoro.created[0].last == (
        "Irrigate in the early morning.",
        "af_heart",
        1.1,
        "en-us",
    )
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        frames = w.readframes(w.getnframes())
    import struct

    assert struct.unpack("<4h", frames) == (0, 16383, 32767, -32767)


def test_kokoro_manifest_pins_every_path_it_loads():
    import engines

    models = json.loads((PKG / "models.example.json").read_text(encoding="utf-8"))
    entry = models["kokoro"]
    for key in engines.PATH_SETTINGS["kokoro"]:
        assert entry["settings"][key] in entry["files"], key
    assert set(engines.PATH_SETTINGS["kokoro"]) == {"model", "voices"}
    assert all(sha is None for sha in entry["files"].values()), "لا بصمةَ قبل مطابقة المصدر"


# ── cgroup v2: الحدود تُقاس على المضيفات الحديثة لا تُحجب ──────────────────────────────────
#
# قياسُ المالك على WSL2 (نواة 6.6): 44 نجاحاً و0 فشلاً و6 BLOCKED، وكلُّها BLOCKED لسببٍ واحد —
# ``setup_cgroups`` كان يعرف v1 فقط، وWSL2 وUbuntu 22.04+ على v2. فأيُّ تشغيلٍ هناك يخرج
# ``performance_comparable=false`` دائماً، لا لعيبٍ في المحرّك بل لأنّ الأداة لا تقرأ الهرم المُركَّب.


def _fake_v2_root(tmp_path, controllers="cpu memory pids", subtree=""):
    (tmp_path / "cgroup.controllers").write_text(controllers, encoding="utf-8")
    (tmp_path / "cgroup.subtree_control").write_text(subtree, encoding="utf-8")
    return tmp_path


def _fake_v1_root(tmp_path):
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "memory.limit_in_bytes").write_text("max", encoding="utf-8")
    (tmp_path / "cpu").mkdir()
    (tmp_path / "cpu" / "cpu.cfs_period_us").write_text("100000", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("shape", ["v1", "v2", "hybrid", "none"])
def test_the_mounted_cgroup_hierarchy_is_detected_not_assumed(tmp_path, monkeypatch, shape):
    if shape in ("v1", "hybrid"):
        _fake_v1_root(tmp_path)
    if shape in ("v2", "hybrid"):
        _fake_v2_root(tmp_path)
    monkeypatch.setattr(run, "CG", tmp_path)
    assert run.cgroup_hierarchy() == {"v1": "v1", "hybrid": "v1", "v2": "v2", "none": None}[shape]


def test_cgroup_v2_writes_the_unified_limits_and_enables_the_controllers(tmp_path, monkeypatch):
    root = _fake_v2_root(tmp_path)
    monkeypatch.setattr(run, "CG", root)

    real_mkdir = Path.mkdir

    def mkdir(self, *a, **k):  # الملفّان لا يوجدان في الابن إلّا إن سرى المتحكّم — نحاكي سريانه
        real_mkdir(self, *a, **k)
        (self / "memory.max").write_text("max", encoding="utf-8")
        (self / "cpu.max").write_text("max 100000", encoding="utf-8")

    monkeypatch.setattr(Path, "mkdir", mkdir)
    info = run.setup_cgroups("bakeoff-t", 2048, 2.0)
    group = root / "bakeoff-t"
    assert info["backend"] == "cgroup-v2"
    assert info["paths"] == [str(group)]
    assert info["controllers_enabled_by_us"] == ["memory", "cpu"]
    assert (root / "cgroup.subtree_control").read_text(encoding="utf-8") == "+memory +cpu"
    assert (group / "memory.max").read_text(encoding="utf-8") == str(2048 * 1024 * 1024)
    assert (group / "cpu.max").read_text(encoding="utf-8") == "200000 100000"


def test_cgroup_v2_without_the_controllers_is_unavailable_not_silently_unlimited(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run, "CG", _fake_v2_root(tmp_path, controllers="pids io"))
    info = run.setup_cgroups("bakeoff-t", 2048, 2.0)
    assert info["backend"] == "UNAVAILABLE"
    assert "memory" in info["error"] and info["paths"] == []


def test_no_hierarchy_at_all_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "CG", tmp_path)
    assert run.setup_cgroups("bakeoff-t", 2048, 2.0)["backend"] == "UNAVAILABLE"


def _write_v2_stats(group, peak="314572800", events="low 0\nhigh 0\nmax 3\noom 0\noom_kill 0"):
    group.mkdir(parents=True, exist_ok=True)
    if peak is not None:
        (group / "memory.peak").write_text(peak, encoding="utf-8")
    (group / "memory.events").write_text(events, encoding="utf-8")
    (group / "cpu.stat").write_text(
        "usage_usec 1\nnr_periods 400\nnr_throttled 20\nthrottled_usec 1500000",
        encoding="utf-8",
    )
    return group


def test_cgroup_v2_stats_read_peak_events_and_microsecond_throttling(tmp_path):
    group = _write_v2_stats(tmp_path / "bakeoff-t")
    stats = run.cgroup_stats({"backend": "cgroup-v2", "paths": [str(group)]})
    assert stats["cgroup_version"] == "v2"
    assert stats["memory_peak_mb"] == 300.0
    assert (stats["memory_failcnt"], stats["oom_kill_events"]) == (3, 0)
    assert (stats["cpu_periods"], stats["cpu_throttled_periods"]) == (400, 20)
    assert stats["cpu_throttled_ratio"] == 0.05
    # ``throttled_usec`` ميكروثانية: 1.5 ثانية — لا 0.0015 لو قُرئت نانوثانيةً كـv1
    assert stats["cpu_throttled_s"] == 1.5


def test_a_kernel_without_memory_peak_declares_it_instead_of_substituting_current(tmp_path):
    group = _write_v2_stats(tmp_path / "bakeoff-t", peak=None)
    (group / "memory.current").write_text("999999999", encoding="utf-8")
    stats = run.cgroup_stats({"backend": "cgroup-v2", "paths": [str(group)]})
    assert "memory_peak_mb" not in stats
    assert "memory.peak" in stats["memory_peak_unavailable"]
    # وبوّابةُ الأداء ترفض سجلّاً بلا ذروةٍ موجبة، فالغيابُ لا يصير مقارنةً
    problems = perf.evidence_problems(
        {"performance_comparable": True, "coordinator": {"cgroup_stats": stats}}
    )
    assert any("memory_peak_mb" in problem for problem in problems)


@pytest.mark.parametrize(
    ("backend", "count", "flagged"),
    [
        ("cgroup-v2", 1, False),
        ("cgroup-v2", 2, True),
        ("cgroup-v1", 2, False),
        ("cgroup-v1", 1, True),
    ],
)
def test_the_perf_gate_counts_the_groups_each_version_actually_creates(backend, count, flagged):
    record = {
        "performance_comparable": True,
        "coordinator": {"cgroup": {"backend": backend, "paths": [f"/p{i}" for i in range(count)]}},
    }
    problems = [p for p in perf.evidence_problems(record) if p.startswith("cgroup.backend=")]
    assert bool(problems) is flagged


@pytest.mark.parametrize(
    ("memory_max", "status"), [("2147483648", "ENFORCED"), ("max", "MISMATCH")]
)
def test_the_worker_reads_the_v2_limits_from_inside_the_process(
    tmp_path, monkeypatch, memory_max, status
):
    import worker

    group = tmp_path / "bakeoff-t"
    group.mkdir()
    (group / "memory.max").write_text(memory_max, encoding="utf-8")
    (group / "cpu.max").write_text("200000 100000", encoding="utf-8")
    proc = tmp_path / "self-cgroup"
    proc.write_text("0::/bakeoff-t\n", encoding="utf-8")
    monkeypatch.setattr(worker, "CG", tmp_path)
    monkeypatch.setattr(worker, "PROC_CGROUP", proc)
    cores = ",".join(str(c) for c in sorted(os.sched_getaffinity(0))[:1])
    monkeypatch.setenv(
        "BAKEOFF_LIMITS",
        json.dumps(
            {
                "cgroup": "cgroup-v2",
                "memory_limit_mb": 2048,
                "cpu_quota": 2.0,
                "cpu_cores": cores,
            }
        ),
    )
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {int(cores)})
    result = worker.verify_limits()
    assert result["status"] == status
    assert result["in_effect"]["cpu_quota"] == 2.0
    assert result["in_effect"]["memory_cgroup"] == "/bakeoff-t"


def test_the_english_corpus_mirrors_the_arabic_one_field_for_field():
    import csv

    def rows(name):
        with (PKG / name).open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    arabic, english = rows("corpus.tsv"), rows("corpus_en.tsv")
    assert [r["id"] for r in english] == [r["id"] for r in arabic]
    assert [r["category"] for r in english] == [r["category"] for r in arabic]
    assert all(set(r) == set(arabic[0]) and all(r.values()) for r in english)
    # كلُّ جملةٍ مُعلَنةٌ اصطناعيّة، ولا حرفَ عربيّاً في نصٍّ إنجليزيّ
    assert all(r["synthetic_example"].startswith("yes") for r in english)
    assert not any("؀" <= ch <= "ۿ" for r in english for ch in r["text"])


# ── المفسّرُ والمضيف يجب أن يتساويا بين التشغيلات ───────────────────────────────────────────
#
# قيدٌ حقيقيّ مقيسٌ من بيانات الحزم: ``kokoro-onnx==0.6.1`` يشترط ``Requires-Python: >=3.10,<3.14``،
# و``silma-tts==1.0.5`` يثبّت ``numpy<=1.26.4`` التي لا عجلةَ لها بعد cp312 — فالمحرّكان يُشغَّلان
# على 3.12 ولو كان المضيفُ على 3.14. وكانت ``perf.py`` تُقارن ``corpus_sha256`` و``scripts_sha256``
# فقط، فتشغيلان على بايثونَين أو جهازَين مختلفَين يُقارَنان كأنّهما متكافئان.


def _two_runs(tmp_path, **second_environment):
    fixture = json.loads((PKG / "fixtures" / "comparable_result.json").read_text(encoding="utf-8"))
    out = []
    for index, overrides in enumerate(({}, second_environment)):
        record = json.loads(json.dumps(fixture))
        record.setdefault("environment", {}).update(overrides)
        directory = tmp_path / f"run{index}"
        directory.mkdir()
        (directory / "result.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        out.append(str(directory))
    return out


@pytest.mark.parametrize(
    "overrides",
    [
        {"python": "3.13.1"},
        {"platform": "Linux-6.6.0-microsoft-standard-WSL2-x86_64"},
        {"cpu_model": "AMD Ryzen 9 7950X"},
        {"cpu_visible": 32},
        {"thread_env": {"OMP_NUM_THREADS": "4"}},
    ],
    ids=["python", "platform", "cpu_model", "cpu_visible", "thread_env"],
)
def test_runs_on_a_different_interpreter_or_host_are_not_compared(
    tmp_path, monkeypatch, capsys, overrides
):
    monkeypatch.setattr(sys, "argv", ["perf.py", *_two_runs(tmp_path, **overrides)])
    assert perf.main() == 2
    field = next(iter(overrides))
    assert f"environment.{field} يختلف بين التشغيلات" in capsys.readouterr().err


def test_two_identical_runs_are_still_compared(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["perf.py", *_two_runs(tmp_path)])
    assert perf.main() == 0
    assert "يختلف بين التشغيلات" not in capsys.readouterr().err
