"""يقيس محرّكاً واحداً — يُشغَّل من ``run.py`` داخل العزل، لا مباشرة.

الترتيب: مجلّدٌ جديد ← البصمات وتغطيتها ← ضابطُ العزل الإيجابيّ ← حارسُ العمليّة ← التحميل ←
طلبٌ بارد ← إحماء ← طلباتٌ دافئة ← تزامن. ``result.json`` يُكتب بعد كلّ مرحلة فيبقى السجلُّ
الجزئيّ إن أُنهيت العمليّة عند المهلة.

الحكم: ``harness_status = ok`` فقط إن نجح **كلُّ** طلبٍ متتابع وتزامنيّ دون خطأٍ أو مهلة، ولم
تُسجَّل أيُّ محاولة اتّصال. أيُّ خلافِ ذلك ``failed`` ورمزُ خروجٍ غيرُ صفريّ.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import importlib.metadata
import ipaddress
import json
import os
import platform
import resource
import signal
import socket
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from audio import AudioRejected, validate_wav  # noqa: E402
from engines import ENGINES, PATH_SETTINGS  # noqa: E402

SCRIPTS = (
    "audio.py",
    "engines.py",
    "worker.py",
    "run.py",
    "blind.py",
    "score.py",
    "perf.py",
    "procs.py",
)
NET_ATTEMPTS: list[str] = []


# ── البصمات ─────────────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: Path) -> str:
    """بصمةُ مجلّد: المساراتُ النسبيّة مرتّبةً مع بصمة كلِّ ملفّ — أيُّ إضافةٍ أو تغييرٍ يغيّرها."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(root)).encode() + b"\0" + sha256_file(path).encode() + b"\n")
    return h.hexdigest()


def verify_manifest(engine: str, cfg: dict, base: Path) -> dict:
    """كلُّ مسارٍ يحمّله المحرّك يقع تحت ملفٍّ أو مجلّدٍ مُعلنٍ ببصمةٍ مطابقة — وإلّا يُرفض قبل الاستيراد."""
    files, trees = cfg.get("files", {}), cfg.get("trees", {})
    if engine != "fake" and not (files or trees):
        raise SystemExit(f"{engine}: بيانٌ بلا ملفّاتٍ مثبّتة — مرفوض")
    verified = {}
    base_real = base.resolve()
    for kind, entries, digest in (("file", files, sha256_file), ("tree", trees, sha256_tree)):
        for rel, expected in entries.items():
            raw = base / rel
            if raw.is_symlink():
                raise SystemExit(f"رابطٌ رمزيّ مرفوض: {rel} — يُثبَّت الملفّ الحقيقيّ لا رابطٌ إليه")
            path = raw.resolve()
            if not path.exists():
                raise SystemExit(f"مفقود: {rel}")
            if base_real not in path.parents:
                raise SystemExit(f"خارج مجلّد البيان: {rel} ⇒ {path}")
            if kind == "file" and not path.is_file():
                raise SystemExit(f"ليس ملفّاً: {rel}")
            if kind == "tree":
                links = [str(p.relative_to(path)) for p in path.rglob("*") if p.is_symlink()]
                if links:
                    raise SystemExit(f"روابطُ رمزيّة داخل {rel} مرفوضة: {links[:3]}")
            if not expected:
                raise SystemExit(f"بلا بصمةٍ مُعلنة: {rel} (الفعليّة {digest(path)})")
            actual = digest(path)
            if actual != expected:
                raise SystemExit(f"بصمةٌ مخالفة: {rel}\n  المُعلنة {expected}\n  الفعليّة {actual}")
            verified[f"{kind}:{rel}"] = actual
    for name, sha in cfg.get("package_assets", {}).items():
        if not (
            isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)
        ):
            raise SystemExit(f"package_assets.{name}: بصمةُ sha256 غيرُ صالحة {sha!r}")
    covered = [(base / r).resolve() for r in list(files) + list(trees)]
    for key in PATH_SETTINGS.get(engine, ()):
        if engine == "fake" and key not in cfg.get("settings", {}):
            continue
        raw = base / cfg["settings"][key]
        if raw.is_symlink():
            raise SystemExit(f"{engine}.settings.{key}: رابطٌ رمزيّ مرفوض")
        target = raw.resolve()
        if not target.exists():
            raise SystemExit(f"{engine}.settings.{key} = {target} غير موجود")
        if not any(target == c or c in target.parents for c in covered):
            raise SystemExit(f"{engine}.settings.{key} = {target} خارج الملفّات المثبّتة")
    return verified


# ── العزل ───────────────────────────────────────────────────────────────────────


def _is_loopback(host) -> bool:
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False  # اسمٌ غير localhost (مثل localhost.evil.example) ليس loopback


#: هدفُ الضابطَين واحد: يجب أن يكون **قابلاً للوصول خارج العزل** (الضابط السلبيّ في run.py يثبته)،
#: وإلّا ففشلُه داخل العزل لا يُميّز شيئاً — كما ثبت مع 1.1.1.1 الذي لا يُبلَغ مباشرةً حتّى خارجه.
CONTROL_HOST = os.environ.get("BAKEOFF_CONTROL_HOST", "pypi.org")
#: عنوانُ الهدف كما حلّله المنسّق **خارج** العزل وبلغه مباشرةً — مسبارٌ لا يمرّ بـDNS، فلا يُنسب «الحجب»
#: إلى غياب /etc/resolv.conf داخل صندوقٍ فارغ (bwrap) بدل غياب الشبكة.
CONTROL_IP = os.environ.get("BAKEOFF_CONTROL_IP", "")


def positive_isolation_control() -> dict:
    """داخل العزل: الاتّصال بهدف الضابط (بالاسم **وبالعنوان مباشرةً**) وتحليل اسمه **يجب** أن تفشل كلُّها."""
    probes = {}
    checks = [
        (
            f"tcp {CONTROL_HOST}:443",
            lambda: socket.create_connection((CONTROL_HOST, 443), timeout=3).close(),
        ),
        (f"dns {CONTROL_HOST}", lambda: socket.getaddrinfo(CONTROL_HOST, 443)),
    ]
    if CONTROL_IP:
        checks.append(
            (
                f"tcp {CONTROL_IP}:443 (بلا DNS)",
                lambda: socket.create_connection((CONTROL_IP, 443), timeout=3).close(),
            )
        )
    for label, fn in checks:
        try:
            fn()
            probes[label] = "REACHED"
        except OSError as exc:
            probes[label] = f"blocked ({type(exc).__name__} {getattr(exc, 'errno', '')})"
    return {"probes": probes, "isolated": all(v.startswith("blocked") for v in probes.values())}


def install_process_guard() -> None:
    """طبقةٌ ثانية داخل بايثون فقط (لا ترى المكتبات الأصليّة) — العزلُ الحقيقيّ من ``run.py``."""
    real_connect, real_connect_ex, real_gai = (
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.getaddrinfo,
    )

    def _host(address):
        return address[0] if isinstance(address, tuple) else None

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(_host(address)):
            NET_ATTEMPTS.append(f"connect {_host(address)}")
            raise OSError("process guard: outbound connect blocked")
        return real_connect(self, address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(_host(address)):
            NET_ATTEMPTS.append(f"connect_ex {_host(address)}")
            return 101  # ENETUNREACH
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            NET_ATTEMPTS.append(f"dns {host}")
            raise socket.gaierror(-3, "process guard: DNS blocked")
        return real_gai(host, *args, **kwargs)

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = (
        connect,
        connect_ex,
        getaddrinfo,
    )
    for var in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[var] = "1"


# ── حدود الموارد: تُقرأ من داخل العمليّة نفسها ─────────────────────────────────────


def verify_limits() -> dict:
    """ما **يسري فعلاً** على هذه العمليّة — من ``/proc/self/cgroup`` وملفّات المجموعة، لا ممّا طُلب.

    ``ENFORCED`` إن طابق المطلوب · ``BLOCKED`` إن لم تتوفّر cgroups أصلاً (يُسجَّل لا يُدّعى) ·
    ``MISMATCH`` إن طُلبت حدودٌ ولم تَسرِ ⇒ يفشل التشغيل.
    """
    requested = json.loads(os.environ.get("BAKEOFF_LIMITS", "{}"))
    seen: dict = {"cpu_affinity": sorted(os.sched_getaffinity(0))}
    try:
        groups = {}
        for line in Path("/proc/self/cgroup").read_text().splitlines():
            _, ctrls, path = line.split(":", 2)
            for c in ctrls.split(","):
                groups[c] = path
        mem = Path("/sys/fs/cgroup/memory") / groups["memory"].lstrip("/")
        cpu = Path("/sys/fs/cgroup/cpu") / groups["cpu"].lstrip("/")
        seen["memory_cgroup"], seen["cpu_cgroup"] = groups["memory"], groups["cpu"]
        seen["memory_limit_mb"] = int((mem / "memory.limit_in_bytes").read_text()) // 2**20
        quota, period = (
            int((cpu / "cpu.cfs_quota_us").read_text()),
            int((cpu / "cpu.cfs_period_us").read_text()),
        )
        seen["cpu_quota"] = None if quota < 0 else quota / period
    except (OSError, KeyError, ValueError) as exc:
        seen["error"] = f"{type(exc).__name__}: {exc}"
    if requested.get("cgroup") != "cgroup-v1":
        return {"status": "BLOCKED", "requested": requested, "in_effect": seen}
    wanted_cores = sorted(int(c) for c in str(requested.get("cpu_cores", "")).split(",") if c)
    ok = (
        seen.get("memory_limit_mb") == requested.get("memory_limit_mb")
        and seen.get("cpu_quota") == requested.get("cpu_quota")
        and (not wanted_cores or seen["cpu_affinity"] == wanted_cores)
    )
    return {"status": "ENFORCED" if ok else "MISMATCH", "requested": requested, "in_effect": seen}


# ── القياس ──────────────────────────────────────────────────────────────────────


def thread_count() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("Threads:"):
            return int(line.split()[1])
    return -1


def p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))] if ordered else None


def stats(values):
    return {
        "n": len(values),
        "median_s": round(statistics.median(values), 3) if values else None,
        "p95_s": round(p95(values), 3) if values else None,
    }


def environment_record(corpus: Path) -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_model": next(
            (
                ln.split(":", 1)[1].strip()
                for ln in open("/proc/cpuinfo")
                if ln.startswith("model name")
            ),
            None,
        ),
        "cpu_visible": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "thread_env": {
            k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "ORT_NUM_THREADS")
        },
        "corpus_sha256": sha256_file(corpus),
        "scripts_sha256": {s: sha256_file(HERE / s) for s in SCRIPTS if (HERE / s).exists()},
        "packages": sorted(
            f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
        ),
        "limits": json.loads(os.environ.get("BAKEOFF_LIMITS", "{}")),
    }


class Run:
    def __init__(self, out: Path, result: dict) -> None:
        self.out, self.result = out, result

    def save(self) -> None:
        tmp = self.out / "result.json.tmp"
        tmp.write_text(json.dumps(self.result, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.out / "result.json")

    def fail(self, status: str, code: int, **extra) -> int:
        self.result.update(
            harness_status="failed", stage=status, network_attempts=NET_ATTEMPTS, **extra
        )
        self.save()
        print(
            json.dumps(
                {k: self.result.get(k) for k in ("engine", "harness_status", "stage", "error")},
                ensure_ascii=False,
            )
        )
        return code


def _measured(engine, text: str):
    """يُنفَّذ **داخل خيط الطلب**: البدءُ والنهايةُ يُسجَّلان حيث يحدث العمل — لا عند جمع النتيجة."""
    t0 = time.perf_counter()
    data = engine.synthesize(text)
    return t0, time.perf_counter(), data


def timed(pool: cf.Executor, engine, text: str, timeout: float):
    t0, t1, data = pool.submit(_measured, engine, text).result(
        timeout=timeout
    )  # TimeoutError للمستدعي
    return data, t1 - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES))
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--corpus", default=str(HERE / "corpus.tsv"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--expect-isolated", action="store_true")
    ap.add_argument("--request-timeout", type=float, default=120.0)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--concurrency", default="1,2,4")
    ap.add_argument("--concurrency-items", type=int, default=6)
    ap.add_argument(
        "--stuck-grace",
        type=float,
        default=1.0,
        help="مهلةٌ إضافيّة بعد مهلة الطلب قبل اعتباره عالقاً وإنهاء التشغيل (الطلبُ يفشل عند مهلته في الحالتين)",
    )
    ap.add_argument(
        "--pinned-dir",
        default=None,
        help="نسخةُ الملفّات المُثبَّتة لهذا التشغيل (يُتحقَّق أنّها للقراءة فقط)",
    )
    args = ap.parse_args()
    # مشغّلٌ ورّث SIGCHLD=SIG_IGN يجعل النواةَ تحصد الأبناءَ فوراً: waitpid ⇒ ECHILD ⇒ returncode = 0 لكلِّ ابن،
    # فيضيع فشلُه (مقيسٌ: 13 حالةَ رفضٍ صارت rc=0). يُعاد إلى الافتراضيّ قبل أيِّ عمليّةٍ فرعيّة، ويُسجَّل الموروث.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print(f"مرفوض: {out} ليس فارغاً — كلُّ تشغيلٍ في مجلّدٍ جديد", file=sys.stderr)
        return 5
    (out / "wav").mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).resolve()
    cfg = json.loads(manifest_path.read_text(encoding="utf-8")).get(args.engine, {})
    corpus_path = Path(args.corpus)
    with corpus_path.open(encoding="utf-8") as fh:
        corpus = list(csv.DictReader(fh, delimiter="\t"))
    run = Run(
        out,
        {
            "run_id": args.run_id,
            "engine": args.engine,
            "harness_status": "running",
            "settings": cfg.get("settings", {}),
            "source": cfg.get("source", {}),
            "environment": environment_record(corpus_path),
        },
    )
    run.save()

    try:
        run.result["verified_files"] = verify_manifest(args.engine, cfg, manifest_path.parent)
        run.result["verified_inside_isolation"] = bool(args.expect_isolated)
    except SystemExit as exc:
        return run.fail("manifest_rejected", 6, error=str(exc))
    control = positive_isolation_control()
    run.result["isolation_control"] = control
    if args.expect_isolated and not control["isolated"]:
        return run.fail("isolation_failed", 3, error="الضابط الإيجابيّ وصل إلى الشبكة داخل العزل")
    run.result["network_isolation"] = "PROVEN" if args.expect_isolated else "BLOCKED"
    limits = verify_limits()
    run.result["resource_limits"] = limits
    if limits["status"] == "MISMATCH":
        return run.fail("limits_not_in_effect", 7, error="الحدود المطلوبة لا تسري على العمليّة")
    if args.pinned_dir:
        probe = Path(args.pinned_dir) / f".write-probe-{os.getpid()}"
        try:
            probe.write_bytes(b"x")
            probe.unlink()
            run.result["files_readonly"] = "BLOCKED" if not args.expect_isolated else "NOT_ENFORCED"
        except OSError as exc:
            run.result["files_readonly"] = (
                "ENFORCED" if exc.errno == 30 else f"UNKNOWN ({exc.errno})"
            )
        if args.expect_isolated and run.result["files_readonly"] != "ENFORCED":
            return run.fail(
                "readonly_not_enforced", 8, error="الملفّات المُثبَّتة قابلةٌ للكتابة داخل العزل"
            )
    install_process_guard()
    run.save()

    settings = {
        k: (
            str((manifest_path.parent / v).resolve())
            if k in PATH_SETTINGS.get(args.engine, ())
            else v
        )
        for k, v in cfg.get("settings", {}).items()
    }
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.perf_counter()
    try:
        engine = ENGINES[args.engine](settings)
    except Exception as exc:  # noqa: BLE001
        return run.fail("load_failed", 2, error=f"{type(exc).__name__}: {exc}")
    run.result["load"] = {
        "seconds": round(time.perf_counter() - t0, 3),
        "threads_after_load": thread_count(),
        "child_pid": getattr(engine, "child_pid", None),
        "child_starttime": getattr(engine, "child_start", None),
        "engine_version": getattr(engine, "version", None),
        "ort": getattr(engine, "ort", None),
        "rss_delta_mb": round(
            (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss0) / 1024, 1
        ),
    }
    run.save()

    rows, cold, warm = [], [], []
    pool = cf.ThreadPoolExecutor(max_workers=1)
    for i, item in enumerate(corpus):
        phase = "cold" if i == 0 else ("warmup" if i <= args.warmup else "warm")
        row = {"id": item["id"], "category": item["category"], "phase": phase}
        try:
            data, wall = timed(pool, engine, item["text"], args.request_timeout)
            if wall > args.request_timeout:
                raise TimeoutError(f"late: اكتمل بعد {wall:.3f}s > المهلة {args.request_timeout}s")
            check = validate_wav(data, item["text"])
            name = f"{item['id']}.wav"
            (out / "wav" / name).write_bytes(data)
            row.update(
                ok=True,
                wall_s=round(wall, 3),
                audio_s=round(check.seconds, 3),
                rtf=round(wall / check.seconds, 3),
                rms=check.rms,
                sha256=hashlib.sha256(data).hexdigest(),
            )
            (cold if phase == "cold" else warm if phase == "warm" else []).append(wall)
        except cf.TimeoutError:
            row.update(ok=False, error=f"timeout > {args.request_timeout}s")
            rows.append(row)
            run.result["sentences"] = rows
            return run.fail(
                "request_timeout", 4, error=f"{item['id']}: timeout"
            )  # الخيط عالق ⇒ إنهاء
        except AudioRejected as exc:
            row.update(ok=False, error=f"audio_rejected: {exc}")
        except TimeoutError as exc:
            row.update(ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            row.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        rows.append(row)
        run.result["sentences"] = rows
        run.save()
    ok_rows = [r for r in rows if r.get("ok")]
    run.result["first_arabic_sentence"] = {
        "id": rows[0]["id"],
        "ok": bool(rows[0].get("ok")),
        "error": rows[0].get("error"),
        "wall_s": rows[0].get("wall_s"),
        "network": run.result.get("network_isolation"),
    }
    run.result["sequential"] = {
        "ok": len(ok_rows),
        "failed": len(rows) - len(ok_rows),
        "cold_request": stats(cold),
        "warm_requests": stats(warm),
        "rtf_warm_median": round(
            statistics.median(r["rtf"] for r in ok_rows if r["phase"] == "warm"), 3
        )
        if any(r["phase"] == "warm" for r in ok_rows)
        else None,
    }
    run.save()

    subset = [c["text"] for c in corpus[: args.concurrency_items]]
    conc_failed = False
    run.result["concurrency"] = {}
    for n in [int(x) for x in args.concurrency.split(",") if x]:
        lat, errors = [], []
        started: dict[int, float] = {}  # رقمُ الطلب ⇒ لحظةُ بدئه الفعليّ داخل خيطه

        def job(i: int, text: str, started: dict = started):
            started[i] = time.perf_counter()
            data = engine.synthesize(text)
            return started[i], time.perf_counter(), data

        start = time.perf_counter()
        cpool = cf.ThreadPoolExecutor(max_workers=n)
        pending = {cpool.submit(job, i, t): (i, t) for i, t in enumerate(subset * n)}
        stuck = []
        while pending and not stuck:
            done, _ = cf.wait(pending, timeout=0.2, return_when=cf.FIRST_COMPLETED)
            for fut in done:
                i, text = pending.pop(fut)
                try:
                    t0, t1, data = fut.result()
                    if t1 - t0 > args.request_timeout:
                        # اكتمل بين جولتَي المراقبة لكن بعد مهلته — لا يُحتسب ناجحاً مهما صحّ صوته.
                        raise TimeoutError(f"late: {t1 - t0:.3f}s > {args.request_timeout}s")
                    validate_wav(data, text)
                    lat.append(t1 - t0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{type(exc).__name__}: {exc}"[:200])
            now = time.perf_counter()
            # مهلةٌ **لكلّ طلب** من بدئه هو — الطلبُ المنتظر دوراً لم يبدأ فلا يُحتسب عليه الانتظار.
            # تجاوزُ المهلة يُفشل الطلب عند اكتماله (``late``)؛ أمّا ما لم يعُد بعد المهلة + السماح فعالقٌ
            # يُنهي التشغيل — فصلُ العتبتين يمنع سباقاً بين «متأخّر» و«عالق» على الطلب نفسه.
            stuck = [
                i
                for i, _ in pending.values()
                if i in started and now - started[i] > args.request_timeout + args.stuck_grace
            ]
        if stuck:
            cpool.shutdown(
                wait=False, cancel_futures=True
            )  # الخيطُ العالق لا يُقتل؛ العمليّةُ تُنهى بعد الكتابة
            run.result["concurrency"][str(n)] = {
                "requests": len(subset) * n,
                "succeeded": len(lat),
                "errors": len(errors),
                "timeouts": len(stuck),
                "timeout_s": args.request_timeout,
            }
            return run.fail(
                "concurrency_timeout",
                4,
                error=f"concurrency {n}: {len(stuck)} طلباً تجاوز {args.request_timeout}s",
            )
        cpool.shutdown(wait=True)
        timeouts = 0
        span = time.perf_counter() - start
        total = len(subset) * n
        run.result["concurrency"][str(n)] = {
            "requests": total,
            "succeeded": len(lat),
            "errors": len(errors),
            "error_samples": errors[:3],
            "timeouts": timeouts,
            "span_s": round(span, 3),
            "throughput_rps": round(len(lat) / span, 3),
            "latency": stats(lat),
        }
        conc_failed |= bool(errors) or len(lat) != total
        run.save()

    run.result["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    run.result["threads_at_end"] = thread_count()
    run.result["network_attempts"] = NET_ATTEMPTS
    failed = len(ok_rows) != len(rows) or conc_failed or bool(NET_ATTEMPTS)
    run.result["harness_status"] = "failed" if failed else "ok"
    run.result["stage"] = "complete"
    run.save()
    print(
        json.dumps(
            {
                "engine": args.engine,
                "harness_status": run.result["harness_status"],
                "network_isolation": run.result["network_isolation"],
                "sequential": run.result["sequential"],
                "network_attempts": NET_ATTEMPTS,
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # خيطٌ عالقٌ بعد مهلة يمنع الخروج العاديّ (خيوط المنفّذ ليست daemon) — النتيجةُ كُتبت قبلُ.
    os._exit(code)
