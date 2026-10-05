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
