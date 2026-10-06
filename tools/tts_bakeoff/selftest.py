"""فحصُ الأداة نفسها بحقن الأعطال المعروفة — كلُّ حالةٍ يجب أن تنتهي بالحكم المتوقّع.

    sudo python3 selftest.py        # root لازمٌ لعزل الشبكة وcgroups؛ بدونه تُسجَّل الحالاتُ BLOCKED

هذا يُثبت سلوكَ الأداة فقط. **لا يقيس أيَّ محرّكٍ حقيقيّ ولا يُثبت مقارنة.**
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import procs
import run as run_mod

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RESULTS: list[tuple[str, str, str]] = []


def run(
    mode: str,
    root: Path,
    *worker_args: str,
    isolation=True,
    hard_timeout=120,
    engine="fake",
    manifest: dict | None = None,
    mem_mb=1024,
    settings: dict | None = None,
    cpus="1",
    coord: tuple = (),
    sigchld_ign: bool = False,
) -> tuple[int, dict]:
    man = root / f"manifest-{mode}.json"
    man.write_text(
        json.dumps(
            manifest or {"fake": {"files": {}, "settings": {"mode": mode, **(settings or {})}}}
        ),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        str(HERE / "run.py"),
        "--engine",
        engine,
        "--manifest",
        str(man),
        "--runs-root",
        str(root / "runs"),
        "--mem-mb",
        str(mem_mb),
        "--cpus",
        str(cpus),
        *coord,
        "--hard-timeout",
        str(hard_timeout),
    ] + ([] if isolation else ["--no-isolation"])
    cmd += ["--", "--concurrency-items", "3", "--warmup", "1", *worker_args]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        preexec_fn=(lambda: signal.signal(signal.SIGCHLD, signal.SIG_IGN)) if sigchld_ign else None,
    )
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    result = json.loads((Path(summary["run"]) / "result.json").read_text(encoding="utf-8"))
    result["_run_dir"] = summary["run"]
    return proc.returncode, result


def probe_host() -> dict:
    """ما يسمح به المضيفُ **فعلاً** — بإنشاءٍ حقيقيّ لا بوجود الأدوات: v12 كان يستنتج العزلَ من root ووجود unshare،
    فعلى مضيفٍ root بلا صلاحيّات (CapEff=0) ظنّ العزلَ متاحاً ثمّ انهار عند أوّل رفض (مراجعةُ المالك)."""
    from run import cgroup_hierarchy, setup_cgroups, teardown_cgroups

    caps = {}
    if shutil.which("unshare"):
        caps["netns"] = procs.probe(["unshare", "-n", "-m", "true"])
    else:
        caps["netns"] = (False, "unshare غيرُ موجود")
    # الهرمُ **المُركَّب فعلاً** لا v1 وحدها: WSL2 وUbuntu 22.04+ على v2، وكان ذلك يحجب
    # ستَّ حالاتٍ لسببٍ واحد (قياسُ المالك على نواة 6.6). يُسجَّل أيُّ هرمٍ قِيس عليه.
    info = setup_cgroups(f"bakeoff-probe-{os.getpid()}", 64, 1.0)
    caps["cgroup"] = (
        info["backend"] in ("cgroup-v1", "cgroup-v2"),
        f"{info['backend']} ({cgroup_hierarchy()}) {info.get('error', 'ok')}",
    )
    teardown_cgroups(info)
    if shutil.which("bwrap"):
        caps["bwrap"] = procs.bwrap_probe(
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
    else:
        caps["bwrap"] = (False, "bwrap غيرُ موجود")
    return caps


def check(name: str, condition: bool, detail: str) -> None:
    RESULTS.append(("PASS" if condition else "FAIL", name, detail))


def survivors(identities: dict) -> tuple[str, dict]:
    """هل بقي أحدٌ من {pid: زمنِ بدئه} حيّاً؟ — بهويّته وفي فضاء PID المختبِر (procs)، لا بقراءة /proc/<رقم> عمياء:
    في فضاءٍ آخر ذلك الرقمُ عمليّةٌ أخرى (مراجعةُ المالك على v13). ما بعد SIGKILL: يختفي أو يصير زومبي — كلاهما منتهٍ.
    ⇒ ("alive" | "unverifiable" | "gone"، الحكمُ لكلّ رقم)."""
    import time as _tm

    states = {}
    for _ in range(20):
        states = {
            int(pid): procs.pid_status(int(pid), start)[0] for pid, start in identities.items()
        }
        if "alive" not in states.values():
            break
        _tm.sleep(0.1)
    worst = next((w for w in ("alive", "unverifiable") if w in states.values()), "gone")
    return worst, states


def check_killed(name: str, condition: bool, identities: dict, detail: str) -> None:
    """FAIL إن لم يتحقّق الشرط أو بقي أحدٌ حيّاً؛ BLOCKED إن تعذّر الحكمُ في هذا الفضاء — لا نجاحاً ولا بقاءً."""
    worst, states = survivors(identities)
    status = (
        "FAIL"
        if not condition or worst == "alive"
        else "BLOCKED"
        if worst == "unverifiable"
        else "PASS"
    )
    RESULTS.append((status, name, f"{detail} survivors={worst} {states}"))


def main() -> int:
    # مشغّلٌ ورّث SIGCHLD=SIG_IGN يجعل النواةَ تحصد الأبناءَ فوراً: waitpid ⇒ ECHILD ⇒ returncode = 0 لكلِّ ابن،
    # فيضيع فشلُه (مقيسٌ: 13 حالةَ رفضٍ صارت rc=0). يُعاد إلى الافتراضيّ قبل أيِّ عمليّةٍ فرعيّة، ويُسجَّل الموروث.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    caps = probe_host()
    print(
        "المضيف:",
        " · ".join(f"{k}={'نعم' if ok else 'لا'} ({why})" for k, (ok, why) in caps.items()),
        flush=True,
    )
    isolated, limits, bwrap_ok = caps["netns"][0], caps["cgroup"][0], caps["bwrap"][0]
    root = Path(tempfile.mkdtemp(prefix="bakeoff-selftest-"))
    net_expect = "PROVEN" if isolated else "BLOCKED"

    rc, r = run("ok", root)
    check(
        "سليم ⇒ ok ورمز 0",
        rc == 0 and r["harness_status"] == "ok",
        f"rc={rc} status={r['harness_status']} net={r.get('network_isolation')}",
    )
    check(
        f"عزل الشبكة = {net_expect}",
        r.get("network_isolation") == net_expect,
        f"control={r.get('isolation_control')} negative={r['coordinator']['negative_control']}",
    )
    good_run = r["_run_dir"]

    rc, r = run("fail_concurrent", root)
    conc = r.get("concurrency", {})
    check(
        "فشلُ كلِّ طلبات التزامن ⇒ failed ورمز ≠ 0",
        rc != 0 and r["harness_status"] == "failed",
        f"rc={rc} errors={[v.get('errors') for v in conc.values()]}",
    )

    for mode, needle in (("header_only", "بلا عيّنات"), ("truncated", "مبتور"), ("silent", "صمت")):
        rc, r = run(mode, root)
        errs = [s.get("error", "") for s in r.get("sentences", [])]
        check(
            f"{mode} ⇒ مرفوض",
            rc != 0 and r["harness_status"] == "failed" and all(needle in e for e in errs),
            f"rc={rc} مرفوض {sum(needle in e for e in errs)}/{len(errs)}",
        )

    rc, r = run("hang", root, "--request-timeout", "2")
    check(
        "طلبٌ عالق ⇒ مهلةُ الطلب تُنهيه",
        rc != 0 and r.get("stage") == "request_timeout",
        f"rc={rc} stage={r.get('stage')}",
    )

    rc, r = run("hang", root, "--request-timeout", "999", hard_timeout=8)
    check(
        "مهلةٌ صلبة ⇒ قتلُ المجموعة مع سجلٍّ جزئيّ",
        r["coordinator"]["killed_at_hard_timeout"]
        and r.get("stage") == "hard_timeout"
        and "environment" in r,
        f"killed={r['coordinator']['killed_at_hard_timeout']} stage={r.get('stage')}",
    )

    rc, r = run("net_on_load", root)
    check(
        "اتّصالُ بايثون عند التحميل ⇒ load_failed (طبقةُ حارس العمليّة)",
        r.get("stage") == "load_failed",
        f"stage={r.get('stage')} error={str(r.get('error'))[:70]}",
    )

    if isolated:
        # الدليلُ على عزل النظام: عمليّةٌ أصليّة مباشرة (بلا وكيل) لا يراها حارسُ بايثون.
        rc_in, r_in = run("net_native_on_load", root)
        rc_out, r_out = run("net_native_on_load", root, isolation=False)
        check(
            "عمليّةٌ أصليّة داخل العزل لا تصل ⇒ التشغيل ok",
            rc_in == 0
            and r_in["harness_status"] == "ok"
            and r_in.get("network_isolation") == "PROVEN",
            f"rc={rc_in} status={r_in['harness_status']} stage={r_in.get('stage')}",
        )
        check(
            "الضابط: نفسُ العمليّة بلا عزلٍ تصل ⇒ load_failed و BLOCKED",
            r_out.get("stage") == "load_failed"
            and "REACHED" in str(r_out.get("error"))
            and r_out.get("network_isolation") == "BLOCKED",
            f"stage={r_out.get('stage')} net={r_out.get('network_isolation')} error={str(r_out.get('error'))[:60]}",
        )
    else:
        RESULTS.append(
            ("BLOCKED", "عزلُ العمليّات الأصليّة", f"المضيفُ لا يُنشئ namespace: {caps['netns'][1]}")
        )

    stale = root / "stale"
    (stale / "wav").mkdir(parents=True)
    (stale / "wav" / "C01.wav").write_bytes(b"old")
    p = subprocess.run(
        [
            sys.executable,
            str(HERE / "worker.py"),
            "--engine",
            "fake",
            "--manifest",
            str(root / "manifest-ok.json"),
            "--out",
            str(stale),
            "--run-id",
            "x",
        ],
        capture_output=True,
        text=True,
    )
    check("مجلّدٌ قديم غير فارغ ⇒ مرفوض", p.returncode == 5, f"rc={p.returncode}")

    def blind(*runs: str, extra=()) -> int:
        out = root / f"review-{len(RESULTS)}"
        return subprocess.run(
            [sys.executable, str(HERE / "blind.py"), *runs, "--out", str(out), *extra],
            capture_output=True,
            text=True,
        ).returncode

    failed_run = run("fail_concurrent", root)[1]["_run_dir"]
    check("blind يرفض تشغيلاً فاشلاً", blind(good_run, failed_run) != 0, "")
    # يُشتقّ من السجلّ المرجعيّ نفسه لا من افتراضٍ عن المضيف: سجلٌّ عزلُه غيرُ مُثبت يحتاج العلَمَ الصريح
    good_net = json.loads((Path(good_run) / "result.json").read_text(encoding="utf-8")).get(
        "network_isolation"
    )
    extra_flag = () if good_net == "PROVEN" else ("--allow-unverified-network",)
    tampered = root / "tampered"
    shutil.copytree(good_run, tampered)
    (tampered / "wav" / "C01.wav").write_bytes((tampered / "wav" / "C01.wav").read_bytes()[:-10])
    check("blind يرفض مقطعاً تغيّرت بايتاته", blind(str(tampered), extra=extra_flag) != 0, "")
    stray = root / "stray"
    shutil.copytree(good_run, stray)
    shutil.copyfile(stray / "wav" / "C01.wav", stray / "wav" / "OLD99.wav")
    check("blind يرفض مقطعاً غير مُسجَّل", blind(str(stray), extra=extra_flag) != 0, "")
    check("blind يقبل التشغيل السليم", blind(good_run, extra=extra_flag) == 0, "")

    rc, r = run(
        "x",
        root,
        engine="piper",
        manifest={"piper": {"files": {}, "settings": {"model": "m.onnx", "config": "m.onnx.json"}}},
    )
    check(
        "محرّكٌ حقيقيّ ببيانٍ فارغ ⇒ مرفوض قبل الاستيراد",
        r.get("stage") == "manifest_rejected",
        f"stage={r.get('stage')}",
    )
    (root / "a.onnx").write_bytes(b"x")
    import worker

    digest = worker.sha256_file(root / "a.onnx")
    (root / "elsewhere.json").write_text("{}", encoding="utf-8")  # موجودٌ فعلاً لكنّه غير مُثبَّت
    rc, r = run(
        "y",
        root,
        engine="piper",
        manifest={
            "piper": {
                "files": {"a.onnx": digest},
                "settings": {"model": "a.onnx", "config": "elsewhere.json"},
            }
        },
    )
    check(
        "مسارُ إعدادٍ موجودٌ لكنّه خارج الملفّات المثبّتة ⇒ مرفوض",
        r.get("stage") == "manifest_rejected" and "خارج الملفّات المثبّتة" in str(r.get("error")),
        f"stage={r.get('stage')} error={str(r.get('error'))[-60:]}",
    )

    check(
        "حارس العمليّة: localhost.evil.example ليس loopback",
        not worker._is_loopback("localhost.evil.example")
        and worker._is_loopback("127.0.0.1")
        and worker._is_loopback("::1"),
        "",
    )

    # ── الإصدار 3 ────────────────────────────────────────────────────────────────
    rc, r = run("fail_when_parallel", root)
    seq, conc = r.get("sequential", {}), r.get("concurrency", {})
    check(
        "v3 فشلُ التزامن وحده (المتتابع سليم 27/27) ⇒ failed ورمز ≠ 0",
        rc != 0
        and r["harness_status"] == "failed"
        and seq.get("ok") == 27
        and seq.get("failed") == 0
        and conc.get("1", {}).get("errors") == 0
        and conc.get("2", {}).get("errors", 0) > 0,
        f"rc={rc} seq={seq.get('ok')}/27 errors 1/2/4={[conc.get(k, {}).get('errors') for k in ('1', '2', '4')]}",
    )

    import time as _t

    t0 = _t.monotonic()
    rc, r = run("hang_when_parallel", root, "--request-timeout", "2", hard_timeout=120)
    took = _t.monotonic() - t0
    check(
        "v3 طلبٌ متزامن عالق ⇒ مهلتُه الخاصّة تُنهي التشغيل دون انتظار الخيط",
        r.get("stage") == "concurrency_timeout"
        and r.get("sequential", {}).get("ok") == 27
        and not r["coordinator"]["killed_at_hard_timeout"]
        and took < 60,
        f"stage={r.get('stage')} seq={r.get('sequential', {}).get('ok')} took={took:.1f}s",
    )

    rc, r = run("sleep", root)
    c4 = r.get("concurrency", {}).get("4", {}).get("latency", {})
    warm = r.get("sequential", {}).get("warm_requests", {})
    check(
        "v3 الكمون يُقاس داخل خيط الطلب (≈0.3ث لا تراكمُ الطابور)",
        rc == 0
        and c4.get("median_s") is not None
        and 0.28 <= c4["median_s"] < 0.6
        and 0.28 <= (warm.get("median_s") or 0) < 0.6,
        f"conc4 median={c4.get('median_s')} p95={c4.get('p95_s')} warm median={warm.get('median_s')}",
    )

    if limits:  # حدودُ الموارد تحتاج هرمَ cgroup (v1 أو v2) قابلاً للكتابة — لا عزلَ الشبكة
        rc, r = run("ok", root)
        lim = r.get("resource_limits", {})
        check(
            "v3 حدودُ الموارد مقروءةٌ من داخل العمليّة = المطلوب (ENFORCED)",
            lim.get("status") == "ENFORCED"
            and lim["in_effect"].get("memory_limit_mb") == 1024
            and lim["in_effect"].get("cpu_quota") == 1.0,
            f"status={lim.get('status')} in_effect={ {k: lim.get('in_effect', {}).get(k) for k in ('memory_limit_mb', 'cpu_quota', 'cpu_affinity')} }",
        )
        rc, r = run("alloc", root, mem_mb=256, settings={"alloc_mb": 600})
        check(
            "v3 تجاوزُ حدّ الذاكرة يُقتل فعلاً ⇒ oom_killed",
            r.get("stage") == "oom_killed"
            and (r["coordinator"]["cgroup_stats"].get("oom_kill_events") or 0) >= 1,
            f"stage={r.get('stage')} oom={r['coordinator']['cgroup_stats'].get('oom_kill_events')} peak={r['coordinator'].get('cgroup_peak_memory_mb')}MB",
        )
        env = dict(
            os.environ,
            BAKEOFF_LIMITS=json.dumps(
                {
                    "cgroup": f"cgroup-{run_mod.cgroup_hierarchy()}",
                    "memory_limit_mb": 999,
                    "cpu_quota": 1.0,
                    "cpu_cores": "0",
                }
            ),
        )
        p = subprocess.run(
            [
                sys.executable,
                str(HERE / "worker.py"),
                "--engine",
                "fake",
                "--manifest",
                str(root / "manifest-ok.json"),
                "--out",
                str(root / "mismatch"),
                "--run-id",
                "m",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        mm = json.loads((root / "mismatch" / "result.json").read_text(encoding="utf-8"))
        check(
            "v3 حدودٌ مُدّعاة لا تسري ⇒ limits_not_in_effect",
            p.returncode == 7 and mm.get("stage") == "limits_not_in_effect",
            f"rc={p.returncode} stage={mm.get('stage')} status={mm.get('resource_limits', {}).get('status')}",
        )
    else:
        RESULTS.append(
            ("BLOCKED", "v3 حدود الموارد", f"لا هرمَ cgroup قابلاً للكتابة: {caps['cgroup'][1]}")
        )

    # البيان: مساراتٌ غير موجودة وروابطُ رمزيّة
    real = root / "real.onnx"
    real.write_bytes(b"model")
    outside = Path(tempfile.mkdtemp(prefix="outside-")) / "secret.bin"
    outside.write_bytes(b"outside")
    dig = worker.sha256_file(real)
    (root / "link.onnx").symlink_to(real)
    tree = root / "vtree"
    tree.mkdir()
    (tree / "ok.bin").write_bytes(b"x")
    (tree / "escape.bin").symlink_to(outside)
    cases = {
        "مسارُ إعدادٍ غير موجود": {
            "files": {"real.onnx": dig},
            "settings": {"model": "real.onnx", "config": "real.onnx.missing"},
        },
        "ملفٌّ مُثبَّت هو رابطٌ رمزيّ": {
            "files": {"link.onnx": dig},
            "settings": {"model": "link.onnx", "config": "link.onnx"},
        },
        "رابطٌ داخل مجلّدٍ مُثبَّت يخرج منه": {
            "trees": {"vtree": "0" * 64},
            "settings": {"model": "vtree/ok.bin", "config": "vtree/escape.bin"},
        },
    }
    for label, spec in cases.items():
        rc, r = run(f"manifest-{abs(hash(label))}", root, engine="piper", manifest={"piper": spec})
        check(
            f"v3 {label} ⇒ مرفوض قبل الاستيراد",
            r.get("stage") == "manifest_rejected",
            f"error={str(r.get('error'))[-70:]}",
        )

    # التقييم: بصمةُ النصوص، والمراجعُ المكرّر، والصفُّ المعدَّل
    other = root / "corpus_modified.tsv"
    other.write_text(
        (HERE / "corpus.tsv").read_text(encoding="utf-8").replace("2.5 مل", "25 مل"),
        encoding="utf-8",
    )
    check(
        "v3 blind يرفض نصوصاً بصمتُها تخالف ما قِيس عليه التشغيل",
        blind(good_run, extra=extra_flag + ("--corpus", str(other))) != 0,
        "",
    )
    review = root / "review-score"
    p = subprocess.run(
        [sys.executable, str(HERE / "blind.py"), good_run, "--out", str(review), *extra_flag],
        capture_output=True,
        text=True,
    )
    check(
        "blind يُعدّ جولةَ تقييمٍ من التشغيل المرجعيّ (أساسُ حالات score التالية)",
        p.returncode == 0,
        f"rc={p.returncode} net={good_net} {p.stderr.strip()[-90:]}",
    )
    if p.returncode != 0:  # بلا جولةٍ لا معنى لحالات score: تُسجَّل محجوبةً لا انهياراً
        RESULTS.append(("BLOCKED", "حالاتُ score.py", "لم تُعدّ جولةُ التقييم المرجعيّة"))
        return finish()
    import csv as _csv

    rows = list(
        _csv.DictReader((review / "rating_sheet.csv").read_text(encoding="utf-8-sig").splitlines())
    )
    crit = next(c for c in rows[0] if c.startswith("خطأ حرج"))

    def sheet(name: str, reviewer: str, mutate=None) -> str:
        out = [
            dict(
                r, reviewer_id=reviewer, **{crit: "لا", "الوضوح (1-5)": "4", "الطبيعيّة (1-5)": "3"}
            )
            for r in rows
        ]
        if mutate:
            mutate(out)
        path = root / name
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = _csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(out)
        return str(path)

    def score(*sheets: str) -> tuple[int, dict | None]:
        p = subprocess.run(
            [sys.executable, str(HERE / "score.py"), str(review), *sheets],
            capture_output=True,
            text=True,
        )
        return p.returncode, (
            json.loads(p.stdout)["engines"]["fake"] if p.returncode == 0 else None
        )

    a, b = sheet("a.csv", "rev-A"), sheet("b.csv", "rev-B")
    a_copy = root / "a_copy.csv"
    shutil.copyfile(a, a_copy)
    d03 = next(r["blind_id"] for r in rows if r["sentence_id"] == "D03")
    rc_ok, rep_ok = score(a, b)
    check(
        "v3 score: مراجعان مختلفان سليمان ⇒ PASSED_SAFETY_GATE",
        rc_ok == 0 and rep_ok["verdict"] == "PASSED_SAFETY_GATE",
        f"verdict={rep_ok and rep_ok['verdict']}",
    )
    check("v3 score: الورقة نفسها مرّتين ⇒ مرفوض", score(a, str(a_copy))[0] != 0, "")
    check(
        "v3 score: المراجع نفسه في ورقتين مختلفتين ⇒ مرفوض",
        score(a, sheet("a2.csv", "rev-A", lambda o: o[0].update({"ملاحظات": "x"})))[0] != 0,
        "",
    )
    check("v3 score: reviewer_id فارغ ⇒ مرفوض", score(a, sheet("anon.csv", ""))[0] != 0, "")
    check(
        "v3 score: صفٌّ مكرّر في الورقة ⇒ مرفوض",
        score(a, sheet("dup.csv", "rev-D", lambda o: o.append(dict(o[0]))))[0] != 0,
        "",
    )
    check(
        "v3 score: نصٌّ أو حقائقُ معدّلة في الورقة ⇒ مرفوض",
        score(
            a,
            sheet(
                "edited.csv",
                "rev-E",
                lambda o: o[0].update({"الحقائق الحرجة (يجب أن تُسمع حرفيّاً)": "عُدِّل"}),
            ),
        )[0]
        != 0,
        "",
    )
    rc_c, rep_c = score(
        a,
        sheet(
            "crit.csv",
            "rev-C",
            lambda o: [
                r.update({crit: "نعم", "وصف الخطأ الحرج": "25 بدل 2.5"})
                for r in o
                if r["blind_id"] == d03
            ],
        ),
    )
    check(
        "v3 score: خطأ حرج واحد ⇒ REJECTED",
        rep_c and rep_c["verdict"] == "REJECTED",
        f"verdict={rep_c and rep_c['verdict']}",
    )
    rc_1, rep_1 = score(a)
    check(
        "v3 score: مراجعٌ واحد فقط ⇒ INCOMPLETE",
        rep_1 and rep_1["verdict"] == "INCOMPLETE",
        f"verdict={rep_1 and rep_1['verdict']} under={rep_1 and rep_1['clips_under_min_reviewers']}",
    )

    # ── الإصدار 4 — بوّابةُ المالك ────────────────────────────────────────────────
    rc, r = run(
        "slow_when_parallel",
        root,
        "--request-timeout",
        "0.25",
        "--concurrency",
        "1,2",
        "--concurrency-items",
        "1",
    )
    c2 = r.get("concurrency", {}).get("2", {})
    check(
        "v4 طلبٌ يكتمل بعد مهلته يُرفض ولو أعاد WAV صالحاً",
        rc != 0
        and r["harness_status"] == "failed"
        and r.get("stage") == "complete"
        and c2.get("errors", 0) >= 1
        and all("late" in e for e in c2.get("error_samples", []))
        and r.get("sequential", {}).get("ok") == 27,
        f"stage={r.get('stage')} conc2 errors={c2.get('errors')} sample={c2.get('error_samples', [''])[:1]}",
    )

    rc, r = run("hang_with_child", root, hard_timeout=8)
    load = r.get("load", {})
    child = load.get("child_pid")
    check_killed(
        "v4 عاملٌ عالق وأبناؤه يُنهَون، ويبقى السجلّ الجزئيّ",
        r.get("stage") == "hard_timeout" and bool(child) and "load" in r and "environment" in r,
        {child: load.get("child_starttime")} if child else {},
        f"stage={r.get('stage')} child={child} killed={r['coordinator'].get('killed_pids')}",
    )

    # المقارنةُ تحتاج العزلَ **و**الحدودَ **و**جذراً فارغاً (bwrap): unshare يكشف نظامَ ملفّات المضيف (مراجعةُ
    # Copilot على #1133) فلا يُثبَت أنّ المحرّك لم يقرأ إلّا المعلَن.
    full = isolated and limits and bwrap_ok
    why = f"netns={caps['netns'][1]} · cgroup={caps['cgroup'][1]} · bwrap={caps['bwrap'][1]}"
    comparable_ref = None
    if full:
        sandbox = ("--sandbox", "bwrap")
        _, r_a = run("ok", root, coord=sandbox)
        _, r_b = run("ok", root, coord=sandbox)
        _, r_blk = run("ok", root, isolation=False)
        _, r_lim = run("ok", root, cpus="0.5", coord=sandbox)
        _, r_un = run("ok", root)  # unshare: عزلٌ وحدودٌ كاملة، لكنّ نظامَ الملفّات مكشوف
        comparable_ref = r_a

        def perf(*runs) -> int:
            return subprocess.run(
                [sys.executable, str(HERE / "perf.py"), *[x["_run_dir"] for x in runs]],
                capture_output=True,
                text=True,
            ).returncode

        check(
            "v4 تشغيلان قابلان للمقارنة بالشروط نفسها ⇒ perf يقبل",
            r_a.get("performance_comparable") and perf(r_a, r_b) == 0,
            f"comparable={r_a.get('performance_comparable')}",
        )
        check(
            "v4 BLOCKED في العزل/الملفّات يمنع مقارنة الأداء",
            r_blk.get("performance_comparable") is False and perf(r_a, r_blk) != 0,
            f"net={r_blk.get('network_isolation')} ro={r_blk.get('files_readonly')}",
        )
        check(
            "v4 حدودٌ مختلفة بين التشغيلات تمنع المقارنة", perf(r_a, r_lim) != 0, "cpus 1 مقابل 0.5"
        )
        un_why = " ".join(r_un.get("comparability_problems") or [])
        check(
            "v14 تشغيلُ unshare (عزلٌ وحدودٌ كاملة) غيرُ قابلٍ للمقارنة: نظامُ ملفّات المضيف مكشوف ⇒ perf يرفض",
            r_un.get("harness_status") == "ok"
            and r_un.get("network_isolation") == "PROVEN"
            and r_un.get("performance_comparable") is False
            and "bwrap" in un_why
            and perf(r_a, r_un) != 0,
            f"status={r_un.get('harness_status')} comparable={r_un.get('performance_comparable')} "
            f"problems={un_why[:90]}",
        )
    else:
        RESULTS.append(("BLOCKED", "v4 بوّابة مقارنة الأداء", why))

    model = root / "pinned_model.bin"
    model.write_bytes(b"pinned-model-bytes")
    mdig = worker.sha256_file(model)
    tamper_manifest = {
        "fake": {
            "files": {"pinned_model.bin": mdig},
            "settings": {"mode": "tamper", "model": "pinned_model.bin"},
        }
    }
    if isolated:
        rc, r = run("tamper", root, manifest=tamper_manifest)
        check(
            "v4 محاولةُ تعديل نموذجٍ مُثبَّت داخل العزل تُرفض (للقراءة فقط حتّى لـroot)",
            r.get("stage") == "load_failed"
            and "Read-only" in str(r.get("error"))
            and r.get("pinned_integrity_after") == "INTACT"
            and r.get("verified_inside_isolation") is True,
            f"error={str(r.get('error'))[:60]} integrity={r.get('pinned_integrity_after')}",
        )
    rc, r = run("tamper", root, manifest=tamper_manifest, isolation=False)
    check(
        "v4 بلا عزلٍ ينجح التعديل ⇒ تكشفه المطابقةُ بعد التشغيل (pinned_files_changed)",
        r.get("stage") == "pinned_files_changed"
        and r.get("files_readonly") == "BLOCKED"
        and worker.sha256_file(model) == mdig,
        f"stage={r.get('stage')} ro={r.get('files_readonly')} original_intact={worker.sha256_file(model) == mdig}",
    )
    model.write_bytes(b"changed-after-pinning")
    rc, r = run(
        "ok",
        root,
        manifest={
            "fake": {
                "files": {"pinned_model.bin": mdig},
                "settings": {"mode": "ok", "model": "pinned_model.bin"},
            }
        },
    )
    check(
        "v4 نموذجٌ تغيّر بعد كتابة بصمته ⇒ مرفوضٌ قبل الإطلاق",
        r.get("stage") == "manifest_rejected",
        f"error={str(r.get('error'))[:50]}",
    )

    if isolated and limits:  # الحصّةُ والجرد: namespace وcgroup — لا تحتاج bwrap
        _, r_full = run("busy", root, "--concurrency", "1", "--concurrency-items", "2", cpus="1")
        _, r_half = run(
            "busy",
            root,
            "--concurrency",
            "1",
            "--concurrency-items",
            "2",
            cpus="0.5",
            coord=("--cores", "1"),
        )
        s_full, s_half = (
            r_full["coordinator"]["cgroup_stats"],
            r_half["coordinator"]["cgroup_stats"],
        )
        lim = r_half.get("resource_limits", {})
        check(
            "v4 تُسجَّل الحصّةُ والأنويةُ والخيوطُ والتباطؤُ وذروةُ الذاكرة — والحصّةُ تُبطئ فعلاً",
            s_half.get("cpu_throttled_ratio", 0) > 0.2
            and s_full.get("cpu_throttled_ratio", 1) < s_half["cpu_throttled_ratio"]
            and lim.get("in_effect", {}).get("cpu_quota") == 0.5
            and lim["in_effect"].get("cpu_affinity") == [0]
            and r_half.get("threads_at_end", 0) > 0
            and s_half.get("memory_peak_mb", 0) > 0
            and r_half["sequential"]["warm_requests"]["median_s"]
            > r_full["sequential"]["warm_requests"]["median_s"],
            f"throttled 1.0={s_full.get('cpu_throttled_ratio')} 0.5={s_half.get('cpu_throttled_ratio')} "
            f"warm 1.0={r_full['sequential']['warm_requests']['median_s']}s 0.5={r_half['sequential']['warm_requests']['median_s']}s "
            f"threads={r_half.get('threads_at_end')} peak={s_half.get('memory_peak_mb')}MB",
        )

        rc, r = run("ok", root, coord=("--inventory",))
        inv = r.get("file_inventory", {})
        check(
            "v4 أوّلُ جملةٍ عربيّة بلا شبكة + جردُ الملفّات بلا غيرِ مُعلن",
            rc == 0
            and r.get("first_arabic_sentence", {}).get("ok")
            and r["first_arabic_sentence"]["network"] == "PROVEN"
            and inv.get("files_opened", 0) > 0
            and inv.get("undeclared") == []
            and r.get("performance_comparable") is False,
            f"opened={inv.get('files_opened')} counts={inv.get('counts')} comparable={r.get('performance_comparable')}",
        )
        secret = Path(tempfile.mkdtemp(prefix="undeclared-", dir="/var/tmp")) / "voice_extra.bin"
        secret.write_bytes(b"x")
        rc, r = run(
            "reads_undeclared",
            root,
            coord=("--inventory",),
            settings={"undeclared_path": str(secret)},
        )
        check(
            "v4 محرّكٌ يفتح ملفّاً خارج المُثبَّت ⇒ undeclared_files_opened",
            r.get("stage") == "undeclared_files_opened"
            and str(secret) in r.get("file_inventory", {}).get("undeclared", []),
            f"stage={r.get('stage')} undeclared={r.get('file_inventory', {}).get('undeclared')}",
        )
        # v6 — ثغراتُ مراجعة v5 الثلاث
        import hashlib

        share = Path(tempfile.mkdtemp(prefix="bakeoff-st-", dir="/usr/share"))
        libdir = Path(tempfile.mkdtemp(prefix="bakeoff-st-", dir="/usr/lib"))
        try:
            voice = share / "voice.onnx"
            voice.write_bytes(b"onnx-weights")
            rc, r = run(
                "reads_undeclared",
                root,
                coord=("--inventory",),
                settings={"undeclared_path": str(voice)},
            )
            reasons = r.get("file_inventory", {}).get("undeclared_reasons", {})
            check(
                "v6 نموذجٌ غيرُ مُعلن تحت /usr/share ⇒ undeclared_files_opened",
                r.get("stage") == "undeclared_files_opened" and str(voice) in reasons,
                f"stage={r.get('stage')} reason={reasons.get(str(voice))}",
            )
            blob = libdir / "blob"
            blob.write_bytes(os.urandom(6 * 2**20))
            rc, r = run(
                "reads_undeclared",
                root,
                coord=("--inventory",),
                settings={"undeclared_path": str(blob)},
            )
            reasons = r.get("file_inventory", {}).get("undeclared_reasons", {})
            check(
                "v6 ملفُّ بياناتٍ كبيرٌ بلا امتدادٍ تحت /usr/lib ⇒ undeclared",
                r.get("stage") == "undeclared_files_opened"
                and "large_data_file" in reasons.get(str(blob), ""),
                f"stage={r.get('stage')} reason={reasons.get(str(blob))}",
            )
            digest = hashlib.sha256(blob.read_bytes()).hexdigest()
            rc, r = run(
                "reads_undeclared",
                root,
                coord=("--inventory",),
                manifest={
                    "fake": {
                        "files": {},
                        "settings": {"mode": "reads_undeclared", "undeclared_path": str(blob)},
                        "package_assets": {"blob": digest},
                    }
                },
            )
            inv = r.get("file_inventory", {})
            check(
                "v6 الملفُّ نفسه مُعلنٌ ببصمته في package_assets ⇒ يمرّ (القاعدةُ لا تحجب المُعلن)",
                rc == 0
                and inv.get("undeclared") == []
                and inv.get("declared_package_assets") == {"blob": digest},
                f"rc={rc} undeclared={inv.get('undeclared')}",
            )
        finally:
            shutil.rmtree(share, ignore_errors=True)
            shutil.rmtree(libdir, ignore_errors=True)

        rc, r = run("ok", root, cpus="0.0001")
        cg = r.get("coordinator", {}).get("cgroup", {})
        # أوّلُ مجموعةٍ تُنشأ: الذاكرةُ في v1، والمجموعةُ الموحّدة في v2 — المسارُ يتبع الهرم المقيس
        mem_path = (
            Path("/sys/fs/cgroup/memory") / f"bakeoff-{r.get('run_id')}"
            if run_mod.cgroup_hierarchy() == "v1"
            else Path("/sys/fs/cgroup") / f"bakeoff-{r.get('run_id')}"
        )
        partial = cg.get("partial_cleanup", {})
        check(
            "v6 فشلُ الحصّة بعد إنشاء مجموعة الذاكرة ⇒ تُزال فوراً، ولا تُدّعى الحدود",
            cg.get("backend") == "UNAVAILABLE"
            and str(mem_path) in partial.get("created", [])
            and partial.get("leaked") == []
            and not mem_path.exists()
            and r.get("resource_limits", {}).get("status") != "ENFORCED"
            and r.get("performance_comparable") is False,
            f"backend={cg.get('backend')} partial={partial} exists={mem_path.exists()} "
            f"limits={r.get('resource_limits', {}).get('status')}",
        )
    else:
        RESULTS.append(("BLOCKED", "v4 الحصّة/الجرد", why))
        RESULTS.append(("BLOCKED", "v6 الجرد تحت /usr والتنظيفُ الجزئيّ", why))

    # v6 — .pth: ملفُّ مسارات site يمرّ، وأوزانٌ ثنائيّة بالامتداد نفسه في الموضع نفسه لا تمرّ (بلا root)
    from run import file_inventory

    site = root / "site-packages"
    site.mkdir()
    (site / "paths.pth").write_text("/opt/extra\n", encoding="utf-8")
    (site / "weights.pth").write_bytes(b"PK\x03\x04" + os.urandom(2048))
    log = root / "pth.trace"
    log.write_text(
        "".join(
            f'1 openat(AT_FDCWD, "{site / n}", O_RDONLY|O_CLOEXEC) = 3\n'
            for n in ("paths.pth", "weights.pth")
        ),
        encoding="utf-8",
    )
    inv = file_inventory(log, str(root / "pinned") + "/", [str(site) + "/"], [])
    check(
        "v6 .pth نصّيٌّ صغيرٌ في جذر بايثون يمرّ، وأوزانٌ .pth ثنائيّة في الموضع نفسه ⇒ undeclared",
        inv["undeclared"] == [str(site / "weights.pth")],
        f"undeclared={inv['undeclared']}",
    )

    # v8 — صندوقُ bwrap: جذرٌ فارغ لا يُرى فيه إلّا المعلن (مقابل الجرد الاستدلاليّ)
    if bwrap_ok and limits:
        bw = ("--sandbox", "bwrap")
        rc, r = run("ok", root, coord=bw)
        probes = r.get("isolation_control", {}).get("probes", {})
        ip_probe = [v for k, v in probes.items() if "بلا DNS" in k]
        check(
            "v8 bwrap: سليم ⇒ ok · PROVEN بمسبار عنوانٍ بلا DNS · المُثبَّت للقراءة فقط · قابلٌ للمقارنة",
            rc == 0
            and r.get("network_isolation") == "PROVEN"
            and ip_probe
            and ip_probe[0].startswith("blocked")
            and r.get("files_readonly") == "ENFORCED"
            and r.get("performance_comparable") is True
            and r["coordinator"]["sandbox"]["kind"] == "bwrap"
            and r["coordinator"]["negative_control"].get("ip"),
            f"rc={rc} probes={probes} ro={r.get('files_readonly')} problems={r.get('comparability_problems')}",
        )
        share = Path(tempfile.mkdtemp(prefix="bakeoff-st-", dir="/usr/share"))
        try:
            hidden = share / "voice.onnx"
            hidden.write_bytes(b"onnx-weights")
            rc, r = run(
                "reads_undeclared", root, coord=bw, settings={"undeclared_path": str(hidden)}
            )
            check(
                "v8 bwrap: نموذجٌ تحت /usr/share **غيرُ موجود** داخل الصندوق ⇒ load_failed (منعٌ لا كشف)",
                r.get("stage") == "load_failed"
                and "FileNotFoundError" in str(r.get("error"))
                and hidden.exists(),
                f"stage={r.get('stage')} error={str(r.get('error'))[:70]}",
            )
        finally:
            shutil.rmtree(share, ignore_errors=True)
        bw_model = root / "bwrap_model.bin"  # ملفٌّ خاصّ: النموذجُ الأوّل يُغيَّر عمداً بعد حالات v4
        bw_model.write_bytes(b"bwrap-pinned-model")
        rc, r = run(
            "tamper",
            root,
            coord=bw,
            manifest={
                "fake": {
                    "files": {"bwrap_model.bin": worker.sha256_file(bw_model)},
                    "settings": {"mode": "tamper", "model": "bwrap_model.bin"},
                }
            },
        )
        check(
            "v8 bwrap: تعديلُ نموذجٍ مُثبَّت يُرفض (ربطٌ للقراءة فقط)",
            r.get("stage") == "load_failed"
            and "Read-only" in str(r.get("error"))
            and r.get("pinned_integrity_after") == "INTACT",
            f"error={str(r.get('error'))[:60]}",
        )
        rc, r = run("net_native_on_load", root, coord=bw)
        check(
            "v8 bwrap: اتّصالٌ أصليٌّ (خارج حارس بايثون) لا يصل ⇒ ok و PROVEN",
            rc == 0 and r.get("harness_status") == "ok" and r.get("network_isolation") == "PROVEN",
            f"rc={rc} stage={r.get('stage')} error={str(r.get('error'))[:60]}",
        )
        rc, r = run("hang_with_child", root, coord=bw, hard_timeout=8)
        coord = r.get("coordinator", {})
        check_killed(
            "v8 bwrap: عالقٌ له ابن داخل الصندوق ⇒ hard_timeout، والمجموعةُ قُتلت",
            r.get("stage") == "hard_timeout"
            and bool(coord.get("killed_at_hard_timeout"))
            and bool(coord.get("killed_pids"))
            and r.get("performance_comparable") is False,
            {
                p: coord.get("killed_starttimes", {}).get(str(p))
                for p in coord.get("killed_pids", [])
            },
            f"stage={r.get('stage')} killed={coord.get('killed_pids')}",
        )
    else:
        RESULTS.append(
            ("BLOCKED", "v8 bwrap", f"bwrap={caps['bwrap'][1]} · cgroup_v1={caps['cgroup_v1'][1]}")
        )

    # v9 — منسّقٌ ورث SIGCHLD=SIG_IGN: رمزُ خروج العامل الفاشل يجب ألّا يصير 0 (كان يضيع قبل إعادة الضبط)
    rc, r = run("header_only", root, isolation=False, sigchld_ign=True)
    coord = r.get("coordinator", {})
    check(
        "v9 SIGCHLD موروثٌ مُهمَلاً ⇒ رمزُ خروج العامل الفاشل محفوظ (≠ 0) والموروثُ مُسجَّل",
        rc != 0
        and coord.get("exit_code") not in (0, None)
        and coord.get("sigchld_inherited") == "SIG_IGN",
        f"rc={rc} worker_exit={coord.get('exit_code')} inherited={coord.get('sigchld_inherited')}",
    )

    # v6/v7 — perf.py لا يثق بالعلَم ولا بحالات النجاح: يشترط الأدلّة نفسها
    def perf_on(doc: dict, name: str) -> tuple[int, str]:
        d = root / f"forged-{name}"
        shutil.copytree(good_run, d)
        (d / "result.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        p = subprocess.run(
            [sys.executable, str(HERE / "perf.py"), str(d), str(d)], capture_output=True, text=True
        )
        return p.returncode, p.stderr

    base = json.loads((Path(good_run) / "result.json").read_text(encoding="utf-8"))
    doc = json.loads(json.dumps(base))
    doc.update(
        harness_status="failed",
        stage="hard_timeout",
        network_isolation="BLOCKED",
        performance_comparable=True,
    )
    rc, err = perf_on(doc, "flag")
    check(
        "v6 perf: علَمُ المقارنة true مع failed/BLOCKED ⇒ سجلٌّ متناقض مرفوض",
        rc == 2 and "متناقض" in err,
        f"rc={rc} {err.strip()[-90:]}",
    )
    minimal = {
        "run_id": "minimal",
        "engine": "fake",
        "harness_status": "ok",
        "network_isolation": "PROVEN",
        "files_readonly": "ENFORCED",
        "pinned_integrity_after": "INTACT",
        "performance_comparable": True,
        "resource_limits": {"status": "ENFORCED"},
        "coordinator": {"exit_code": 0, "killed_at_hard_timeout": False},
    }
    rc, err = perf_on(minimal, "minimal")
    check(
        "v7 perf: سجلٌّ يحمل حالاتِ النجاح وحدها بلا قياساتٍ ولا بصماتٍ ولا حدودٍ فعليّة ⇒ مرفوض",
        rc == 2
        and "متناقض" in err
        and "sequential" in err
        and "corpus_sha256" in err
        and "in_effect" in err,
        f"rc={rc} {err.strip()[-100:]}",
    )
    # الضابطُ الإيجابيّ وسجلّاتُ نقص الدليل تُبنى على تشغيل bwrap من v4: السجلُّ المرجعيّ good_run يعمل بـunshare
    # فلم يعُد قابلاً للمقارنة، وتزويرٌ مبنيٌّ عليه يُرفض لسبب الإخفاء لا للسبب الذي تختبره الحالة.
    if comparable_ref is not None and comparable_ref.get("performance_comparable") is True:
        base = json.loads(
            (Path(comparable_ref["_run_dir"]) / "result.json").read_text(encoding="utf-8")
        )
        rc, err = perf_on(base, "control")
        check(
            "v7 perf: الضابطُ الإيجابيّ — سجلٌّ حقيقيٌّ كامل الأدلّة (bwrap) يُقبل",
            rc == 0,
            f"rc={rc} {err.strip()[-90:]}",
        )

        def forged(mutate) -> dict:
            d = json.loads(json.dumps(base))
            mutate(d)
            return d

        cases = (
            ("بلا قياساتٍ تتابعيّة", lambda d: d.pop("sequential"), "sequential"),
            ("جملٌ فشلت والباقي سليم", lambda d: d["sequential"].update(failed=3), "failed=3"),
            (
                "بلا بصمات السكربتات",
                lambda d: d["environment"].pop("scripts_sha256"),
                "بصماتُ سكربتاتٍ",
            ),
            ("بلا الحدود الفعليّة", lambda d: d["resource_limits"].pop("in_effect"), "in_effect"),
            (
                "حصّةٌ فعليّة ≠ المطلوبة",
                lambda d: d["resource_limits"]["in_effect"].update(cpu_quota=2.0),
                "in_effect.cpu_quota",
            ),
            (
                "خطأٌ في قراءة إحصاءات المجموعة",
                lambda d: d["coordinator"]["cgroup_stats"].update(error="OSError: x"),
                "إحصاءات المجموعة",
            ),
            (
                "تسرّبُ تنظيف المجموعة",
                lambda d: d["coordinator"]["cgroup"].update(
                    teardown_leaked=["/sys/fs/cgroup/memory/x"]
                ),
                "تسرّبُ تنظيف",
            ),
            (
                "p95 أصغرُ من الوسيط",
                lambda d: d["sequential"]["warm_requests"].update(p95_s=0.0001),
                "warm_requests",
            ),
            ("بلا verified_files", lambda d: d.pop("verified_files"), "verified_files"),
            (
                "كمونُ تزامنٍ لا يتّسق مع النجاحات",
                lambda d: next(iter(d["concurrency"].values()))["latency"].update(n=999),
                "concurrency",
            ),
            # v8 — ما يكشفه **عقدُ البنية** وحده (JSON Schema) ولا تراه فحوصُ الاتّساق
            (
                "بصمةُ مقطعٍ غيرُ صالحة",
                lambda d: d["sentences"][3].update(sha256="x"),
                "schema:/sentences/3/sha256",
            ),
            (
                "مقطعٌ فاشلٌ داخل سجلٍّ ناجح",
                lambda d: d["sentences"][3].update(ok=False),
                "schema:/sentences/3/ok",
            ),
            (
                "نسبةُ تباطؤٍ > 1",
                lambda d: d["coordinator"]["cgroup_stats"].update(cpu_throttled_ratio=4.2),
                "schema:/coordinator/cgroup_stats/cpu_throttled_ratio",
            ),
            (
                "مسبارُ عزلٍ وصل",
                lambda d: d["isolation_control"]["probes"].update({"tcp x": "REACHED"}),
                "schema:/isolation_control/probes",
            ),
            # v9 — مراجعةُ المالك: فشلُ التزامن ومقاييسُ مستحيلةٌ أو غيرُ متّسقة
            (
                "كلُّ طلبات التزامن فشلت",
                lambda d: [
                    c.update(succeeded=0, errors=c["requests"], throughput_rps=0.0, latency={})
                    for c in d["concurrency"].values()
                ],
                "أخطاءٌ أو مهلات",
            ),
            (
                "كلُّ طلبات التزامن فشلت — يكشفه العقدُ أيضاً",
                lambda d: [
                    c.update(succeeded=0, errors=c["requests"], throughput_rps=0.0, latency={})
                    for c in d["concurrency"].values()
                ],
                "schema:/concurrency/1/errors",
            ),
            (
                "مهلةٌ واحدة بعدّاتٍ متّسقة",
                lambda d: (
                    d["concurrency"]["1"].update(
                        succeeded=d["concurrency"]["1"]["requests"] - 1, timeouts=1
                    ),
                    d["concurrency"]["1"]["latency"].update(
                        n=d["concurrency"]["1"]["requests"] - 1
                    ),
                ),
                "أخطاءٌ أو مهلات",
            ),
            (
                "غيابُ p95 في التزامن",
                lambda d: d["concurrency"]["1"]["latency"].pop("p95_s"),
                "الكمونُ ناقص",
            ),
            (
                "نسبةُ تباطؤ 9",
                lambda d: d["coordinator"]["cgroup_stats"].update(cpu_throttled_ratio=9),
                "خارج [0, 1]",
            ),
            (
                "نسبةُ تباطؤٍ لا تتّسق مع عدّاتها",
                lambda d: d["coordinator"]["cgroup_stats"].update(
                    cpu_throttled_ratio=round(
                        min(1.0, d["coordinator"]["cgroup_stats"]["cpu_throttled_ratio"] + 0.3), 3
                    )
                    if d["coordinator"]["cgroup_stats"]["cpu_throttled_ratio"] < 0.7
                    else 0.1
                ),
                "لا تتّسق مع",
            ),
            (
                "فتراتُ تباطؤٍ > الفترات",
                lambda d: d["coordinator"]["cgroup_stats"].update(cpu_throttled_periods=10**6),
                "> cpu_periods",
            ),
            (
                "إنتاجيّةٌ لا تتّسق مع النجاحات والمدّة",
                lambda d: d["concurrency"]["1"].update(throughput_rps=999.0),
                "throughput_rps=999.0 لا تتّسق",
            ),
            (
                "ذروةُ ذاكرةٍ فوق الحدّ",
                lambda d: d["coordinator"]["cgroup_stats"].update(memory_peak_mb=10**6),
                "> حدّ الذاكرة",
            ),
        )
        bad = []
        for i, (label, mutate, reason) in enumerate(cases):
            rc, err = perf_on(forged(mutate), f"ev{i}")
            if not (rc == 2 and "متناقض" in err and reason in err):
                bad.append(f"{label}: rc={rc} {err.strip()[-60:]}")
        check(
            f"v7/v8 perf: {len(cases)} سجلّاتٍ ناقصةَ الدليل أو مخالفةً للعقد ⇒ كلٌّ مرفوضٌ بسببه",
            not bad,
            "; ".join(bad) or f"{len(cases)}/{len(cases)}",
        )
        d = root / "forged-noschema"
        shutil.copytree(good_run, d, dirs_exist_ok=True)
        (d / "result.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        p = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys,runpy; sys.modules['jsonschema'] = None; "
                f"sys.argv = ['perf.py', {str(d)!r}, {str(d)!r}]; runpy.run_path({str(HERE / 'perf.py')!r}, run_name='__main__')",
            ],
            capture_output=True,
            text=True,
        )
        check(
            "v8 perf: بلا jsonschema ⇒ BLOCKED (رمز 3) ولو كان السجلُّ سليماً — لا مقارنةَ بلا عقد",
            p.returncode == 3 and "BLOCKED" in p.stderr,
            f"rc={p.returncode} {p.stderr.strip()[-80:]}",
        )
    else:
        RESULTS.append(
            (
                "BLOCKED",
                "v7 perf: الضابطُ الإيجابيّ وسجلّاتُ نقص الدليل",
                f"لا سجلَّ حقيقيّاً قابلاً للمقارنة على هذا المضيف ({why}) — gate_selftest.py يغطّيها بلا root",
            )
        )

    return finish()


def finish() -> int:
    width = max(len(n) for _, n, _ in RESULTS)
    for status, name, detail in RESULTS:
        print(f"{status:8} {name.ljust(width)}  {detail}")
    failed = [n for s, n, _ in RESULTS if s == "FAIL"]
    blocked = sum(s == "BLOCKED" for s, _, _ in RESULTS)
    print(f"\n{len(RESULTS)} حالة · فشل {len(failed)} · BLOCKED {blocked}")
    if blocked:
        print("BLOCKED = لم يُختبر على هذا المضيف (لا شهادةَ عزلٍ أو حدودٍ منه) — لا يُحسب نجاحاً.")
    print("تنبيه: هذا يُثبت سلوك الأداة فقط — لا قياسَ لأيِّ محرّكٍ حقيقيّ ولا مقارنة.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
