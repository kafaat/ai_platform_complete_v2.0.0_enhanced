"""صندوقُ ``tools/tts_bakeoff`` مع بيئةٍ افتراضيّة حقيقيّة — عيوبُ تشغيل Kokoro عند المالك على WSL2 (2026-10-06).

الأداةُ المدموجة (``9801d076``) لم تُشغِّل أيَّ محرّكٍ مثبّتٍ في venv تحت bwrap، وما تجاوز ذلك بترقيعٍ محلّيّ
بقي «غيرَ قابلٍ للمقارنة» لأسبابٍ من الأداة نفسها. كلُّ حالةٍ هنا حمراءُ على ``main@77f9f188`` وحتميّةٌ بلا root
ولا bwrap ولا cgroup حقيقيّ (مسارٌ مصطنع أو ترقيعٌ صريح)، فتعمل في CI. التشغيلُ الحقيقيّ تحت bwrap في
``selftest.py`` (الحالة v15).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PKG = Path(__file__).resolve().parents[1] / "tools" / "tts_bakeoff"
sys.path.insert(0, str(PKG))

import engines  # noqa: E402
import perf  # noqa: E402
import run  # noqa: E402
import worker  # noqa: E402


def _venv(tmp_path: Path) -> tuple[Path, Path, Path]:
    """بايثونٌ مستقلّ (كـuv) وبيئةٌ افتراضيّة مفسّرُها رابطٌ إليه — شكلُ ``/root/tts/pythons`` عند المالك."""
    base = tmp_path / "pythons" / "cpython-3.12"
    (base / "bin").mkdir(parents=True)
    (base / "lib" / "python3.12" / "lib-dynload").mkdir(parents=True)
    real = base / "bin" / "python3.12"
    real.write_text("#!/bin/sh\n")
    real.chmod(0o755)
    venv = tmp_path / "venv_kokoro"
    (venv / "bin").mkdir(parents=True)
    (venv / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(real)
    return base, venv, venv / "bin" / "python"


def _fixture() -> dict:
    return json.loads((PKG / "fixtures" / "comparable_result.json").read_text(encoding="utf-8"))


def _manifest(tmp_path: Path) -> Path:
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({"fake": {"files": {}, "settings": {"mode": "ok"}}}), encoding="utf-8")
    return m


# ── 1) bwrap: رابطُ المفسّر تحت بادئةٍ مربوطة لا يُربط ثانيةً ─────────────────────────────────────


def test_path_under_a_bound_directory_is_not_bound_again(tmp_path):
    """``--ro-bind venv/bin/python`` داخل ``venv`` المربوط للقراءة فقط ⇒ «Can't create file at venv/bin/python»."""
    base, venv, py = _venv(tmp_path)
    ro = [
        str(base),
        str(base / "lib" / "python3.12"),
        str(venv),
        str(venv / "lib" / "python3.12" / "site-packages"),
        str(py),
    ]
    out = tmp_path / "out"
    args, binds = run.bwrap_command(["true"], ro, [str(out)])
    assert str(py) not in args
    assert binds == [f"ro:{base}", f"ro:{venv}", f"rw:{out}"]


def test_every_hop_of_a_stdlib_venv_interpreter_is_reachable(tmp_path):
    """``python -m venv``: ``venv/bin/python → python3 → /usr/local/bin/python3 → /usr/bin/python3.11``.
    القفزةُ الوسطى خارج كلّ ربط؛ بدونها ``bwrap: execvp … No such file`` (الحالة v15 حمراءُ قبل هذا)."""
    usr_bin = tmp_path / "usr" / "bin"
    usr_bin.mkdir(parents=True)
    real = usr_bin / "python3.11"
    real.write_text("#!/bin/sh\n")
    local = tmp_path / "usr" / "local" / "bin"
    local.mkdir(parents=True)
    (local / "python3").symlink_to(real)
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python3").symlink_to(local / "python3")
    (venv / "bin" / "python").symlink_to("python3")
    py = venv / "bin" / "python"
    chain = run.link_chain(str(py))
    assert chain == [str(py), str(venv / "bin" / "python3"), str(local / "python3"), str(real)]
    out = tmp_path / "out"
    _, binds = run.bwrap_command(["true"], [str(usr_bin), str(venv), *chain], [str(out)])
    assert binds == [
        f"ro:{usr_bin}",
        f"ro:{venv}",
        f"link:{local / 'python3'}->{real}",
        f"rw:{out}",
    ]


def test_link_whose_target_is_outside_every_bind_is_skipped_and_recorded(tmp_path):
    """``/etc/resolv.conf → /mnt/wsl/resolv.conf``: إنشاءُ الرابط يسمّي هدفاً غيرَ معلن ولا يُوصل إليه."""
    target = tmp_path / "mnt" / "wsl" / "resolv.conf"
    target.parent.mkdir(parents=True)
    target.write_text("nameserver 10.255.255.254\n")
    link = tmp_path / "etc" / "resolv.conf"
    link.parent.mkdir()
    link.symlink_to(target)
    out = tmp_path / "out"
    args, binds = run.bwrap_command(["true"], [str(link)], [str(out)])
    assert binds == [f"skip:{link}->{target}", f"rw:{out}"]
    assert str(link) not in args
    assert perf.sandbox_bind_problems(binds, "out") == []


# ── 2) perf: بادئتا المفسّر مقبولتان، ولا شيءَ أوسع ─────────────────────────────────────────────


def test_interpreter_licenses_its_venv_and_base_prefix_only(tmp_path):
    base, venv, py = _venv(tmp_path)
    interp = {"path": str(py), "real": str(base / "bin" / "python3.12")}
    out = tmp_path / "runs" / "r1"
    binds = [f"ro:{base}", f"ro:{venv}", f"rw:{out}"]
    assert perf.sandbox_bind_problems(binds, "r1", interp) == []
    # الربطاتُ نفسها بلا مفسّرٍ مُسجَّل تبقى خارج المعلن — البوّابةُ لم تُفتح لكلّ مجلّد
    assert len(perf.sandbox_bind_problems(binds, "r1")) == 2
    for p in ("/opt/bin/python3", "/usr/bin/python3", "/usr/local/bin/python3", "/bin/python"):
        assert perf.interpreter_prefixes({"path": p}) == set(), p
    assert perf.sandbox_bind_problems(
        ["ro:/home", f"rw:{out}"], "r1", {"path": "/home/bin/python3"}
    )


def test_declared_interpreter_must_be_the_one_that_ran():
    r = _fixture()
    assert r["coordinator"]["sandbox"]["interpreter"]["path"] in r["coordinator"]["command"]
    assert not [p for p in perf.evidence_problems(r) if "interpreter" in p]
    r["coordinator"]["sandbox"]["interpreter"]["path"] = "/srv/other/venv/bin/python"
    assert [p for p in perf.evidence_problems(r) if "interpreter" in p]


# ── 3) المبادلة: حدُّ الذاكرة بلا إغلاقها لا يُقاس ───────────────────────────────────────────────


def test_limit_swap_closes_it_when_the_kernel_exposes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "host_swap_active", lambda: True)
    f = tmp_path / "memory.swap.max"
    f.write_text("max\n")
    assert run._limit_swap(f, "0") == {
        "limited": True,
        "file": "memory.swap.max",
        "value": "0",
        "host_swap_active": True,
    }
    assert f.read_text() == "0"
    absent = run._limit_swap(tmp_path / "nope", "0")
    assert absent["limited"] is False and absent["host_swap_active"] is True


def test_v2_group_records_whether_swap_was_closed(tmp_path, monkeypatch):
    """الهرمُ الموحّد المصطنع بلا ``memory.swap.max`` (محاسبةُ المبادلة معطّلة) — يُسجَّل ولا يُدّعى الإغلاق."""
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "cgroup.controllers").write_text("cpu memory io\n")
    (cg / "cgroup.subtree_control").write_text("cpu memory\n")
    monkeypatch.setattr(run, "CG", cg)
    monkeypatch.setattr(run, "host_swap_active", lambda: True)
    info = run.setup_cgroups("bakeoff-t", 256, 1.0)
    assert info["backend"] == "cgroup-v2"
    assert info["swap"]["limited"] is False and info["swap"]["host_swap_active"] is True


def test_memory_limit_without_swap_evidence_is_not_comparable():
    r = _fixture()
    assert not [p for p in perf.evidence_problems(r) if "swap" in p]
    for swap in (None, {"limited": False, "host_swap_active": True}, {"limited": False}):
        rr = json.loads(json.dumps(r))
        if swap is None:
            rr["coordinator"]["cgroup"].pop("swap")
        else:
            rr["coordinator"]["cgroup"]["swap"] = swap
        assert [p for p in perf.evidence_problems(rr) if "swap" in p], swap
    rr["coordinator"]["cgroup"]["swap"] = {"limited": False, "host_swap_active": False}
    assert not [p for p in perf.evidence_problems(rr) if "swap" in p]


# ── 4) الجرد: ملفُّ نظامٍ معلنٌ باسمه يبقى نظاماً عبر رابط — والأوزانُ لا تمرّ عبره ────────────────


def _inventory_through(tmp_path, monkeypatch, opened: str, real_target: str) -> dict:
    log = tmp_path / "t.trace"
    log.write_text(f'1 openat(AT_FDCWD, "{opened}", O_RDONLY|O_CLOEXEC) = 3\n', encoding="utf-8")
    realpath = os.path.realpath
    monkeypatch.setattr(
        run.os.path,
        "realpath",
        lambda p, *a, **k: real_target if p == opened else realpath(p, *a, **k),
    )
    return run.file_inventory(log, str(tmp_path / "pinned") + "/", [], [])


def test_declared_system_file_reached_through_a_link_stays_system(tmp_path, monkeypatch):
    inv = _inventory_through(tmp_path, monkeypatch, "/etc/resolv.conf", "/mnt/wsl/resolv.conf")
    assert inv["undeclared"] == [] and inv["counts"]["system"] == 1


def test_weights_behind_a_declared_system_name_are_still_undeclared(tmp_path, monkeypatch):
    weights = tmp_path / "voice.onnx"
    weights.write_bytes(b"onnx")
    inv = _inventory_through(tmp_path, monkeypatch, "/etc/hosts", str(weights))
    assert inv["undeclared"] == [str(weights)]


# ── 5) سجلُّ البيئة لا يُطلق عمليّة (uname -p ⇒ ملفّاتُ coreutils في الجرد) ──────────────────────


def test_environment_record_spawns_no_process(tmp_path, monkeypatch):
    monkeypatch.setattr(platform, "_uname_cache", None, raising=False)

    def spawned(*a, **k):
        raise AssertionError(f"عمليّةٌ فرعيّة من سجلّ البيئة: {a[0] if a else k}")

    monkeypatch.setattr(subprocess, "Popen", spawned)
    corpus = tmp_path / "corpus.tsv"
    corpus.write_text("id\ttext\n", encoding="utf-8")
    rec = worker.environment_record(corpus)
    assert rec["platform"].startswith(f"{os.uname().sysname}-{os.uname().release}")


# ── 6) خيوطُ ORT تتبع --threads ما لم تُعلَن ─────────────────────────────────────────────────────


def test_ort_threads_follow_run_threads_unless_declared(monkeypatch):
    monkeypatch.setenv("BAKEOFF_LIMITS", json.dumps({"threads": 2}))
    assert engines.ort_intra_threads({})[0] == 2
    assert engines.ort_intra_threads({"ort_intra_threads": 3}) == (3, "settings.ort_intra_threads")
    monkeypatch.delenv("BAKEOFF_LIMITS")
    assert engines.ort_intra_threads({})[0] == 1


# ── 7) المنسِّق: مفسّرٌ نسبيّ، ومفسّرٌ غائب، وجردٌ بلا strace ────────────────────────────────────


def _coordinate(tmp_path: Path, *extra: str, cwd: Path | None = None, env=None) -> dict:
    p = subprocess.run(
        [
            sys.executable,
            str(PKG / "run.py"),
            "--engine",
            "fake",
            "--manifest",
            str(_manifest(tmp_path)),
            "--runs-root",
            str(tmp_path / "runs"),
            "--hard-timeout",
            "60",
            *extra,
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert p.stdout.strip(), p.stderr[-2000:]
    summary = json.loads(p.stdout.strip().splitlines()[-1])
    return json.loads((Path(summary["run"]) / "result.json").read_text(encoding="utf-8"))


def test_relative_python_is_resolved_against_the_callers_directory(tmp_path):
    """داخل bwrap يصير مجلّدُ العمل مجلّدَ الحزمة، فـ«env/bin/python» النسبيّ لا يوجد (bwrap: execvp)."""
    (tmp_path / "env" / "bin").mkdir(parents=True)
    (tmp_path / "env" / "bin" / "python").symlink_to(sys.executable)
    r = _coordinate(
        tmp_path,
        "--python",
        "env/bin/python",
        "--no-isolation",
        "--",
        "--concurrency-items",
        "2",
        "--warmup",
        "1",
        cwd=tmp_path,
    )
    interp = r["coordinator"]["sandbox"]["interpreter"]
    assert interp["path"] == str(tmp_path / "env" / "bin" / "python")
    assert interp["path"] in r["coordinator"]["command"]


def test_missing_interpreter_is_a_named_stage(tmp_path):
    r = _coordinate(tmp_path, "--python", "nosuch/bin/python")
    assert (r["harness_status"], r["stage"]) == ("failed", "python_not_found")


def test_inventory_without_strace_is_a_named_stage_not_a_crash(tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    r = _coordinate(
        tmp_path,
        "--inventory",
        "--python",
        sys.executable,
        env=dict(os.environ, PATH=str(empty)),
    )
    assert (r["harness_status"], r["stage"]) == ("failed", "inventory_tool_missing")
