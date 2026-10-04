"""المُنسِّق: يشغّل ``worker.py`` لمحرّكٍ واحد داخل عزلٍ على مستوى النظام، بحدودٍ ومهلة.

    python3 run.py --engine piper --python venv_piper/bin/python --manifest models.json \\
        --mem-mb 2048 --cpus 2 --hard-timeout 1800

• **الشبكة:** ``unshare -n`` يضع العامل في فضاء شبكةٍ لا يحوي إلّا loopback معطّلاً — يمنع
  المكتباتِ الأصليّة أيضاً، لا بايثون وحدها. ضابطٌ سلبيّ هنا (خارج العزل يصل)، وإيجابيّ داخل
  العامل (داخله لا يصل). إن تعذّر ``unshare`` (لا root أو لا دعم) فالاختبار **BLOCKED** ولا يُدّعى عزل.
• **الموارد:** cgroup v1 (``memory.limit_in_bytes`` و``cpu.cfs_quota_us``) + ``taskset`` للأنوية.
  تُسجَّل الحدود وذروةُ الذاكرة الفعليّة للمجموعة. تعذُّرها يُسجَّل صراحةً لا يُفترض.
• **المهلة:** العاملُ في مجموعة عمليّاتٍ مستقلّة؛ عند ``--hard-timeout`` تُقتل المجموعة كلُّها،
  ويبقى ``result.json`` الجزئيّ (العامل يكتبه بعد كلّ مرحلة).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
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
    for path in ro:
        if not os.path.exists(path):
            continue
        covered = any(
            path != r and path.startswith(r.rstrip("/") + "/") for r in ro if os.path.isdir(r)
        )
        if os.path.islink(path) and not covered:
            # مفسّرٌ عبر رابطٍ خارج المربوط (/usr/local/bin/python3 → /usr/bin/python3.11): يُنشأ الرابطُ وحده
            # داخل الصندوق، لا يُربط مجلّدُه كلّه.
            args += ["--dir", os.path.dirname(path), "--symlink", os.path.realpath(path), path]
            binds.append(f"link:{path}->{os.path.realpath(path)}")
            continue
        args += ["--ro-bind", path, path]
        binds.append(f"ro:{path}")
    for path in dict.fromkeys(rw):
        args += ["--bind", path, path]
        binds.append(f"rw:{path}")
    return args + ["--chdir", str(HERE), "--", *worker], binds


def setup_cgroups(name: str, mem_mb: int, cpus: float) -> dict:
    """يُنشئ مجموعتَي الذاكرة والمعالج. كلُّ مسارٍ يُسجَّل **لحظةَ إنشائه**، فإن فشلت خطوةٌ لاحقة
    (حصّةٌ مرفوضة مثلاً) أُزيل ما أُنشئ فوراً وسُجِّل — لا تبقى مجموعةُ ذاكرةٍ يتيمة خارج التنظيف."""
    info = {"backend": None, "memory_limit_mb": mem_mb, "cpu_quota": cpus, "paths": []}
    mem, cpu = CG / "memory" / name, CG / "cpu" / name
    created: list[str] = []
    try:
        mem.mkdir()
        created.append(str(mem))
        (mem / "memory.limit_in_bytes").write_text(str(mem_mb * 1024 * 1024))
        cpu.mkdir()
        created.append(str(cpu))
        (cpu / "cpu.cfs_period_us").write_text("100000")
        (cpu / "cpu.cfs_quota_us").write_text(str(int(cpus * 100000)))
        info.update(backend="cgroup-v1", paths=created)
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


def cgroup_stats(info: dict) -> dict:
    """تُقرأ **قبل** إزالة المجموعة: ذروةُ الذاكرة، وأحداثُ OOM، والتباطؤُ بسبب الحصّة."""
    stats: dict = {"cgroup_version": "v1" if info.get("paths") else None}
    if not info.get("paths"):
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
    for line in log.read_text(errors="replace").splitlines():
        m = re.search(r'open(?:at2?)?\((?:[^,]+, )?"([^"]+)"', line)
        if m and "ENOENT" not in line and "ENOTDIR" not in line:
            opened.add(m.group(1))
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
        elif real.startswith(SYSTEM_ROOTS) or real in ("/dev/null",):
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
    try:
        cfg, pinned_manifest = pin_files(args.engine, Path(args.manifest).resolve(), pinned)
    except SystemExit as exc:
        out.mkdir(parents=True)
        result = {
            "run_id": run_id,
            "engine": args.engine,
            "harness_status": "failed",
            "stage": "manifest_rejected",
            "error": str(exc),
        }
        (out / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {"run": str(out), "harness_status": "failed", "stage": "manifest_rejected"},
                ensure_ascii=False,
            )
        )
        return 1
    from worker import sha256_file, sha256_tree

    def pinned_digests() -> dict:
        return {
            **{f"file:{r}": sha256_file(pinned / r) for r in cfg.get("files", {})},
            **{f"tree:{r}": sha256_tree(pinned / r) for r in cfg.get("trees", {})},
        }

    before = pinned_digests()

    # جذورُ بيئة بايثون كما يراها **مفسّرُ المحرّك نفسه** (sys.path + prefix)، لا تخميناً — للجرد ولربط bwrap.
    probe = subprocess.run(
        [
            args.python,
            "-c",
            "import sys,json;print(json.dumps([p for p in sys.path if p]"
            "+[sys.prefix,sys.base_prefix]))",
        ],
        capture_output=True,
        text=True,
    )
    # sys.prefix يُستبعد إن كان جذرَ نظام (/usr · /usr/local · /): ربطُه في bwrap يُعيد كشفَ /usr/share كلّه،
    # وعدُّه «بيئة بايثون» في الجرد يُصنّف كلَّ /usr تحتها. مداخلُ sys.path نفسُها محدّدةٌ بما يكفي.
    py_roots = sorted(
        {
            p.rstrip("/") + "/"
            for p in json.loads(probe.stdout or "[]")
            if p and p.rstrip("/") not in ("", "/usr", "/usr/local")
        }
    )
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
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.lower().endswith("_proxy") and "TOKEN" not in k.upper()
    }
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
    sandbox = {"kind": args.sandbox, "probe": isolation_probe[1]}
    if args.sandbox == "bwrap" and can_isolate:
        out.mkdir(parents=True, exist_ok=True)
        ro = [
            *BWRAP_SYSTEM_RO,
            *[r.rstrip("/") for r in py_roots],
            args.python,
            str(HERE),
            str(pinned),
        ]
        bw, binds = bwrap_command([*inner, "--expect-isolated"], ro, [str(out)])
        sandbox.update(
            binds=binds,
            version=subprocess.run(
                ["bwrap", "--version"], capture_output=True, text=True
            ).stdout.strip(),
        )
        inner = bw
    worker = ["taskset", "-c", cores, *inner]
    if args.inventory:
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
    if args.inventory and trace.exists():
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
