"""حياةُ العمليّات بلا إنذارٍ كاذب: هويّةُ العمليّة **وفضاءُ PID** قبل الحكم بأنّها باقية.

رقمُ PID لا يكفي وحده:
- **الفضاء:** ``/proc`` المركَّب قد يخصّ فضاءَ PID آخر (``unshare -p -f`` بلا ``--mount-proc``، أو حاويةٌ متداخلة).
  حينها ``/proc/172`` عمليّةٌ أخرى غيرُ ابننا ذي الرقم 172 في فضائنا (مراجعةُ المالك على v13: الابنُ ``sleep``
  برقم 172 و``/proc/172`` يشير إلى غيره ⇒ ``child_alive=True`` كاذب). يُكشف بسطر ``NSpid`` في
  ``/proc/self/status``: مُدخلٌ واحدٌ يساوي ``getpid()`` ⇔ ``/proc`` لفضائنا.
- **الهويّة:** الرقمُ يُعاد استعمالُه؛ زمنُ البدء (الحقل 22 من ``stat``) يميّز العمليّةَ نفسها من وارثة رقمها.

الأحكام: ``gone`` (لا عمليّةَ بهذا الرقم في فضائنا: ``kill(pid, 0)`` ⇒ ESRCH — قاطعٌ بلا ``/proc``) ·
``dead`` (زومبي/X: ماتت ولم تُحصَد) · ``reused`` (الرقمُ لعمليّةٍ أخرى بدأت في زمنٍ آخر) · ``alive`` (الفضاءُ
مُتحقَّق والهويّةُ مطابِقة أو لم تُسجَّل) · ``unverifiable`` (الرقمُ موجودٌ في فضائنا و``/proc`` لا يعرضه) —
وهذا الأخير **ليس** «حيّة»: من يستهلكه يُسجّله محجوباً (BLOCKED) لا فشلاً.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
from pathlib import Path

PROC = Path("/proc")
PR_SET_CHILD_SUBREAPER = 36
NOT_ALIVE = ("gone", "dead", "reused")


def proc_namespace(proc_root: Path = PROC) -> tuple[bool, str]:
    """هل ``proc_root`` يعرض فضاءَ PID هذه العمليّة؟ ⇒ (نعم/لا، الدليل)."""
    me = os.getpid()
    try:
        for line in (proc_root / "self" / "status").read_text().splitlines():
            if line.startswith("NSpid:"):
                ns = [int(x) for x in line.split()[1:]]
                return ns == [me], f"NSpid={ns} getpid={me}"
    except (OSError, ValueError):
        pass
    try:  # نواةٌ أقدم من 4.1 بلا NSpid: رابطُ self يُترجَم في فضاء /proc
        seen = int(os.readlink(proc_root / "self"))
    except (OSError, ValueError) as exc:
        return False, f"{proc_root}/self غيرُ مقروء: {type(exc).__name__}"
    return seen == me, f"{proc_root}/self={seen} getpid={me}"


def _stat_fields(pid: int, proc_root: Path = PROC) -> list[str] | None:
    try:
        return (proc_root / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None


def starttime(pid: int, proc_root: Path = PROC) -> int | None:
    """زمنُ بدء العمليّة (نبضاتٌ منذ الإقلاع) — هويّتُها؛ ``None`` إن تعذّر إثباتُ أنّ ``/proc`` لفضائنا."""
    if not proc_namespace(proc_root)[0]:
        return None
    fields = _stat_fields(pid, proc_root)
    return int(fields[19]) if fields and len(fields) > 19 else None


def pid_status(pid: int, start: int | None = None, proc_root: Path = PROC) -> tuple[str, str]:
    """حالُ العمليّة ``pid`` (رقمُها في **فضائنا**) ⇒ (الحكم، الدليل). ``start``: زمنُ بدئها المسجَّل عند إنشائها."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "gone", "kill(pid, 0): ESRCH في فضاء PID هذه العمليّة"
    except PermissionError:
        pass  # موجودةٌ لمالكٍ آخر
    ours, why = proc_namespace(proc_root)
    if not ours:
        return (
            "unverifiable",
            f"الرقمُ موجودٌ في فضائنا و{proc_root} يعرض فضاءً آخر ({why}) — لا يُقرأ حالُه ولا هويّتُه",
        )
    fields = _stat_fields(pid, proc_root)
    if fields is None:
        return "gone", "زالت بين الإشارة والقراءة"
    if fields[0] in ("Z", "X"):
        return "dead", f"state={fields[0]}"
    if start is not None and len(fields) > 19 and int(fields[19]) != start:
        return "reused", f"starttime={fields[19]} ≠ المسجَّل {start}"
    return "alive", f"state={fields[0]}" + (
        " starttime مطابق" if start is not None else " (بلا هويّةٍ مسجَّلة)"
    )


def become_subreaper(on: bool = True) -> bool:
    """تتبنّى هذه العمليّةُ أحفادَها الأيتام فتحصدهم هي (لا PID 1 الذي قد لا يحصد) — Linux ≥ 3.4. ``on=False`` يُلغيه."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.prctl(PR_SET_CHILD_SUBREAPER, int(on), 0, 0, 0) == 0
    except (OSError, AttributeError):
        return False


def reap_group(pgid: int) -> int:
    """يحصد أبناءَنا **من هذه المجموعة وحدها** الذين ماتوا — لا يمسّ أبناءً آخرين (``Popen`` يحصد أبناءه)."""
    reaped = 0
    while True:
        try:
            if os.waitid(os.P_PGID, pgid, os.WEXITED | os.WNOHANG) is None:
                return reaped
        except ChildProcessError:
            return reaped
        reaped += 1


def group_status(pgid: int, proc_root: Path = PROC) -> tuple[str, list[int], str]:
    """حالُ مجموعة العمليّات ``pgid`` في فضائنا ⇒ (gone/alive/unverifiable، الأحياء، الدليل)."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return "gone", [], "killpg(pgid, 0): ESRCH في فضاء PID هذه العمليّة"
    except PermissionError:
        pass
    ours, why = proc_namespace(proc_root)
    if not ours:
        return (
            "unverifiable",
            [],
            f"المجموعةُ تقبل الإشارة (قد يكون أعضاؤها زومبي لم يُحصَدوا) و{proc_root} لفضاءٍ آخر ({why})",
        )
    alive = live_in_group(pgid, proc_root)
    return (
        ("alive" if alive else "gone"),
        alive,
        f"{proc_root} لفضائنا ({why}): الأحياء غيرُ الزومبي {alive}",
    )


def live_in_group(pgid: int, proc_root: Path = PROC) -> list[int]:
    """أعضاءُ المجموعة **الأحياء** من ``/proc`` — الزومبي (Z) ميّتٌ لم يُحصَد بعد: في حاوياتٍ لا يحصد فيها PID 1
    الأيتام، ``kill(pid, 0)`` ينجح على الزومبي فيُعدّ حيّاً خطأً. **لا يُستدعى إلّا بعد ``proc_namespace``**: في فضاءٍ
    آخر أرقامُ ``pgrp`` في ``stat`` ليست أرقامَنا."""
    alive = []
    for stat in proc_root.glob("[0-9]*/stat"):
        try:
            fields = stat.read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue  # عمليّةٌ زالت بين السرد والقراءة: ليست حيّة
        if fields[0] != "Z" and int(fields[2]) == pgid:
            alive.append(int(stat.parent.name))
    return alive


def probe(argv: list[str], timeout: float = 15.0) -> tuple[bool, str]:
    """يُشغّل مسبارَ قدرةٍ (``unshare``/``bwrap``) **بمهلةٍ وبمجموعة عمليّاتٍ خاصّة** ⇒ (نجح؟، السبب). مقيسٌ: تحت
    ``unshare -p -f`` بلا ``--mount-proc`` يفتح أبُ bwrap /proc/<رقم ابنه> فيجد عمليّةً أخرى فيخرج، ويبقى الابنُ ينتظر
    eventfd إلى الأبد ممسكاً بالأنبوب — فيعلق ``subprocess.run(capture_output=True)`` بلا مهلة. القتلُ للمجموعة كلّها."""
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    try:
        _, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        return False, f"علِق أكثر من {timeout}s فقُتلت مجموعتُه ({proc_namespace()[1]})"
    return proc.returncode == 0, (err.strip()[-80:] or "ok") if proc.returncode else "ok"


def bwrap_probe(argv: list[str], timeout: float = 15.0) -> tuple[bool, str]:
    """bwrap يتطلّب ``/proc`` لفضاء PID المُشغِّل: أبوه يفتح ``/proc/<رقم ابنه>``، وفي فضاءٍ آخر يجد عمليّةً أخرى. مقيسٌ
    تحت ``unshare -p -f``: ينجح أو يعلق بحسب الأرقام التي يصادفها — فيُعلَن غيرَ متاح هناك حتميّاً، لا مرّةً ومرّة."""
    ours, why = proc_namespace()
    if not ours:
        return False, f"/proc لفضاء PID آخر ({why}) — bwrap لا يُعتمد هنا"
    return probe(argv, timeout)
