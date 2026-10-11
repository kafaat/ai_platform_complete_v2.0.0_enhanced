"""حياةُ العمليّة في ``tools/tts_bakeoff`` تُحكم بهويّتها وفي فضاء PID المختبِر — لا بقراءة ``/proc/<رقم>`` عمياء.

مراجعةُ المالك على v13: ``child_alive=True`` كان إنذاراً كاذباً — ``/proc`` المركَّب لفضاء PID آخر،
فـ``/proc/172`` عمليّةٌ غيرُ الابن ذي الرقم 172. وأوسعُ من الاختبار: ``asr_screen._kill_group`` ادّعى
``group_gone=True`` من ذلك الـ``/proc``. هذه الحالات حتميّة بلا root ولا namespace (``/proc`` مصطنعة
وترقيعٌ صريح)، فتعمل في CI؛ وتشغيلُ الحزمة تحت ``unshare -p -f`` في ``tools/tts_bakeoff/results/v14/``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PKG = Path(__file__).resolve().parents[1] / "tools" / "tts_bakeoff"
sys.path.insert(0, str(PKG))

import asr_screen  # noqa: E402
import procs  # noqa: E402


def _fake_proc(root: Path, nspid: list[int], entries: dict[int, tuple[str, int, int]]) -> Path:
    """``self/status`` بسطر NSpid، و``<pid>/stat`` بحالةٍ ومجموعةٍ وزمنِ بدء (الحقل 22)."""
    (root / "self").mkdir(parents=True)
    (root / "self" / "status").write_text(
        "Name:\tx\nNSpid:\t" + "\t".join(map(str, nspid)) + "\n", encoding="utf-8"
    )
    for pid, (state, pgrp, start) in entries.items():
        (root / str(pid)).mkdir()
        fields = [state, "1", str(pgrp), str(pgrp)] + ["0"] * 15 + [str(start), "0", "0"]
        (root / str(pid) / "stat").write_text(
            f"{pid} (name with ) paren) " + " ".join(fields), encoding="utf-8"
        )
    return root


def test_proc_of_another_namespace_is_unverifiable_not_alive(tmp_path):
    me, pg = os.getpid(), os.getpgrp()
    other = _fake_proc(tmp_path / "other", [me + 100000], {me: ("R", pg, 5)})
    nested = _fake_proc(tmp_path / "nested", [me + 100000, me], {me: ("R", pg, 5)})
    assert procs.proc_namespace(other)[0] is False
    assert procs.proc_namespace(nested)[0] is False  # فضاءٌ أبٌ: مُدخلان
    assert procs.pid_status(me, 5, other)[0] == "unverifiable"
    assert procs.pid_status(me, 5, nested)[0] == "unverifiable"
    assert procs.starttime(me, other) is None
    assert procs.group_status(pg, other)[0] == "unverifiable"


def test_identity_and_state_when_proc_is_ours(tmp_path):
    me, pg = os.getpid(), os.getpgrp()
    mine = _fake_proc(tmp_path / "mine", [me], {me: ("S", pg, 777)})
    zombie = _fake_proc(tmp_path / "zombie", [me], {me: ("Z", pg, 777)})
    assert procs.proc_namespace(mine)[0] is True
    assert procs.pid_status(me, 777, mine)[0] == "alive"
    assert procs.pid_status(me, 778, mine)[0] == "reused"  # الرقمُ لعمليّةٍ بدأت في زمنٍ آخر
    assert procs.pid_status(me, 777, zombie)[0] == "dead"
    assert procs.starttime(me, mine) == 777


def test_reaped_process_is_gone_without_reading_proc(tmp_path):
    previous = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    try:
        child = os.fork()
        if child == 0:
            os._exit(0)
        os.waitpid(child, 0)
    finally:
        signal.signal(signal.SIGCHLD, previous)
    assert procs.pid_status(child, None, tmp_path / "no-such-proc")[0] == "gone"


def test_probe_times_out_and_kills_the_grandchild_holding_the_pipe(tmp_path):
    """شكلُ bwrap تحت ``/proc`` لفضاءٍ آخر: الأبُ يخرج والحفيدُ يُمسك الأنبوب فيعلق ``capture_output``."""
    pidfile = tmp_path / "grandchild.pid"
    previous = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    adopted = procs.become_subreaper()  # الحفيدُ اليتيم يتبنّاه الاختبار فيُثبَت موتُه بـwaitpid
    try:
        t0 = time.monotonic()
        ok, why = procs.probe(["sh", "-c", f"sleep 30 & echo $! > {pidfile}; exit 0"], timeout=0.5)
        wall = time.monotonic() - t0
        gpid = int(pidfile.read_text(encoding="utf-8"))
        killed_by = None
        for _ in range(200 if adopted else 0):
            pid, status = os.waitpid(gpid, os.WNOHANG)
            if pid:
                killed_by = os.WTERMSIG(status) if os.WIFSIGNALED(status) else None
                break
            time.sleep(0.01)
    finally:
        procs.become_subreaper(False)
        signal.signal(signal.SIGCHLD, previous)
    assert ok is False and "علِق" in why and wall < 5
    if adopted:
        assert killed_by == signal.SIGKILL
    assert procs.pid_status(gpid)[0] in procs.NOT_ALIVE + ("unverifiable",)


def test_bwrap_is_declared_unavailable_when_proc_is_another_namespace(monkeypatch):
    monkeypatch.setattr(procs, "proc_namespace", lambda proc_root=procs.PROC: (False, "مصطنع"))
    ok, why = procs.bwrap_probe(["sh", "-c", "exit 0"])
    assert ok is False and "bwrap لا يُعتمد" in why


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        (("unverifiable", [], "/proc لفضاءٍ آخر"), (None, None, True)),
        (("alive", [4242], "حيّ"), (False, [4242], False)),
    ],
)
def test_kill_group_never_claims_gone_without_proof(monkeypatch, verdict, expected):
    monkeypatch.setattr(asr_screen.procs, "reap_group", lambda pgid: 0)
    monkeypatch.setattr(asr_screen.procs, "group_status", lambda pgid: verdict)
    monkeypatch.setattr(asr_screen.time, "sleep", lambda s: None)
    proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
    info = asr_screen._kill_group(proc)
    assert (info.get("group_gone"), info.get("alive"), "unverifiable" in info) == expected


def test_kill_group_proves_gone_for_a_real_group():
    proc = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], start_new_session=True)
    info = asr_screen._kill_group(proc)
    assert info["group_gone"] in (True, None)  # None فقط حيث يتعذّر الإثبات (فضاءٌ آخر)
    assert info["group_gone"] is not False
