"""صندوقُ ``tools/tts_bakeoff`` مع بيئةٍ افتراضيّة حقيقيّة — عيوبُ تشغيل Kokoro عند المالك على WSL2 (2026-10-06).

الأداةُ المدموجة (``9801d076``) لم تُشغِّل أيَّ محرّكٍ مثبّتٍ في venv تحت bwrap، وما تجاوز ذلك بترقيعٍ محلّيّ
بقي «غيرَ قابلٍ للمقارنة» لأسبابٍ من الأداة نفسها. كلُّ حالةٍ هنا حمراءُ على ``main@77f9f188`` — عدا ضابطٍ
واحد يمرّ على الاثنين (``test_weights_behind_a_declared_system_name_are_still_undeclared``) — وحتميّةٌ بلا root
ولا bwrap ولا cgroup حقيقيّ (مسارٌ مصطنع أو ترقيعٌ صريح)، فتعمل في CI. التشغيلُ الحقيقيّ تحت bwrap في
``selftest.py`` (الحالة v15).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
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
    real.write_text("#!/bin/sh\n", encoding="utf-8")
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
    real.write_text("#!/bin/sh\n", encoding="utf-8")
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
    target.write_text("nameserver 10.255.255.254\n", encoding="utf-8")
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


def test_real_licenses_its_prefix_only_if_it_is_the_actual_target(tmp_path):
    """مراجعةُ Copilot على #1146: ``real`` بلا تحقّقٍ كان يُرخِّص أيَّ مجلّدٍ يكتبه السجلّ."""
    base, venv, py = _venv(tmp_path)
    forged = {"path": str(py), "real": "/srv/private/bin/python"}
    assert perf.interpreter_prefixes(forged) == {str(venv)}
    out = tmp_path / "runs" / "r1"
    assert perf.sandbox_bind_problems(["ro:/srv/private", f"rw:{out}"], "r1", forged)
    genuine = {"path": str(py), "real": str(base / "bin" / "python3.12")}
    assert perf.interpreter_prefixes(genuine) == {str(venv), str(base)}


# ── 3) المبادلة: حدُّ الذاكرة بلا إغلاقها لا يُقاس ───────────────────────────────────────────────


def test_limit_swap_closes_it_when_the_kernel_exposes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "host_swap_active", lambda: True)
    f = tmp_path / "memory.swap.max"
    f.write_text("max\n", encoding="utf-8")
    assert run._limit_swap(f, "0") == {
        "limited": True,
        "file": "memory.swap.max",
        "value": "0",
        "host_swap_active": True,
    }
    assert f.read_text(encoding="utf-8") == "0"
    absent = run._limit_swap(tmp_path / "nope", "0")
    assert absent["limited"] is False and absent["host_swap_active"] is True


def test_v2_group_records_whether_swap_was_closed(tmp_path, monkeypatch):
    """الهرمُ الموحّد المصطنع بلا ``memory.swap.max`` (محاسبةُ المبادلة معطّلة) — يُسجَّل ولا يُدّعى الإغلاق."""
    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "cgroup.controllers").write_text("cpu memory io\n", encoding="utf-8")
    (cg / "cgroup.subtree_control").write_text("cpu memory\n", encoding="utf-8")
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


def test_swap_is_closed_only_by_its_backend_file_and_value():
    """``limited=true`` وحده ليس دليلاً: الملفُّ والقيمةُ لكلّ هرم (مراجعةُ Copilot على #1146)."""
    r = _fixture()
    cg = r["coordinator"]["cgroup"]
    assert cg["backend"] == "cgroup-v1" and cg["swap"]["limited"] is True
    # المضيفُ هنا بلا مبادلة فيُعفى؛ المزوّراتُ تفترضها مفعّلةً كي يُفحص الملفُّ والقيمة وحدهما
    assert perf.swap_closed(cg["swap"], cg)
    for forged in (
        {"limited": True, "host_swap_active": True},
        {**cg["swap"], "value": "9223372036854771712", "host_swap_active": True},
        {**cg["swap"], "file": "memory.swap.max", "value": "0", "host_swap_active": True},
    ):
        rr = json.loads(json.dumps(r))
        rr["coordinator"]["cgroup"]["swap"] = forged
        assert [p for p in perf.evidence_problems(rr) if "swap" in p], forged
    v2 = {"backend": "cgroup-v2", "memory_limit_mb": 256}
    assert perf.swap_closed({"limited": True, "file": "memory.swap.max", "value": "0"}, v2)
    assert not perf.swap_closed({"limited": True, "file": "memory.swap.max", "value": "max"}, v2)


def test_unreadable_proc_swaps_is_unknown_not_absent(tmp_path):
    assert run.host_swap_active(tmp_path / "no-such-swaps") is None
    swaps = tmp_path / "swaps"
    swaps.write_text("Filename Type Size Used Priority\n", encoding="utf-8")
    assert run.host_swap_active(swaps) is False
    r = _fixture()
    r["coordinator"]["cgroup"]["swap"] = {"limited": False, "host_swap_active": None}
    assert [p for p in perf.evidence_problems(r) if "swap" in p]


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
        encoding="utf-8",
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


# ── 8) الإغلاق: ربطاتُ مجلّدات النظام لا تُثبت حدَّ نظام الملفّات (TTS-BAKEOFF-PERF-COMPARABLE-WITHOUT-FS-BOUNDARY-01) ──
#
# مقيسٌ على main@0e5281614: محرّكٌ وهميّ يقرأ نموذجاً غيرَ معلَن تحت /usr/lib في ``--sandbox bwrap`` انتهى
# ``harness_status=ok`` و``performance_comparable=true`` — فـ/usr/lib مربوطٌ كاملاً. ``wide_bwrap_result.json`` سجلٌّ
# حقيقيٌّ بذلك الصندوق (كان ``comparable_result.json`` حتّى v15)؛ و``comparable_result.json`` الآن تشغيلٌ حقيقيٌّ
# بـ``--closure-from`` جردٍ نظيف (selftest v16).


def _wide() -> dict:
    return json.loads((PKG / "fixtures" / "wide_bwrap_result.json").read_text(encoding="utf-8"))


def test_directory_binds_without_an_inventory_closure_are_not_comparable():
    r = _wide()
    binds = r["coordinator"]["sandbox"]["binds"]
    assert "ro:/usr/lib" in binds, "السجلُّ الشاهد يربط مجلّدَ النظام كاملاً"
    problems = perf.evidence_problems(r)
    assert problems, "صندوقٌ يكشف /usr/lib كلَّه قُبل للمقارنة — نموذجٌ غيرُ معلَن تحته يمرّ"
    assert all("closure" in p for p in problems), problems  # السجلُّ كاملٌ عدا الإغلاق
    assert perf.why_not_comparable(r)


def _closure_record() -> dict:
    return _fixture()


def _redigest(r: dict) -> dict:
    closure = r["coordinator"]["sandbox"]["closure"]
    closure["sha256"] = perf.closure_digest(closure)
    return r


def test_every_read_bind_of_a_closure_run_is_a_closure_file():
    r = _closure_record()
    sandbox = r["coordinator"]["sandbox"]
    assert perf.closure_problems(sandbox, r["run_id"]) == []
    ros = [b[3:] for b in sandbox["binds"] if b.startswith("ro:")]
    files = sandbox["closure"]["files"]
    assert ros and all(p in files or p == "/sys/fs/cgroup" or p.endswith(".pinned") for p in ros)
    for extra in ("ro:/usr/lib", "ro:/usr/share/voice.onnx", "link:/x->/usr/lib", "ro:/"):
        rr = json.loads(json.dumps(r))
        rr["coordinator"]["sandbox"]["binds"].append(extra)
        assert [p for p in perf.evidence_problems(rr) if "sandbox" in p], extra


def test_a_closure_entry_that_is_a_directory_or_unhashed_is_refused():
    for path, entry in (
        ("/usr/lib", {"sha256": "0" * 64, "access": ["read"]}),
        ("/usr/lib/x/voice.onnx", {"access": ["read"]}),
        ("/srv/models", {"sha256": "0" * 64, "kind": "directory"}),
    ):
        r = _closure_record()
        r["coordinator"]["sandbox"]["closure"]["files"][path] = entry
        r["coordinator"]["sandbox"]["binds"].insert(0, f"ro:{path}")
        _redigest(r)
        problems = perf.closure_problems(r["coordinator"]["sandbox"], r["run_id"])
        assert any(path in p for p in problems), (path, problems)


def test_the_closure_digest_binds_its_content():
    r = _closure_record()
    closure = r["coordinator"]["sandbox"]["closure"]
    closure["files"]["/usr/lib/extra.so"] = {"sha256": "1" * 64, "access": ["read"]}
    r["coordinator"]["sandbox"]["binds"].insert(0, "ro:/usr/lib/extra.so")
    assert any("بصمة" in p for p in perf.closure_problems(r["coordinator"]["sandbox"], r["run_id"]))
    assert perf.why_not_comparable(r)
    rr = _redigest(json.loads(json.dumps(r)))
    rr["coordinator"]["sandbox"]["integrity_after"] = {"changed": ["/usr/lib/extra.so"]}
    assert any("integrity_after" in p for p in perf.evidence_problems(rr))


def _inventory_run(tmp_path: Path, closure_file: Path, **override) -> tuple[Path, dict, str]:
    interp = {"path": "/venv/bin/python", "real": "/usr/bin/python3.11"}
    manifest_sha = run.manifest_digest("fake", {"files": {}, "settings": {"mode": "ok"}})
    closure = {
        "version": 1,
        "files": {
            str(closure_file): {"sha256": worker.sha256_file(closure_file), "access": ["read"]}
        },
        "dirs": [],
        "symlinks": {},
        "loaders": {},
        "stat_only": [],
        "skipped": {"virtual": 0, "run_private": 0},
        "problems": [],
        "engine": "fake",
        "interpreter": interp,
        "manifest_sha256": manifest_sha,
        "inventory_run": "inv",
    }
    closure.update(override.pop("closure", {}))
    closure["sha256"] = perf.closure_digest(closure)
    record = {
        "run_id": "inv",
        "engine": "fake",
        "harness_status": "ok",
        "coordinator": {"sandbox": {"kind": "bwrap", "inventory": "strace-inside-sandbox"}},
        "file_inventory": {"undeclared": [], "closure": closure},
    }
    for key, value in override.items():
        record[key] = value
    d = tmp_path / f"inv-{len(list(tmp_path.iterdir()))}"
    d.mkdir()
    (d / "result.json").write_text(json.dumps(record), encoding="utf-8")
    return d, interp, manifest_sha


def test_closure_from_refuses_an_unclean_foreign_or_stale_inventory(tmp_path):
    lib = tmp_path / "lib.so"
    lib.write_bytes(b"\x7fELF-lib")
    d, interp, msha = _inventory_run(tmp_path, lib)
    closure, stage, why = run.load_closure(d, "fake", interp, msha)
    assert stage is None and list(closure["files"]) == [str(lib)], why
    dirty, _, _ = _inventory_run(tmp_path, lib)
    rec = json.loads((dirty / "result.json").read_text(encoding="utf-8"))
    rec["file_inventory"]["undeclared"] = ["/usr/lib/x/voice.onnx"]
    (dirty / "result.json").write_text(json.dumps(rec), encoding="utf-8")
    assert run.load_closure(dirty, "fake", interp, msha)[1] == "closure_rejected"
    for name, override in {
        "failed": dict(harness_status="failed"),
        "outside_sandbox": dict(coordinator={"sandbox": {"kind": "unshare"}}),
        "closure_problems": dict(closure={"problems": ["x"]}),
    }.items():
        dd, _, _ = _inventory_run(tmp_path, lib, **override)
        assert run.load_closure(dd, "fake", interp, msha)[1] == "closure_rejected", name
    assert run.load_closure(d, "kokoro", interp, msha)[1] == "closure_rejected"
    assert run.load_closure(d, "fake", {**interp, "path": "/other"}, msha)[1] == "closure_rejected"
    assert run.load_closure(d, "fake", interp, "f" * 64)[1] == "closure_rejected"
    rec = json.loads((d / "result.json").read_text(encoding="utf-8"))
    rec["file_inventory"]["closure"]["files"]["/usr/lib/more.so"] = {"sha256": "0" * 64}
    (d / "result.json").write_text(json.dumps(rec), encoding="utf-8")
    assert run.load_closure(d, "fake", interp, msha)[1] == "closure_rejected"  # بصمةٌ لا تطابق
    d2, _, _ = _inventory_run(tmp_path, lib)
    lib.write_bytes(b"\x7fELF-changed")
    assert run.load_closure(d2, "fake", interp, msha)[1] == "closure_stale"


@pytest.fixture
def sandbox_tmpfs_path():
    """Place this fixture under the sandbox tmpfs, independent of host TMPDIR."""
    with tempfile.TemporaryDirectory(prefix="tts-closure-", dir=run.SANDBOX_TMPFS) as directory:
        yield Path(directory)


def test_the_inventory_trace_becomes_a_closure_of_files_links_and_loaders(sandbox_tmpfs_path):
    """سجلُّ ``strace -ff -y`` داخل الصندوق ⇒ ملفّاتٌ ببصماتها، وروابطُ عُبرت، ومُحمِّلُ التنفيذيّ (لا يظهر في strace)."""
    tmp_path = sandbox_tmpfs_path
    real_dir = tmp_path / "lib"
    real_dir.mkdir()
    target = real_dir / "libvoice.so.1.2"
    target.write_bytes(b"lib")
    (real_dir / "libvoice.so.1").symlink_to("libvoice.so.1.2")
    data = tmp_path / "data.tsv"
    data.write_text("x\n", encoding="utf-8")
    private = tmp_path / "run1"
    private.mkdir()
    exe = os.path.realpath(sys.executable)
    log = tmp_path / "t.1"
    log.write_text(
        "\n".join(
            [
                f'execve("{exe}", ["python"], 0x7ffe /* 3 vars */) = 0',
                f'openat(AT_FDCWD<{real_dir}>, "libvoice.so.1", O_RDONLY|O_CLOEXEC) = 3<{target}>',
                f'newfstatat(AT_FDCWD<{tmp_path}>, "data.tsv", {{st_mode=S_IFREG|0644}}, 0) = 0',
                f'newfstatat(AT_FDCWD</>, "{real_dir}", {{st_mode=S_IFDIR|0755}}, 0) = 0',
                f'openat(AT_FDCWD</>, "{private}/result.json", O_WRONLY|O_CREAT, 0644) = 4<{private}/result.json>',
                'openat(AT_FDCWD</>, "/proc/self/status", O_RDONLY) = 5</proc/1/status>',
                'openat(AT_FDCWD</>, "/usr/lib/missing.so", O_RDONLY) = -1 ENOENT (No such file)',
                "newfstatat(3<" + str(target) + '>, "", {st_mode=S_IFREG}, AT_EMPTY_PATH) = 0',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    events, unresolved = run.trace_events([log])
    assert unresolved == []
    # tmp_path تحت /tmp: في الصندوق tmpfs، فلا يُرى منه إلّا ما رُبط — وهنا رُبط (كمجلّد تشغيلٍ تحت /tmp)
    assert run.build_closure(events, unresolved, [str(private) + "/"])["files"].keys() == {exe} | {
        f for f in run.build_closure(events, [], [])["files"] if not f.startswith(str(tmp_path))
    }
    closure = run.build_closure(events, unresolved, [str(private) + "/"], [str(tmp_path)])
    assert closure["problems"] == [], closure["problems"]
    assert set(closure["files"]) >= {str(target), str(data), exe}
    assert closure["files"][str(data)]["access"] == ["stat"] and str(data) in closure["stat_only"]
    assert closure["files"][str(target)]["sha256"] == worker.sha256_file(target)
    assert closure["symlinks"][str(real_dir / "libvoice.so.1")] == "libvoice.so.1.2"
    loader = closure["loaders"].get(exe)
    assert loader and "ld-linux" in loader, closure["loaders"]
    assert any(f.endswith(os.path.basename(loader)) or "ld-linux" in f for f in closure["files"])
    assert str(real_dir) in closure["dirs"]
    assert not [f for f in closure["files"] if os.path.isdir(f)]
    assert not [f for f in closure["files"] if f.startswith(("/proc/", str(private)))]
    assert closure["skipped"]["run_private"] == 1 and closure["skipped"]["virtual"] == 1
