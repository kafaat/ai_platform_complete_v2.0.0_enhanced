"""المُنسِّق: يشغّل ``worker.py`` لمحرّكٍ واحد داخل عزلٍ على مستوى النظام، بحدودٍ ومهلة.

    python3 run.py --engine piper --python venv_piper/bin/python --manifest models.json \\
        --mem-mb 2048 --cpus 2 --hard-timeout 1800

• **الشبكة:** ``unshare -n`` يضع العامل في فضاء شبكةٍ لا يحوي إلّا loopback معطّلاً — يمنع
  المكتباتِ الأصليّة أيضاً، لا بايثون وحدها. ضابطٌ سلبيّ هنا (خارج العزل يصل)، وإيجابيّ داخل
  العامل (داخله لا يصل). إن تعذّر ``unshare`` (لا root أو لا دعم) فالاختبار **BLOCKED** ولا يُدّعى عزل.
• **الموارد:** cgroup v1 (``memory.limit_in_bytes`` و``cpu.cfs_quota_us``) أو v2 (``memory.max``
  و``cpu.max``) — الهرمُ المُركَّب فعلاً يُكتشَف لا يُفترض + ``taskset`` للأنوية.
  تُسجَّل الحدود وذروةُ الذاكرة الفعليّة للمجموعة. تعذُّرها يُسجَّل صراحةً لا يُفترض.
• **المهلة:** العاملُ في مجموعة عمليّاتٍ مستقلّة؛ عند ``--hard-timeout`` تُقتل المجموعة كلُّها،
  ويبقى ``result.json`` الجزئيّ (العامل يكتبه بعد كلّ مرحلة).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import uuid
from pathlib import Path

import procs

HERE = Path(__file__).resolve().parent
CG = Path("/sys/fs/cgroup")


CONTROL_HOST = os.environ.get("BAKEOFF_CONTROL_HOST", "pypi.org")


def negative_control() -> dict:
    """خارج العزل يجب أن **يصل** الاتّصال المباشر إلى هدف الضابط — بالاسم **وبالعنوان** — وإلّا ففشلُ
    الضابط الإيجابيّ داخل العزل لا يُثبت شيئاً، ويُحكم على التشغيل بالفشل (``negative_control_failed``).
    العنوانُ يُمرَّر للعامل ليُجرَّب داخل العزل بلا DNS."""
    out = {"target": f"{CONTROL_HOST}:443", "reached": False, "ip": None}
    try:
        socket.create_connection((CONTROL_HOST, 443), timeout=10).close()
        ip = socket.getaddrinfo(CONTROL_HOST, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        socket.create_connection((ip, 443), timeout=10).close()
        out.update(reached=True, ip=ip)
    except OSError as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


# bwrap: جذرٌ **فارغ**، ولا يُرى إلّا ما رُبط صراحةً. /usr/share و/usr/local و/home و/var غيرُ مرئيّة؛
# ملفّاتُ الشبكة في /etc تُربط عمداً كي لا يُنسب حجبُ DNS إلى غيابها (والمسبارُ بالعنوان يتجاوز DNS أصلاً).
BWRAP_SYSTEM_RO = (
    "/usr/lib",
    "/usr/lib64",
    "/usr/bin",
    "/etc/ld.so.cache",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/nsswitch.conf",
    "/etc/ssl",
    "/sys/fs/cgroup",
)


def bwrap_command(worker: list[str], ro: list[str], rw: list[str]) -> tuple[list[str], list[str]]:
    """يبني أمرَ bwrap: الربطُ للقراءة فقط لكلّ مسارٍ معلن، والكتابةُ لمجلّد الناتج وحده."""
    args, binds = (
        [
            "bwrap",
            "--die-with-parent",
            "--new-session",
            "--unshare-net",
            "--unshare-ipc",
            "--unshare-uts",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--symlink",
            "usr/bin",
            "/bin",
        ],
        [],
    )
    ro = list(dict.fromkeys(ro))
    # المجلّداتُ التي ستُربط فعلاً (مجلّدٌ هو رابطٌ يُنشأ رابطاً لا ربطاً، فلا يغطّي ما تحته)
    dirs = [r.rstrip("/") for r in ro if os.path.isdir(r) and not os.path.islink(r)]

    def under_dir(p: str) -> bool:
        return any(p != d and p.startswith(d + "/") for d in dirs)

    for path in ro:
        if not os.path.exists(path):
            continue
        if under_dir(path):
            # مرئيٌّ عبر مجلّدٍ مربوطٍ أعلاه. ربطُه ثانيةً يطلب نقطةَ تركيبٍ **داخل** ربطٍ للقراءة فقط فيفشل
            # bwrap بـ«Can't create file» في كلّ بيئةٍ افتراضيّة (venv/bin/python رابطٌ تحت sys.prefix
            # المربوط) — قياسُ المالك على WSL2، 2026-10-06؛ والاختبارُ الذاتيّ لم يره لأنّه يعمل بـ/usr/bin/python3.
            continue
        if os.path.islink(path):
            real = os.path.realpath(path)
            if not (under_dir(real) or real in dirs):
                # هدفُ الرابط خارج كلّ ربطٍ معلن (/etc/resolv.conf → /mnt/wsl/resolv.conf على WSL، أو
                # /run/systemd/resolve/… على systemd): إنشاؤه يسمّي هدفاً غيرَ معلن ولا يُوصِل إليه. يُترك،
                # ويُسجَّل تركُه — لا ربطَ لما لم يُعلَن، ولا إخفاءَ أنّه تُرك.
                binds.append(f"skip:{path}->{real}")
                continue
            # مفسّرٌ عبر رابطٍ خارج المربوط (/usr/local/bin/python3 → /usr/bin/python3.11): يُنشأ الرابطُ وحده
            # داخل الصندوق، لا يُربط مجلّدُه كلّه.
            args += ["--dir", os.path.dirname(path), "--symlink", real, path]
            binds.append(f"link:{path}->{real}")
            continue
        args += ["--ro-bind", path, path]
        binds.append(f"ro:{path}")
    for path in dict.fromkeys(rw):
        args += ["--bind", path, path]
        binds.append(f"rw:{path}")
    return args + ["--chdir", str(HERE), "--", *worker], binds


def link_chain(path: str) -> list[str]:
    """كلُّ قفزةٍ من المفسّر إلى ملفّه الحقيقيّ. ``python -m venv`` يكتب ``venv/bin/python → python3 →
    /usr/local/bin/python3 → /usr/bin/python3.11``: الطرفان وحدهما لا يكفيان، فالقفزةُ الوسطى (/usr/local/bin)
    غائبةٌ داخل الصندوق ⇒ ``bwrap: execvp … No such file``. ما وقع منها تحت مجلّدٍ مربوط يُتخطّى في
    ``bwrap_command``، وما سواه يُنشأ رابطاً إلى هدفه."""
    chain, seen = [path], {path}
    while os.path.islink(chain[-1]) and len(chain) < 40:
        nxt = os.path.normpath(os.path.join(os.path.dirname(chain[-1]), os.readlink(chain[-1])))
        if nxt in seen:
            break
        chain.append(nxt)
        seen.add(nxt)
    return chain


def cgroup_hierarchy() -> str | None:
    """أيُّ هرمٍ **مُركَّبٌ فعلاً**: ``v1`` إن كان متحكّما الذاكرة والمعالج هرمَين منفصلَين بملفّاتهما،
    و``v2`` إن وُجد الهرمُ الموحّد، و``None`` إن لم يوجد أيٌّ منهما.

    الترتيبُ يفضّل v1 حيث وُجد فلا يتغيّر ما قِيس عليه سابقاً؛ والمضيفُ الهجين (v1 للذاكرة
    والمعالج مع ``unified`` للباقي) يبقى v1. وWSL2 وUbuntu 22.04 وما بعدها v2 فقط.
    """
    if (CG / "memory" / "memory.limit_in_bytes").exists() and (
        CG / "cpu" / "cpu.cfs_period_us"
    ).exists():
        return "v1"
    if (CG / "cgroup.controllers").exists():
        return "v2"
    return None


def _setup_v2(name: str, mem_mb: int, cpus: float, created: list[str]) -> dict:
    """v2: مجموعةٌ واحدة بملفَّي ``memory.max`` و``cpu.max``.

    المتحكّمان يجب أن يكونا مُفعَّلَين في ``cgroup.subtree_control`` للجذر وإلّا لم يوجد الملفّان
    في الابن أصلاً. والجذرُ **مستثنىً** من قاعدة «لا عمليّاتٍ داخليّة»، فتفعيلُهما فيه لا يتطلّب
    نقلَ عمليّات المضيف. وما فعّلناه **لا يُعاد تعطيلُه** في التنظيف: مجموعاتٌ أخرى قد تكون
    نشأت تحته. الكتابةُ إلى ملفَّي الحدّ هي الشاهد: إن لم يَسرِ المتحكّمُ فالملفُّ غائبٌ وتفشل.
    """
    available = (CG / "cgroup.controllers").read_text().split()
    missing = [c for c in ("memory", "cpu") if c not in available]
    if missing:
        raise OSError(f"متحكّماتٌ غائبةٌ عن الهرم الموحّد: {missing} (المتوفّر {available})")
    enabled = (CG / "cgroup.subtree_control").read_text().split()
    turned_on = [c for c in ("memory", "cpu") if c not in enabled]
    if turned_on:
        (CG / "cgroup.subtree_control").write_text(" ".join(f"+{c}" for c in turned_on))
    group = CG / name
    group.mkdir()
    created.append(str(group))
    (group / "memory.max").write_text(str(mem_mb * 1024 * 1024))
    (group / "cpu.max").write_text(f"{int(cpus * 100000)} 100000")
    return {
        "backend": "cgroup-v2",
        "paths": created,
        "controllers_enabled_by_us": turned_on,
        "swap": _limit_swap(group / "memory.swap.max", "0"),
    }


def host_swap_active(swaps: Path = Path("/proc/swaps")) -> bool | None:
    """هل في المضيف مبادلةٌ مفعّلة؟ (/proc/swaps: سطرُ العناوين ثمّ سطرٌ لكلّ جهاز). تعذُّرُ القراءة ⇒ ``None``
    (مجهول) لا ``False``: «لا مبادلة» دليلٌ يُعفي من إغلاقها، فلا يُستنتج من ملفٍّ لم يُقرأ (مراجعةُ Copilot على #1146)."""
    try:
        return len(swaps.read_text(encoding="utf-8").strip().splitlines()) > 1
    except OSError:
        return None


def _limit_swap(path: Path, value: str) -> dict:
    """``memory.max`` (v2) و``memory.limit_in_bytes`` (v1) يحدّان الذاكرةَ **لا المبادلة**: مع مبادلةٍ مفعّلة
    تُبادَل العمليّةُ بدل أن تُقتل، فلا يقع OOM ولا يُقاس الحدّ (قياسُ المالك على WSL2 بمبادلة: peak=256MB
    وoom=0، 2026-10-06). يُغلق الملفُّ المبادلةَ (v2: ``memory.swap.max=0`` · v1: ``memsw`` = حدّ الذاكرة).
    غيابُه (محاسبةُ المبادلة معطّلة في النواة) يُسجَّل كما هو مع حالة المبادلة في المضيف، ولا يُدّعى الإغلاق."""
    active = host_swap_active()
    if not path.exists():
        return {"limited": False, "file": path.name, "host_swap_active": active, "why": "absent"}
    path.write_text(value)
    return {"limited": True, "file": path.name, "value": value, "host_swap_active": active}


def setup_cgroups(name: str, mem_mb: int, cpus: float) -> dict:
    """يُنشئ حدودَ الذاكرة والمعالج على الهرم المُركَّب (v1 مجموعتان · v2 مجموعةٌ واحدة). كلُّ مسارٍ
    يُسجَّل **لحظةَ إنشائه**، فإن فشلت خطوةٌ لاحقة (حصّةٌ مرفوضة مثلاً) أُزيل ما أُنشئ فوراً
    وسُجِّل — لا تبقى مجموعةُ ذاكرةٍ يتيمة خارج التنظيف."""
    info = {"backend": None, "memory_limit_mb": mem_mb, "cpu_quota": cpus, "paths": []}
    created: list[str] = []
    try:
        hierarchy = cgroup_hierarchy()
        if hierarchy == "v1":
            mem, cpu = CG / "memory" / name, CG / "cpu" / name
            mem.mkdir()
            created.append(str(mem))
            (mem / "memory.limit_in_bytes").write_text(str(mem_mb * 1024 * 1024))
            # memsw = الذاكرة + المبادلة، فمساواتُه بحدّ الذاكرة تمنع المبادلة (ويُكتب بعده: لا يقلّ عنه)
            swap = _limit_swap(mem / "memory.memsw.limit_in_bytes", str(mem_mb * 1024 * 1024))
            cpu.mkdir()
            created.append(str(cpu))
            (cpu / "cpu.cfs_period_us").write_text("100000")
            (cpu / "cpu.cfs_quota_us").write_text(str(int(cpus * 100000)))
            info.update(backend="cgroup-v1", paths=created, swap=swap)
        elif hierarchy == "v2":
            info.update(_setup_v2(name, mem_mb, cpus, created))
        else:
            raise OSError(f"لا هرمَ cgroup مُركَّباً تحت {CG} (لا v1 ولا v2)")
    except OSError as exc:
        partial = {"paths": created}
        teardown_cgroups(partial)
        info.update(
            backend="UNAVAILABLE",
            error=f"{type(exc).__name__}: {exc}",
            partial_cleanup={"created": created, "leaked": partial.get("teardown_leaked", [])},
        )
    return info


def teardown_cgroups(info: dict) -> None:
    """يُزيل المجموعة بعد أن تفرغ — عمليّةٌ مقتولةٌ قد تبقى لحظاتٍ قيد الخروج فيفشل rmdir. يُسجَّل ما بقي."""
    import time

    for path in info.get("paths", []):
        for _ in range(50):  # حتّى 5 ثوانٍ
            try:
                os.rmdir(path)
                break
            except OSError:
                time.sleep(0.1)
        else:
            info.setdefault("teardown_leaked", []).append(path)


def _stats_v2(group: Path) -> dict:
    """ذروةُ الذاكرة من ``memory.peak`` (نواة 5.19+). غيابُها يُعلَن ولا يُستبدل بـ``memory.current``
    (قراءةٌ لحظيّةٌ لا ذروة) — وبوّابةُ ``perf.py`` ترفض السجلَّ بلا ذروةٍ موجبة. وأحداثُ الحدّ
    وOOM من ``memory.events`` (``max`` يقابل ``failcnt`` في v1)، والتباطؤُ من ``cpu.stat``
    بوحدة ``throttled_usec`` لا ``throttled_time`` النانوثانويّة."""
    out: dict = {}
    peak = group / "memory.peak"
    if peak.exists():
        out["memory_peak_mb"] = round(int(peak.read_text()) / 2**20, 1)
    else:
        out["memory_peak_unavailable"] = (
            "memory.peak غائب (نواةٌ أقدم من 5.19) — لا يُستبدل بـmemory.current"
        )
    events = dict(ln.split() for ln in (group / "memory.events").read_text().splitlines())
    out["memory_failcnt"] = int(events.get("max", 0))
    out["oom_kill_events"] = int(events.get("oom_kill", 0))
    cpu_stat = dict(ln.split() for ln in (group / "cpu.stat").read_text().splitlines())
    periods, throttled = (
        int(cpu_stat.get("nr_periods", 0)),
        int(cpu_stat.get("nr_throttled", 0)),
    )
    out.update(
        cpu_periods=periods,
        cpu_throttled_periods=throttled,
        cpu_throttled_ratio=round(throttled / periods, 3) if periods else 0.0,
        cpu_throttled_s=round(int(cpu_stat.get("throttled_usec", 0)) / 1e6, 3),
    )
    return out


def cgroup_stats(info: dict) -> dict:
    """تُقرأ **قبل** إزالة المجموعة: ذروةُ الذاكرة، وأحداثُ OOM، والتباطؤُ بسبب الحصّة."""
    version = {"cgroup-v1": "v1", "cgroup-v2": "v2"}.get(info.get("backend"))
    stats: dict = {"cgroup_version": version if info.get("paths") else None}
    if not info.get("paths") or version is None:
        return stats
    if version == "v2":
        try:
            stats.update(_stats_v2(Path(info["paths"][0])))
        except (OSError, ValueError) as exc:
            stats["error"] = f"{type(exc).__name__}: {exc}"
        return stats
    mem, cpu = Path(info["paths"][0]), Path(info["paths"][1])
    try:
        stats["memory_peak_mb"] = round(
            int((mem / "memory.max_usage_in_bytes").read_text()) / 2**20, 1
        )
        stats["memory_failcnt"] = int((mem / "memory.failcnt").read_text())
        oom = (mem / "memory.oom_control").read_text()
        stats["oom_kill_events"] = next(
            (int(ln.split()[1]) for ln in oom.splitlines() if ln.startswith("oom_kill ")), 0
        )
        cpu_stat = dict(ln.split() for ln in (cpu / "cpu.stat").read_text().splitlines())
        periods, throttled = (
            int(cpu_stat.get("nr_periods", 0)),
            int(cpu_stat.get("nr_throttled", 0)),
        )
        stats.update(
            cpu_periods=periods,
            cpu_throttled_periods=throttled,
            cpu_throttled_ratio=round(throttled / periods, 3) if periods else 0.0,
            cpu_throttled_s=round(int(cpu_stat.get("throttled_time", 0)) / 1e9, 3),
        )
    except (OSError, ValueError) as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
    return stats


# بيئةُ العامل قائمةُ سماحٍ معرَّفةٌ مرّةً واحدة في procs.py — يستعملها المنسّقُ هنا وعمّالُ ASR في asr_screen.py.
WORKER_ENV_ALLOW = procs.WORKER_ENV_ALLOW
worker_env = procs.worker_env


def kill_everything(
    proc: subprocess.Popen, info: dict, identities: dict | None = None
) -> list[int]:
    """يقتل مجموعةَ العمليّات **وكلَّ** عمليّةٍ في المجموعة (يلحق الأبناءَ الذين غيّروا مجموعتهم). ``identities``
    يُملأ بزمن بدء كلِّ مقتولٍ **قبل** قتله (هويّتُه، أو None إن لم يكن /proc لفضاء PID المنسّق) — فلا يُحكم لاحقاً
    ببقاء عمليّةٍ ورثت رقمَها. cgroup.procs يُترجَم إلى فضاء القارئ، و``kill`` في فضائنا."""
    killed = []
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    for path in info.get("paths", [])[:1]:
        for pid in Path(path, "cgroup.procs").read_text().split():
            start = procs.starttime(int(pid))
            try:
                os.kill(int(pid), signal.SIGKILL)
                killed.append(int(pid))
                if identities is not None:
                    identities[str(pid)] = start
            except ProcessLookupError:
                pass
    return killed


def pin_files(engine: str, manifest: Path, dest: Path) -> tuple[dict, Path]:
    """نسخةٌ خاصّة بالتشغيل من الملفّات المُثبَّتة، تُطابَق بصماتها قبل الإطلاق — لا يُحمَّل الأصل."""
    from worker import verify_manifest  # بلا تبعيّات المحرّك

    cfg = json.loads(manifest.read_text(encoding="utf-8")).get(engine, {})
    verify_manifest(engine, cfg, manifest.parent)  # يرفض الأصلَ المعطوب قبل النسخ
    dest.mkdir(parents=True)
    for rel in cfg.get("files", {}):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifest.parent / rel, target)
    for rel in cfg.get("trees", {}):
        shutil.copytree(manifest.parent / rel, dest / rel, symlinks=True)
    pinned_manifest = dest / "manifest.json"
    pinned_manifest.write_text(
        json.dumps({engine: cfg}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    verify_manifest(engine, cfg, dest)  # النسخةُ نفسها تطابق
    return cfg, pinned_manifest


# جذورُ النظام **ضيّقة**: مكتباتٌ وتنفيذيّاتٌ وإعداداتٌ وواجهاتُ النواة. /usr/share ليس منها (إلّا المنطقةَ
# الزمنيّة واللغات) — فنموذجٌ يُوضع هناك لا يمرّ «نظاماً».
SYSTEM_ROOTS = (
    "/lib/",
    "/lib64/",
    "/usr/lib/",
    "/usr/lib64/",
    "/usr/libexec/",
    "/bin/",
    "/sbin/",
    "/usr/bin/",
    "/usr/sbin/",
    "/etc/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/usr/share/zoneinfo/",
    "/usr/share/locale/",
)
# ما يُشبه أوزاناً أو بياناتِ نموذج: غيرُ مُعلنٍ **أينما كان** خارج المُثبَّت، ما لم تُعلَن بصمتُه في
# ``package_assets`` (مثل piper/tashkeel/model.onnx داخل الحزمة).
WEIGHT_EXT = (
    ".onnx",
    ".ort",
    ".pt",
    ".pth",
    ".bin",
    ".safetensors",
    ".ckpt",
    ".gguf",
    ".ggml",
    ".tflite",
    ".pb",
    ".h5",
    ".npz",
    ".npy",
    ".msgpack",
    ".model",
    ".tar",
    ".zip",
    ".pkl",
)
LARGE_BYTES = 5 * 2**20  # ملفُّ بياناتٍ كبيرٌ بلا امتدادٍ معروف يُعامَل كالأوزان
CODE_RE = r"\.(so(\.[\w.]+)?|py|pyc|pyi)$"
LARGE_EXEMPT = ("/usr/lib/locale/locale-archive",)


def file_inventory(
    log: Path,
    pinned_root: str,
    py_roots: list[str],
    harness_roots: list[str],
    declared_assets: dict | None = None,
) -> dict:
    """يصنّف كلَّ ملفٍّ فتحته العمليّة وأبناؤها (strace): مُثبَّت · بيئةُ بايثون · نظام · **غيرُ مُعلن**.

    غيرُ مُعلن: ما وقع خارج الجذور المعروفة، **أو** ما يُشبه أوزاناً (امتداداً أو حجماً) خارج المُثبَّت
    ولم تُعلَن بصمتُه في ``package_assets`` — ولو كان تحت /usr أو داخل بيئة بايثون."""
    import re

    from worker import sha256_file

    declared_sha = set((declared_assets or {}).values())
    reasons: dict[str, str] = {}

    def site_pth(real: str) -> bool:
        """ملفُّ .pth الخاصّ ببايثون (مساراتُ site): مباشرةً في جذرٍ لبايثون، صغيرٌ ونصّيّ. أوزانُ PyTorch
        بالامتداد نفسه لا تستوفي الثلاثة معاً — وإن وُضعت هناك صغيرةً نصّيّةً فليست أوزاناً."""
        if not real.endswith(".pth") or os.path.dirname(real) + "/" not in py_roots:
            return False
        try:
            if os.path.getsize(real) > 64 * 1024:
                return False
            Path(real).read_text(encoding="utf-8")
            return True
        except (OSError, UnicodeDecodeError):
            return False

    def weight_like(real: str) -> str | None:
        if real.lower().endswith(WEIGHT_EXT) and not site_pth(real):
            return "weight_extension"
        try:
            big = os.path.getsize(real) >= LARGE_BYTES
        except OSError:
            return None
        if big and not re.search(CODE_RE, real) and real not in LARGE_EXEMPT:
            return f"large_data_file>={LARGE_BYTES // 2**20}MiB"
        return None

    opened = set()
    for one in log if isinstance(log, list) else [log]:
        for line in one.read_text(errors="replace").splitlines():
            m = re.search(r'open(?:at2?)?\((?:[^,]+, )?"([^"]+)"', line)
            if m and "ENOENT" not in line and "ENOTDIR" not in line:
                # مسارٌ نسبيّ يُحلّ بما طبعه ``-y`` للواصف المُعاد، لا بمجلّد عمل المنسّق (داخل bwrap: --chdir الحزمة)
                decorated = re.search(r"\) += \d+<([^>]+)>$", line)
                path = m.group(1)
                if not path.startswith("/") and decorated:
                    path = decorated.group(1)
                opened.add(_unescape(path))
    classes: dict[str, list] = {
        "pinned": [],
        "python_env": [],
        "system": [],
        "harness": [],
        "undeclared": [],
    }
    for path in sorted(opened):
        real = os.path.realpath(path)
        if os.path.isdir(real):
            continue
        if real.startswith(pinned_root):
            classes["pinned"].append(real)
            continue
        kind = weight_like(real) if os.path.isfile(real) else None
        if kind:
            digest = sha256_file(Path(real))
            if digest not in declared_sha:
                classes["undeclared"].append(real)
                reasons[real] = f"{kind} (sha256 {digest[:16]}… غيرُ مُعلن في package_assets)"
                continue
        if any(real.startswith(a) for a in py_roots):
            entry = {"path": real}
            if (
                os.path.isfile(real)
                and not real.endswith((".py", ".pyc"))
                and "/site-packages/" in real
            ):
                entry["sha256"] = sha256_file(
                    Path(real)
                )  # بياناتُ الحزم (مثل piper/tashkeel/model.onnx)
            classes["python_env"].append(entry)
        elif any(real.startswith(a) for a in harness_roots):
            classes["harness"].append(real)
        elif real.startswith(SYSTEM_ROOTS) or real in ("/dev/null",) or path in BWRAP_SYSTEM_RO:
            # ملفُّ نظامٍ معلنٌ **باسمه** يبقى ملفَّ نظام وإن كان رابطاً إلى خارج الجذور (/etc/resolv.conf →
            # /mnt/wsl/resolv.conf على WSL). شبيهُ الأوزان فُحص قبل هذا فلا يمرّ عبر رابطٍ كهذا.
            classes["system"].append(real)
        else:
            classes["undeclared"].append(real)
            reasons[real] = "outside_known_roots"
    return {
        "files_opened": len(opened),
        "python_roots": py_roots,
        "system_roots": list(SYSTEM_ROOTS),
        "declared_package_assets": declared_assets or {},
        "undeclared_reasons": reasons,
        "package_data": [e for e in classes["python_env"] if "sha256" in e],
        "pinned": classes["pinned"],
        "undeclared": classes["undeclared"],
        "counts": {k: len(v) for k, v in classes.items()},
    }


# ── الإغلاق (closure): ما لمسه المحرّكُ فعلاً **داخل** الصندوق، ملفّاً ملفّاً ─────────────────────────────────
#
# صندوقُ bwrap بربطات مجلّدات النظام (/usr/lib · /usr/bin …) يُبقي كلَّ ما تحتها مقروءاً للمحرّك: نموذجٌ غيرُ معلَن
# تحت /usr/lib كان يمرّ ``harness_status=ok`` و``performance_comparable=true`` (مقيسٌ على main@0e5281614). والجردُ
# بـstrace كان **خارج** الصندوق فيرى إعدادَ bwrap نفسه (/newroot/…) لا ما فتحه المحرّك. الآن: ``--inventory --sandbox
# bwrap`` يشغّل strace **داخل** الصندوق ويُسجّل الإغلاق، و``--closure-from`` يربط تلك الملفّات وحدها، واحداً واحداً.
STRACE_ARGS = ("-ff", "-y", "-qq", "-e", "trace=%file")
# ما يُنشئه الصندوقُ نفسه (proc · dev · tmpfs) أو يُربط كاملاً لأنّه واجهةُ النواة لحدود هذا التشغيل (مجموعتُه باسمه).
VIRTUAL_ROOTS = ("/proc/", "/dev/", "/sys/fs/cgroup/")
VIRTUAL_EXACT = ("/proc", "/dev", "/tmp", "/sys/fs/cgroup")
# /tmp في الصندوق tmpfs جديد: ما تحته إمّا أنشأه التشغيلُ نفسُه (لا يوجد في المضيف) أو رُبط صراحةً فوقه (بيئةٌ
# افتراضيّة أو مجلّدُ تشغيلٍ تحت /tmp) — والثاني يدخل الإغلاق كأيّ ملفّ.
SANDBOX_TMPFS = "/tmp/"
# الروابطُ التي يُنشئها bwrap_command في كلّ صندوق: تُتبَع كما يراها الصندوق لا كما يراها المضيف.
SANDBOX_LINKS = {"/lib": "usr/lib", "/lib64": "usr/lib64", "/bin": "usr/bin"}
_QUOTED = r'"((?:[^"\\]|\\.)*)"'
_TRACE_LINE = re.compile(
    r"^(?:\d+ +)?(?P<call>[a-z_0-9]+)\((?P<args>.*)\) += (?P<ret>-?\d+|\?)"
    r"(?:<(?P<fdpath>(?:[^>\\]|\\.)*)>)?(?: (?P<err>E[A-Z0-9]+))?"
)
_DIRFD = re.compile(r"^(?:AT_FDCWD|-?\d+)(?:<(?P<dir>(?:[^>\\]|\\.)*)>)?, " + _QUOTED)
_FIRST = re.compile(r"^" + _QUOTED)


def _unescape(text: str) -> str:
    """سلسلةُ strace بترميز C (``\\ooo`` · ``\\xhh`` · ``\\n`` …) ⇒ المسارُ كما هو (UTF-8 لا يضيع)."""
    out, i = bytearray(), 0
    simple = {"n": b"\n", "t": b"\t", "r": b"\r", "v": b"\v", "f": b"\f", "\\": b"\\", '"': b'"'}
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in "01234567":
                j = i + 1
                while j < len(text) and j < i + 4 and text[j] in "01234567":
                    j += 1
                out.append(int(text[i + 1 : j], 8) & 0xFF)
                i = j
                continue
            if nxt == "x":
                out.append(int(text[i + 2 : i + 4], 16))
                i += 4
                continue
            out += simple.get(nxt, nxt.encode())
            i += 2
            continue
        out += ch.encode("utf-8", "surrogateescape")
        i += 1
    return out.decode("utf-8", "surrogateescape")


def trace_events(paths: list[Path]) -> tuple[list[dict], list[str]]:
    """كلُّ نداءٍ ناجحٍ يحمل مساراً في سجلّات ``strace -ff -y``: ``(call, path, fdpath)`` بمسارٍ مطلق.

    النسبيُّ يُحلّ على مجلّد ``dirfd`` الذي يطبعه ``-y`` (``AT_FDCWD</cwd>``)، ونسبيٌّ بلا مجلّدٍ معلَن يُعاد
    في القائمة الثانية (لا يُخمَّن مجلّدُ العمل). الفاشلُ (ENOENT …) غيابٌ يتكرّر في الصندوق الضيّق نفسه."""
    events, unresolved = [], []
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
            m = _TRACE_LINE.match(line)
            if not m or m.group("ret") in ("?",) or int(m.group("ret")) < 0:
                continue
            args = m.group("args")
            # نداءاتُ *at تبدأ بالواصف (``AT_FDCWD</cwd>, "…"``)، والباقي بالمسار نفسه — لا التباس بين الشكلين
            at, plain = _DIRFD.match(args), _FIRST.match(args)
            if not (at or plain):
                continue
            target = _unescape(at.group(2) if at else plain.group(1))
            if not target:  # AT_EMPTY_PATH: النداءُ على واصفٍ فُتح سابقاً
                continue
            if not target.startswith("/"):
                base = _unescape(at.group("dir")) if at and at.group("dir") else None
                if not base:
                    unresolved.append(f"{m.group('call')}:{target}")
                    continue
                target = os.path.join(base, target)
            fdpath = m.group("fdpath")
            events.append(
                {
                    "call": m.group("call"),
                    "path": os.path.normpath(target),
                    "fdpath": _unescape(fdpath) if fdpath else None,
                }
            )
    return events, unresolved


def resolve_in_sandbox(path: str, crossed: dict[str, str]) -> str:
    """``realpath`` كما يراه الصندوق: روابطُ bwrap (/lib → usr/lib) أوّلاً، ثمّ روابطُ المضيف — وكلُّ رابطٍ عُبر يُسجَّل
    في ``crossed`` (موضعُه بمسارٍ حقيقيٍّ لأبيه ⇒ هدفُه الخام) كي يُعاد إنشاؤه كما هو في الصندوق الضيّق."""
    comps = [c for c in path.split("/") if c not in ("", ".")]
    cur, i, hops = "", 0, 0
    while i < len(comps):
        name = comps[i]
        i += 1
        if name == "..":
            cur = os.path.dirname(cur) if cur else ""
            cur = "" if cur == "/" else cur
            continue
        cand = f"{cur}/{name}"
        target = SANDBOX_LINKS.get(cand)
        if target is None and os.path.islink(cand):
            target = os.readlink(cand)
            crossed[cand] = target
        if target is None:
            cur = cand
            continue
        hops += 1
        if hops > 40:
            raise OSError(40, "ELOOP", path)
        base = "" if target.startswith("/") else cur
        comps = [c for c in f"{base}/{target}".split("/") if c not in ("", ".")] + comps[i:]
        cur, i = "", 0
    return cur or "/"


def elf_interpreter(path: str) -> str | None:
    """ما تُحمّله النواةُ **بنفسها** عند ``execve`` فلا يظهر في strace: ``PT_INTERP`` لملفّ ELF (ld-linux)، أو مفسّرُ
    سطر ``#!``. بدونه يربط الصندوقُ الضيّقُ التنفيذيَّ ولا يجد مُحمِّلَه (``execvp … No such file``)."""
    import struct

    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
            if head[:2] == b"#!":
                words = (head + fh.read(192))[2:].split(b"\n")[0].split()
                return words[0].decode("utf-8", "surrogateescape") if words else None
            if head[:4] != b"\x7fELF" or len(head) < 58:
                return None
            end = "<" if head[5] == 1 else ">"
            wide = head[4] == 2
            phoff = struct.unpack(
                end + ("Q" if wide else "I"), head[32:40] if wide else head[28:32]
            )[0]
            phentsize, phnum = struct.unpack(end + "HH", head[54:58] if wide else head[42:46])
            for k in range(phnum):
                fh.seek(phoff + k * phentsize)
                ph = fh.read(phentsize)
                if struct.unpack(end + "I", ph[:4])[0] != 3:  # PT_INTERP
                    continue
                off, size = (
                    struct.unpack(end + "QQ", ph[8:16] + ph[32:40])
                    if wide
                    else struct.unpack(end + "II", ph[4:8] + ph[16:20])
                )
                fh.seek(off)
                return fh.read(size).rstrip(b"\0").decode("utf-8", "surrogateescape")
    except (OSError, struct.error):
        return None
    return None


def _excluded(real: str, private: list[str], bound=()) -> str | None:
    if real in VIRTUAL_EXACT or real.startswith(VIRTUAL_ROOTS):
        return "virtual"
    if any(real == p.rstrip("/") or real.startswith(p) for p in private):
        return "run_private"
    if real.startswith(SANDBOX_TMPFS) and not any(
        real == b or real.startswith(b.rstrip("/") + "/") for b in bound
    ):
        return "virtual"
    return None


def build_closure(events: list[dict], unresolved: list[str], private: list[str], bound=()) -> dict:
    """الإغلاقُ من أحداث strace: كلُّ ملفٍّ لُمس (قراءةً · تنفيذاً · فحصَ وجود · مُحمِّلاً) ببصمته، والمجلّداتُ التي لُمست،
    والروابطُ التي عُبرت، ومُحمِّلُ كلّ تنفيذيّ. ``private`` (المُثبَّتُ والناتجُ لهذا التشغيل) خارجه: لكلّ تشغيلٍ نسختُه.
    ``bound``: ما رُبط في صندوق الجرد — وحده يُرى تحت tmpfs ‏/tmp.

    ``problems`` غيرُ فارغة ⇒ الإغلاقُ لا يُعتمد (ملفٌّ لُمس ثمّ غاب عن المضيف · مسارٌ نسبيّ بلا مجلّد · نوعٌ خاصّ)."""
    from worker import sha256_file

    files: dict[str, set] = {}
    dirs: set[str] = set()
    crossed: dict[str, str] = {}
    loaders: dict[str, str] = {}
    skipped = {"virtual": 0, "run_private": 0}
    problems = [f"مسارٌ نسبيٌّ بلا مجلّدٍ معلَن: {u}" for u in sorted(set(unresolved))]
    queue = [
        (
            e["path"],
            "exec"
            if e["call"].startswith("execve")
            else "read"
            if e["call"].startswith("open")
            else "stat",
        )
        for e in events
    ]
    seen_exec: set[str] = set()
    while queue:
        path, access = queue.pop(0)
        # /proc/self … تُتبَع في المضيف إلى عمليّةٍ أخرى — لا تُمشى
        if _excluded(path, private, bound) == "virtual":
            skipped["virtual"] += 1
            continue
        try:
            real = resolve_in_sandbox(path, crossed)
        except OSError as exc:
            problems.append(f"{path}: {exc}")
            continue
        why = _excluded(real, private, bound)
        if why:
            skipped[why] += 1
            continue
        if os.path.isdir(real):
            if real != "/":  # الجذرُ قائمٌ في كلّ صندوق
                dirs.add(real)
            continue
        if not os.path.isfile(real):
            if os.path.lexists(real) or not os.path.lexists(path):
                problems.append(f"لُمس ولا يوجد ملفّاً عادياً على المضيف: {path} -> {real}")
            continue
        files.setdefault(real, set()).add(access)
        if access in ("exec", "loader") and real not in seen_exec:
            seen_exec.add(real)
            interp = elf_interpreter(real)
            if interp:
                loaders[real] = interp
                queue.append((interp, "loader"))
    return {
        "version": 1,
        "files": {
            p: {"sha256": sha256_file(Path(p)), "access": sorted(a)}
            for p, a in sorted(files.items())
        },
        "dirs": sorted(dirs),
        "symlinks": dict(sorted(crossed.items())),
        "loaders": dict(sorted(loaders.items())),
        "stat_only": sorted(p for p, a in files.items() if a == {"stat"}),
        "skipped": skipped,
        "problems": problems,
    }


def manifest_digest(engine: str, cfg: dict) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps({engine: cfg}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def load_closure(
    inventory_run: Path, engine: str, interpreter: dict, manifest_sha: str
) -> tuple[dict | None, str | None, str | None]:
    """الإغلاقُ من تشغيل جرد ⇒ ``(closure, None, None)``، أو ``(None, stage, why)``.

    ``closure_rejected``: ليس تشغيلَ جردٍ نظيفاً داخل bwrap للمحرّك والمفسّر والبيان أنفسهم، أو بصمتُه لا تطابق محتواه.
    ``closure_stale``: ملفٌّ من الإغلاق تغيّر أو غاب منذ الجرد — ما قِيس ليس ما سيُربط."""
    from perf import closure_digest, load_result
    from worker import sha256_file

    try:
        inv = load_result(inventory_run / "result.json")
    except (OSError, ValueError) as exc:
        return None, "closure_rejected", f"لا سجلَّ جردٍ مقروءاً في {inventory_run}: {exc}"
    fi = inv.get("file_inventory") or {}
    closure = fi.get("closure")
    sandbox = (inv.get("coordinator") or {}).get("sandbox") or {}
    reasons = []
    if inv.get("harness_status") != "ok":
        reasons.append(f"harness_status={inv.get('harness_status')!r} stage={inv.get('stage')!r}")
    if sandbox.get("kind") != "bwrap" or sandbox.get("inventory") != "strace-inside-sandbox":
        reasons.append("ليس جرداً بـstrace داخل صندوق bwrap")
    if fi.get("undeclared"):
        reasons.append(f"ملفّاتٌ غيرُ معلنة في الجرد: {fi['undeclared'][:5]}")
    if not isinstance(closure, dict):
        return None, "closure_rejected", "; ".join(reasons + ["لا إغلاقَ في سجلّ الجرد"])
    if closure.get("problems"):
        reasons.append(f"مشكلاتُ الإغلاق: {closure['problems'][:5]}")
    if closure.get("sha256") != closure_digest(closure):
        reasons.append("بصمةُ الإغلاق لا تطابق محتواه")
    if closure.get("engine") != engine or inv.get("engine") != engine:
        reasons.append(f"محرّكٌ آخر: {closure.get('engine')!r} ≠ {engine!r}")
    if {k: (closure.get("interpreter") or {}).get(k) for k in ("path", "real")} != {
        k: interpreter.get(k) for k in ("path", "real")
    }:
        reasons.append(f"مفسّرٌ آخر: {closure.get('interpreter')} ≠ {interpreter}")
    if closure.get("manifest_sha256") != manifest_sha:
        reasons.append("بيانُ المحرّك (الملفّاتُ المُثبَّتة والإعدادات) غيرُ الذي جُرد")
    if reasons:
        return None, "closure_rejected", "; ".join(reasons)
    stale = []
    for path, entry in closure["files"].items():
        try:
            if os.path.isdir(path) or sha256_file(Path(path)) != entry["sha256"]:
                stale.append(path)
        except OSError:
            stale.append(path)
    if stale:
        return None, "closure_stale", f"{len(stale)} ملفّاً تغيّر أو غاب منذ الجرد: {stale[:5]}"
    return closure, None, None


def closure_bwrap_command(
    worker: list[str], closure: dict, pinned: str, out: str
) -> tuple[list[str], list[str]]:
    """صندوقٌ لا يُربط فيه **مجلّدٌ** من النظام: كلُّ ملفٍّ من الإغلاق وحده للقراءة، والمجلّداتُ التي لُمست تُنشأ فارغة،
    والروابطُ التي عُبرت تُنشأ بأهدافها الخام. يبقى المُثبَّتُ (بصماتُه من البيان) و/sys/fs/cgroup (حدودُ هذا التشغيل)."""
    base, _ = bwrap_command([], [], [])
    args = base[: base.index("--chdir")]
    binds: list[str] = []
    for d in closure.get("dirs", []):
        args += ["--dir", d]
        binds.append(f"dir:{d}")
    for path in closure["files"]:
        args += ["--ro-bind", path, path]
        binds.append(f"ro:{path}")
    for link, target in closure.get("symlinks", {}).items():
        if link in SANDBOX_LINKS:
            continue
        args += ["--symlink", target, link]
        binds.append(f"symlink:{link}->{target}")
    for path in (pinned, "/sys/fs/cgroup"):
        args += ["--ro-bind", path, path]
        binds.append(f"ro:{path}")
    args += ["--bind", out, out, "--remount-ro", "/"]
    binds.append(f"rw:{out}")
    return args + ["--chdir", str(HERE), "--", *worker], binds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--python", default=sys.executable, help="مفسّرُ بيئة المحرّك")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    ap.add_argument("--mem-mb", type=int, default=4096)
    ap.add_argument("--cpus", type=float, default=2.0, help="حصّةُ وقت المعالج (cpu.cfs_quota_us)")
    ap.add_argument(
        "--cores", type=int, default=0, help="عددُ الأنوية المسموح بها (taskset)؛ 0 = ceil(cpus)"
    )
    ap.add_argument("--threads", type=int, default=0, help="OMP/ORT/MKL threads؛ 0 = عددُ الأنوية")
    ap.add_argument("--hard-timeout", type=float, default=3600)
    ap.add_argument(
        "--inventory", action="store_true", help="جردُ الملفّات المفتوحة بـstrace (لا لقياس الأداء)"
    )
    ap.add_argument(
        "--no-isolation", action="store_true", help="للتطوير فقط: الشبكة والملفّات BLOCKED"
    )
    ap.add_argument(
        "--sandbox",
        choices=("unshare", "bwrap"),
        default="unshare",
        help="unshare: شبكةٌ وتركيبٌ خاصّان والمُثبَّت للقراءة · bwrap: جذرٌ فارغ لا يُرى فيه إلّا المعلن",
    )
    ap.add_argument(
        "--closure-from",
        default=None,
        metavar="INVENTORY_RUN",
        help="مع --sandbox bwrap: يربط ملفّاتِ إغلاق تشغيل جردٍ نظيف (--inventory --sandbox bwrap) واحداً واحداً، "
        "لا مجلّداتِ النظام — الشرطُ لمقارنة الأداء",
    )
    ap.add_argument("worker_args", nargs=argparse.REMAINDER, help="-- ثمّ معاملاتٌ تُمرَّر للعامل")
    args = ap.parse_args()
    # مشغّلٌ ورّث SIGCHLD=SIG_IGN يجعل النواةَ تحصد الأبناءَ فوراً: waitpid ⇒ ECHILD ⇒ returncode = 0 لكلِّ ابن،
    # فيضيع فشلُه (مقيسٌ: 13 حالةَ رفضٍ صارت rc=0). يُعاد إلى الافتراضيّ قبل أيِّ عمليّةٍ فرعيّة، ويُسجَّل الموروث.
    SIGCHLD_INHERITED = (
        "SIG_IGN" if signal.getsignal(signal.SIGCHLD) == signal.SIG_IGN else "default"
    )
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)

    run_id = f"{args.engine}-{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    root = Path(args.runs_root).resolve()
    out, pinned, trace = root / run_id, root / f"{run_id}.pinned", root / f"{run_id}.strace"
    if out.exists() or pinned.exists():
        print(f"مرفوض: {out} موجود", file=sys.stderr)
        return 5

    def early_failure(stage: str, error: str) -> int:
        """فشلٌ قبل أيّ تشغيل: سجلٌّ بمرحلته وسببه، لا أثرَ مكدّسٍ ولا سجلَّ مفقود."""
        out.mkdir(parents=True)
        result = {
            "run_id": run_id,
            "engine": args.engine,
            "harness_status": "failed",
            "stage": stage,
            "error": error,
        }
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {"run": str(out), "harness_status": "failed", "stage": stage},
                ensure_ascii=False,
            )
        )
        return 1

    # المفسّرُ بمسارٍ مطلق: داخل bwrap يتغيّر مجلّدُ العمل (--chdir إلى الحزمة) فيُحلّ «venv/bin/python» النسبيُّ
    # على غير ما قصده المستدعي، ولا يُربط مسارٌ نسبيّ. يُحفظ الرابطُ نفسه (abspath لا realpath): بايثون يكتشف
    # بيئتَه الافتراضيّة من موضع المُشغِّل، فحلُّ الرابط يُسقط site-packages البيئة.
    found = args.python if os.sep in args.python else shutil.which(args.python)
    if not found or not os.access(found, os.X_OK):
        return early_failure("python_not_found", f"--python {args.python!r}: لا مفسّرَ قابلاً للتنفيذ")
    args.python = os.path.abspath(found)
    if args.closure_from and (args.sandbox != "bwrap" or args.inventory or args.no_isolation):
        return early_failure(
            "closure_rejected",
            "--closure-from يتطلّب --sandbox bwrap بلا --inventory ولا --no-isolation",
        )
    if args.inventory and not shutil.which("strace"):
        # ليس عيباً في المحرّك ولا في الأداة: أداةُ القياس غائبة. مرحلةٌ مسمّاة يُصنّفها الاختبارُ الذاتيّ BLOCKED.
        return early_failure("inventory_tool_missing", "--inventory يتطلّب strace وهو غيرُ مثبّت")
    try:
        cfg, pinned_manifest = pin_files(args.engine, Path(args.manifest).resolve(), pinned)
    except SystemExit as exc:
        return early_failure("manifest_rejected", str(exc))
    from worker import sha256_file, sha256_tree

    def pinned_digests() -> dict:
        return {
            **{f"file:{r}": sha256_file(pinned / r) for r in cfg.get("files", {})},
            **{f"tree:{r}": sha256_tree(pinned / r) for r in cfg.get("trees", {})},
        }

    before = pinned_digests()
    manifest_sha = manifest_digest(args.engine, cfg)

    # جذورُ بيئة بايثون كما يراها **مفسّرُ المحرّك نفسه** (sys.path + prefix)، لا تخميناً — للجرد ولربط bwrap.
    probe = subprocess.run(
        [
            args.python,
            "-c",
            "import sys,json;print(json.dumps({'path':[p for p in sys.path if p],"
            "'prefix':sys.prefix,'base_prefix':sys.base_prefix}))",
        ],
        capture_output=True,
        text=True,
    )
    seen = json.loads(probe.stdout or "{}")
    # المفسّرُ وبادئتاه كما رآها **هو**: perf.py يقبل ربطَ بادئةٍ لأنّها بادئةُ هذا المفسّر (فيها bin/python)،
    # لا لأنّها مذكورةٌ في السجلّ. بلا هذا كانت كلُّ بيئةٍ افتراضيّة «ربطاً خارج المعلن» (قياسُ المالك).
    interpreter = {
        "path": args.python,
        "real": os.path.realpath(args.python),
        "prefix": seen.get("prefix"),
        "base_prefix": seen.get("base_prefix"),
    }
    # sys.prefix يُستبعد إن كان جذرَ نظام (/usr · /usr/local · /): ربطُه في bwrap يُعيد كشفَ /usr/share كلّه،
    # وعدُّه «بيئة بايثون» في الجرد يُصنّف كلَّ /usr تحتها. مداخلُ sys.path نفسُها محدّدةٌ بما يكفي.
    py_roots = sorted(
        {
            p.rstrip("/") + "/"
            for p in [*seen.get("path", []), seen.get("prefix"), seen.get("base_prefix")]
            if p and p.rstrip("/") not in ("", "/usr", "/usr/local")
        }
    )
    closure = None
    if args.closure_from:
        closure, stage, why = load_closure(
            Path(args.closure_from).resolve(), args.engine, interpreter, manifest_sha
        )
        if closure is None:
            return early_failure(stage, why)
    if args.sandbox == "bwrap":
        isolation_probe = (
            procs.bwrap_probe(
                [
                    "bwrap",
                    "--ro-bind",
                    "/usr",
                    "/usr",
                    "--symlink",
                    "usr/lib64",
                    "/lib64",
                    "--symlink",
                    "usr/lib",
                    "/lib",
                    "--unshare-net",
                    "--die-with-parent",
                    "/usr/bin/true",
                ]
            )
            if shutil.which("bwrap")
            else (False, "لا bwrap")
        )
    else:
        isolation_probe = (
            procs.probe(["unshare", "-n", "-m", "true"])
            if shutil.which("unshare")
            else (False, "لا unshare")
        )
    can_isolate = bool(
        not args.no_isolation
        and (args.sandbox == "bwrap" or os.geteuid() == 0)
        and isolation_probe[0]
    )
    neg = negative_control()
    cg = setup_cgroups(f"bakeoff-{run_id}", args.mem_mb, args.cpus)
    ncores = args.cores or max(1, -(-int(args.cpus * 100) // 100))
    cores = ",".join(str(i) for i in sorted(os.sched_getaffinity(0))[:ncores])
    nthreads = args.threads or ncores
    limits = {
        "memory_limit_mb": args.mem_mb,
        "cpu_quota": args.cpus,
        "cpu_cores": cores,
        "threads": nthreads,
        "cgroup": cg["backend"],
        "hard_timeout_s": args.hard_timeout,
    }
    env = worker_env(os.environ)
    env.update(
        {
            "BAKEOFF_LIMITS": json.dumps(limits),
            "BAKEOFF_CONTROL_HOST": CONTROL_HOST,
            "BAKEOFF_CONTROL_IP": neg.get("ip") or "",
            "OMP_NUM_THREADS": str(nthreads),
            "MKL_NUM_THREADS": str(nthreads),
            "ORT_NUM_THREADS": str(nthreads),
        }
    )

    inner = [
        args.python,
        str(HERE / "worker.py"),
        "--engine",
        args.engine,
        "--manifest",
        str(pinned_manifest),
        "--out",
        str(out),
        "--run-id",
        run_id,
        "--pinned-dir",
        str(pinned),
    ]
    inner += [a for a in args.worker_args if a != "--"]
    sandbox = {"kind": args.sandbox, "probe": isolation_probe[1], "interpreter": interpreter}
    # الجردُ داخل bwrap: strace **داخل** الصندوق، فيرى ما يفتحه المحرّك بمساراته هناك — لا إعدادَ bwrap نفسه (/newroot/…)
    # ولا ما خارج الصندوق. ناتجُه في مجلّدٍ منفصل (مجلّدُ الناتج يجب أن يبدأ فارغاً) — ربطُ كتابةٍ ثانٍ في تشغيلٍ لا يُقارَن أصلاً.
    inside_trace = args.inventory and args.sandbox == "bwrap" and can_isolate
    if args.sandbox == "bwrap" and can_isolate:
        out.mkdir(parents=True, exist_ok=True)
        inner = [*inner, "--expect-isolated"]
        if closure is not None:
            bw, binds = closure_bwrap_command(inner, closure, str(pinned), str(out))
            sandbox["closure"] = {**closure, "from_run": str(Path(args.closure_from).resolve())}
        else:
            ro = [
                *BWRAP_SYSTEM_RO,
                *[r.rstrip("/") for r in py_roots],
                *link_chain(args.python),
                str(HERE),
                str(pinned),
            ]
            rw = [str(out)]
            if inside_trace:
                trace.mkdir()
                ro += link_chain(shutil.which("strace"))
                rw.append(str(trace))
                inner = ["strace", *STRACE_ARGS, "-o", str(trace / "t"), *inner]
                sandbox["inventory"] = "strace-inside-sandbox"
            bw, binds = bwrap_command(inner, ro, rw)
        sandbox.update(
            binds=binds,
            version=subprocess.run(
                ["bwrap", "--version"], capture_output=True, text=True
            ).stdout.strip(),
        )
        inner = bw
    worker = ["taskset", "-c", cores, *inner]
    if args.inventory and not inside_trace:
        worker = [
            "strace",
            "-f",
            "-qq",
            "-e",
            "trace=open,openat,openat2",
            "-o",
            str(trace),
            *worker,
        ]
    if args.sandbox == "bwrap":
        cmd = worker  # العزلُ داخل أمر bwrap نفسه (أو لا عزل إن تعذّر، فيُسجَّل BLOCKED)
    elif can_isolate:
        # شبكةٌ ومساراتُ تركيبٍ خاصّة: الملفّاتُ المُثبَّتة للقراءة فقط **حتّى لـroot**، ولا يتسرّب التركيب للمضيف.
        wrapper = (
            'mount --make-rprivate / && mount --bind "$P" "$P" && mount -o remount,bind,ro "$P" '
            '|| exit 90; exec "$@"'
        )
        cmd = [
            "unshare",
            "-n",
            "-m",
            "--",
            "env",
            f"P={pinned}",
            "sh",
            "-c",
            wrapper,
            "sh",
            *worker,
            "--expect-isolated",
        ]
    else:
        cmd = worker

    def enter_limits() -> None:
        os.setsid()
        for path in cg.get("paths", []):
            Path(path, "cgroup.procs").write_text(str(os.getpid()))

    proc = subprocess.Popen(cmd, env=env, preexec_fn=enter_limits)
    killed, killed_pids, killed_identities = False, [], {}
    try:
        rc = proc.wait(timeout=args.hard_timeout)
    except subprocess.TimeoutExpired:
        killed_pids = kill_everything(proc, cg, killed_identities)
        rc, killed = proc.wait(), True
    # أبناءٌ قد يبقون بعد خروج العامل نفسه
    survivors = Path(cg["paths"][0], "cgroup.procs").read_text().split() if cg.get("paths") else []
    if survivors:
        killed_pids += kill_everything(proc, cg, killed_identities)
    stats = cgroup_stats(cg)
    teardown_cgroups(cg)
    after = pinned_digests()
    if closure is not None:
        # ما رُبط بقي كما جُرد بعد التشغيل؟ (تغييرٌ عابرٌ أثناءه ثمّ إرجاعٌ لا يُرى هنا — حدٌّ معلَن لا مُخفى)
        from worker import sha256_file

        changed = []
        for path, entry in closure["files"].items():
            try:
                if sha256_file(Path(path)) != entry["sha256"]:
                    changed.append(path)
            except OSError:
                changed.append(path)
        sandbox["integrity_after"] = "INTACT" if not changed else {"changed": changed}

    result_path = out / "result.json"
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.exists()
        else {
            "run_id": run_id,
            "engine": args.engine,
            "harness_status": "failed",
            "stage": "no_result",
        }
    )
    if not can_isolate:
        result["network_isolation"] = "BLOCKED"
        result["files_readonly"] = "BLOCKED"
    if inside_trace:
        logs = sorted(trace.glob("t.*"))
        result["file_inventory"] = file_inventory(
            logs,
            str(pinned) + "/",
            py_roots,
            [str(HERE) + "/", str(out) + "/"],
            cfg.get("package_assets"),
        )
        events, unresolved = trace_events(logs)
        built = build_closure(
            events,
            unresolved,
            [str(pinned) + "/", str(out) + "/", str(trace) + "/"],
            # ما رُبط فوق tmpfs ‏/tmp مرئيٌّ في الصندوق فيدخل الإغلاق؛ وما سواه تحت /tmp أنشأه التشغيل
            [b.split(":", 1)[1].split("->")[0] for b in sandbox.get("binds", [])],
        )
        built.update(
            engine=args.engine,
            interpreter={k: interpreter[k] for k in ("path", "real")},
            manifest_sha256=manifest_sha,
            inventory_run=run_id,
        )
        from perf import closure_digest

        built["sha256"] = closure_digest(built)
        result["file_inventory"]["closure"] = built
    elif args.inventory and trace.exists():
        result["file_inventory"] = file_inventory(
            trace,
            str(pinned) + "/",
            py_roots,
            [str(HERE) + "/", str(out) + "/"],
            cfg.get("package_assets"),
        )
    result["pinned_integrity_after"] = (
        "INTACT"
        if after == before
        else {"changed": sorted(k for k in before if after.get(k) != before[k])}
    )
    result["coordinator"] = {
        "command": cmd,
        "exit_code": rc,
        "killed_at_hard_timeout": killed,
        "killed_pids": sorted(set(killed_pids)),
        "killed_starttimes": killed_identities,
        "worker_env_names": sorted(env),
        "proc_matches_pid_namespace": procs.proc_namespace()[0],
        "survivors_after_exit": survivors,
        "negative_control": neg,
        "system_isolation": (
            "UNAVAILABLE"
            if not can_isolate
            else "unshare -n -m (ro pinned)"
            if args.sandbox == "unshare"
            else "bwrap (empty root, declared ro binds, net/ipc/uts unshared)"
        ),
        "sandbox": sandbox,
        "cgroup": cg,
        "sigchld_inherited": SIGCHLD_INHERITED,
        "cgroup_stats": stats,
        "cgroup_peak_memory_mb": stats.get("memory_peak_mb"),
    }
    oom = stats.get("oom_kill_events") or 0
    reason = None
    if oom:
        reason = "oom_killed"  # دليلٌ من المجموعة، لا استنتاجٌ من SIGKILL
    elif killed:
        reason = "hard_timeout"
    elif rc == 90:
        reason = "readonly_mount_failed"
    elif rc < 0:
        reason = f"killed_by_signal_{-rc}_unattributed"
    elif result["pinned_integrity_after"] != "INTACT":
        reason = "pinned_files_changed"
    elif can_isolate and not neg["reached"]:
        reason = "negative_control_failed"
    elif args.inventory and result.get("file_inventory", {}).get("undeclared"):
        reason = "undeclared_files_opened"
    elif inside_trace and result["file_inventory"]["closure"]["problems"]:
        reason = "closure_incomplete"
    elif closure is not None and sandbox.get("integrity_after") != "INTACT":
        reason = "closure_files_changed"
    if reason or rc != 0:
        result["harness_status"] = "failed"
        if reason:
            result["stage"] = reason
    from perf import evidence_problems  # تعريفٌ واحد للقابليّة، يُعاد حسابُه في perf.py

    result["comparability_problems"] = evidence_problems(result)
    result["performance_comparable"] = not result["comparability_problems"]
    out.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "run": str(out),
                "harness_status": result["harness_status"],
                "stage": result.get("stage"),
                "network_isolation": result.get("network_isolation"),
                "files_readonly": result.get("files_readonly"),
                "performance_comparable": result["performance_comparable"],
                "exit_code": rc,
                "peak_mb": stats.get("memory_peak_mb"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["harness_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
