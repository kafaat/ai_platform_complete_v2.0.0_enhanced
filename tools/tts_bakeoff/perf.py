"""مقارنةُ الأداء بين تشغيلات — تُرفض ما لم تكن كلُّها قابلةً للمقارنة وبالشروط نفسها.

    python3 perf.py runs/silma-… runs/<محرّكٌ ثانٍ>-…

يُرفض التشغيلُ ما لم تكتمل **أدلّتُه** (``evidence_problems``) — لا يكفي علَمُ ``performance_comparable`` ولا حالاتُ النجاح.
ويُرفض إن لم يكن ``performance_comparable``: أيُّ ``BLOCKED`` في عزل الشبكة أو حدود الموارد،
أو ملفّاتٌ مُثبَّتةٌ غيرُ مقروءةٍ فقط، أو تشغيلُ جردٍ بـstrace (يُبطئ)، يمنع اعتماد المقارنة.
وتُرفض المجموعة إن اختلفت الحدودُ (الذاكرة، والحصّة، والأنوية، والخيوط) أو بصمةُ النصوص أو السكربتات.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

SAME = ("memory_limit_mb", "cpu_quota", "cpu_cores", "threads")


HEX64 = re.compile(r"[0-9a-f]{64}")
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


def _num(v, *, positive=False) -> bool:
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and (v > 0 if positive else v >= 0)
    )


class NonFiniteJSON(ValueError):
    pass


def _reject_constant(name: str):
    raise NonFiniteJSON(f"قيمةٌ غيرُ منتهية في JSON: {name}")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):  # 1e999 يُحلَّل inf بصمت دون parse_constant
        raise NonFiniteJSON(f"عددٌ يفيض إلى قيمةٍ غير منتهية: {text}")
    return value


def load_result(path: Path) -> dict:
    """يقرأ result.json **بصرامة**: NaN وInfinity و-Infinity (وهي ليست JSON صالحاً) وما يفيض كـ1e999 تُرفض عند
    القراءة. ``json.loads`` الافتراضيّ يقبلها، والعقدُ لا يراها: NaN يفشل كلَّ مقارنة فلا يخرق أيَّ حدّ."""
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def nonfinite_paths(obj, path: str = "") -> list[str]:
    """كلُّ عددٍ غيرِ منتهٍ في السجلّ أينما كان — لسجلٍّ في الذاكرة لم يمرّ بالقارئ الصارم (run.py)."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return [path or "/"]
    if isinstance(obj, dict):
        return [p for k, v in obj.items() for p in nonfinite_paths(v, f"{path}/{k}")]
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in nonfinite_paths(v, f"{path}/{i}")]
    return []


# ما يجوز ربطُه في صندوق bwrap لمقارنة الأداء (مراجعةُ Copilot الثانية على #1133): «binds غيرُ فارغة» لا يُثبت
# جذراً فارغاً — ``rw:/`` يمرّ. فكلُّ ربطٍ يُفحص بنفسه مقابل ما يبنيه run.py: ربطاتُ النظام المعلنة
# (``run.BWRAP_SYSTEM_RO``) · جذورُ بايثون (``site-packages``/``dist-packages``) · المفسّر · مجلّدُ الحزمة ·
# مجلّدُ النماذج المُثبَّتة لهذا التشغيل؛ والكتابةُ لمجلّد ناتج هذا التشغيل وحده.
_PY_BIN = re.compile(r"/(?:[^/]+/)*bin/python3(?:\.\d+)?")
_BIND = re.compile(r"(ro|rw):(/\S*)")
_LINK = re.compile(r"link:(/\S*)->(/\S*)")


def _clean_abs(path: str) -> bool:
    import posixpath

    return path.startswith("/") and posixpath.normpath(path) == path and path != "/"


def _ro_allowed(path: str, rw: str | None) -> bool:
    import posixpath

    import run

    if not _clean_abs(path):
        return False
    if any(path == s or path.startswith(s + "/") for s in run.BWRAP_SYSTEM_RO):
        return True
    name = posixpath.basename(path)
    if name in ("site-packages", "dist-packages") or _PY_BIN.fullmatch(path):
        return True
    if name == "tts_bakeoff":
        return True
    return rw is not None and path == rw + ".pinned"


def sandbox_bind_problems(binds, run_id) -> list[str]:
    """كلُّ ربطٍ معلنٍ مقبولٌ بنفسه، وربطُ كتابةٍ واحدٌ لمجلّد ناتج هذا التشغيل؛ وإلّا فالمشكلات بأسمائها."""
    import posixpath

    if not isinstance(binds, list) or not binds:
        return ["sandbox.binds فارغة أو ليست قائمة"]
    out, rws, ros, links = [], [], [], []
    for b in binds:
        m, ln = _BIND.fullmatch(str(b)), _LINK.fullmatch(str(b))
        if m:
            (rws if m.group(1) == "rw" else ros).append(m.group(2))
        elif ln:
            links.append((ln.group(1), ln.group(2)))
        else:
            out.append(f"ربطٌ بصيغةٍ غير معروفة: {b!r}")
    if len(rws) != 1:
        out.append(f"المطلوب ربطُ كتابةٍ واحد لمجلّد ناتج التشغيل، وُجد {len(rws)}: {rws}")
    rw = rws[0] if len(rws) == 1 else None
    if rw is not None and (not _clean_abs(rw) or posixpath.basename(rw) != str(run_id)):
        out.append(f"ربطُ الكتابة ليس مجلّدَ ناتج هذا التشغيل ({run_id!r}): {rw!r}")
        rw = None
    for path in ros:
        if not _ro_allowed(path, rw):
            out.append(f"ربطُ قراءةٍ خارج المعلن: {path!r}")
    for src, dst in links:
        if not _clean_abs(src) or not _ro_allowed(dst, rw):
            out.append(f"رابطٌ إلى خارج المعلن: {src!r} -> {dst!r}")
    return out


def evidence_problems(r: dict) -> list[str]:
    """ما ينقص السجلَّ ليُقارَن أداؤه — **أدلّةٌ** لا أعلام. يُستعمل في run.py لحساب العلَم، وهنا لإعادة حسابه.

    حالاتُ النجاح وحدها لا تكفي: يُشترط وجودُ القياسات نفسها وصلاحُها (أعدادٌ منتهية موجبة، p95 ≥ الوسيط)،
    والبصمات (النصوص والسكربتات والحزم والملفّات المُثبَّتة)، والحدودُ **الفعليّة** مطابقةً للمطلوبة، وإحصاءاتُ
    المجموعة بلا خطأ، وتنظيفُها بلا تسرّب."""
    p: list[str] = [f"قيمةٌ غيرُ منتهية في {q}" for q in nonfinite_paths(r)]
    coord, env = r.get("coordinator") or {}, r.get("environment") or {}
    lim = r.get("resource_limits") or {}
    for key, want in (
        ("harness_status", "ok"),
        ("network_isolation", "PROVEN"),
        ("files_readonly", "ENFORCED"),
        ("pinned_integrity_after", "INTACT"),
    ):
        if r.get(key) != want:
            p.append(f"{key}={r.get(key)!r}")
    if lim.get("status") != "ENFORCED":
        p.append(f"resource_limits.status={lim.get('status')!r}")
    if "file_inventory" in r:
        p.append("تشغيلُ جردٍ بـstrace (يُبطئ)")
    # إخفاءٌ صارم (مراجعةُ Copilot على #1133): ``unshare -n -m`` يُبقي نظامَ ملفّات المضيف كلَّه مرئيّاً، فنموذجٌ
    # غيرُ معلَن يؤثّر في الناتج ويمرّ. المقارنةُ تُشترط في جذرٍ فارغ (bwrap) بربطٍ معلَنٍ للقراءة فقط، والربطُ
    # مُسجَّلٌ في السجلّ؛ وما تحت ربطات النظام نفسها يبقى للجرد المنفصل (``--inventory``).
    sandbox = coord.get("sandbox") or {}
    if sandbox.get("kind") != "bwrap" or not sandbox.get("binds"):
        p.append(
            f"sandbox={sandbox.get('kind')!r}: المقارنةُ تتطلّب جذراً فارغاً (bwrap) بربطٍ معلَن — "
            "unshare يكشف نظامَ ملفّات المضيف فلا يُثبَت أنّ المحرّك لم يقرأ إلّا المعلَن"
        )
    else:
        p += [f"sandbox: {q}" for q in sandbox_bind_problems(sandbox["binds"], r.get("run_id"))]
    # الخروج والقتل وOOM
    if coord.get("exit_code") != 0:
        p.append(f"coordinator.exit_code={coord.get('exit_code')!r}")
    if coord.get("killed_at_hard_timeout") is not False:
        p.append(f"killed_at_hard_timeout={coord.get('killed_at_hard_timeout')!r}")
    if coord.get("survivors_after_exit"):
        p.append(f"عمليّاتٌ بقيت بعد الخروج {coord['survivors_after_exit']}")
    # المجموعة: إنشاءٌ كامل، وإحصاءاتٌ بلا خطأ، وتنظيفٌ بلا تسرّب
    cg, st = coord.get("cgroup") or {}, coord.get("cgroup_stats") or {}
    # v1 مجموعتان (ذاكرة ومعالج) · v2 مجموعةٌ واحدة بالملفَّين. العددُ يُفحص لكلٍّ بحسبه،
    # فلا يمرّ سجلُّ v1 ناقصَ مجموعةٍ ولا يُرفض سجلُّ v2 الكامل.
    expected = {"cgroup-v1": 2, "cgroup-v2": 1}.get(cg.get("backend"))
    if expected is None or len(cg.get("paths") or []) != expected:
        p.append(f"cgroup.backend={cg.get('backend')!r} paths={cg.get('paths')!r}")
    if cg.get("teardown_leaked"):
        p.append(f"تسرّبُ تنظيف المجموعة {cg['teardown_leaked']}")
    if (cg.get("partial_cleanup") or {}).get("leaked"):
        p.append(f"تسرّبُ تنظيفٍ جزئيّ {cg['partial_cleanup']['leaked']}")
    if "error" in st:
        p.append(f"خطأٌ في قراءة إحصاءات المجموعة: {st['error']}")
    if not _num(st.get("memory_peak_mb"), positive=True):
        p.append(f"cgroup_stats.memory_peak_mb={st.get('memory_peak_mb')!r}")
    for key in ("cpu_periods", "cpu_throttled_periods", "cpu_throttled_ratio"):
        if not _num(st.get(key)):
            p.append(f"cgroup_stats.{key}={st.get(key)!r}")
    if st.get("oom_kill_events") != 0:
        p.append(f"oom_kill_events={st.get('oom_kill_events')!r}")
    # نطاقاتٌ واتّساقُ عدّاتٍ في إحصاءات المجموعة (مقاييسُ مستحيلةٌ تُرفض لا تُعرض)
    periods, throttled, ratio = (
        st.get("cpu_periods"),
        st.get("cpu_throttled_periods"),
        st.get("cpu_throttled_ratio"),
    )
    if _num(ratio) and not 0 <= ratio <= 1:
        p.append(f"cpu_throttled_ratio={ratio} خارج [0, 1]")
    if all(isinstance(v, int) for v in (periods, throttled)) and _num(ratio):
        if throttled > periods:
            p.append(f"cpu_throttled_periods={throttled} > cpu_periods={periods}")
        elif abs(ratio - (throttled / periods if periods else 0.0)) > 0.0015:
            p.append(f"cpu_throttled_ratio={ratio} لا تتّسق مع {throttled}/{periods}")
    limit = (lim.get("requested") or {}).get("memory_limit_mb")
    if _num(st.get("memory_peak_mb")) and _num(limit) and st["memory_peak_mb"] > limit * 1.01:
        p.append(f"memory_peak_mb={st['memory_peak_mb']} > حدّ الذاكرة {limit}")
    # الحدود: المطلوبةُ كاملة، والفعليّةُ تطابقها
    req, eff = lim.get("requested") or {}, lim.get("in_effect") or {}
    for key in SAME:
        if req.get(key) in (None, ""):
            p.append(f"resource_limits.requested.{key} مفقود")
    for key in ("memory_limit_mb", "cpu_quota"):
        if eff.get(key) != req.get(key):
            p.append(f"in_effect.{key}={eff.get(key)!r} ≠ requested {req.get(key)!r}")
    cores = [c for c in str(req.get("cpu_cores", "")).split(",") if c != ""]
    try:
        affinity_ok = bool(eff.get("cpu_affinity")) and sorted(
            map(int, eff["cpu_affinity"])
        ) == sorted(map(int, cores))
    except (TypeError, ValueError, OverflowError):
        affinity_ok = False  # قيمٌ مشوّهة لا تُنهي البوّابةَ بخطأ — تُرفض
    if not affinity_ok:
        p.append(f"in_effect.cpu_affinity={eff.get('cpu_affinity')!r} ≠ requested cores {cores}")
    if env.get("limits") != req:
        p.append("environment.limits ≠ resource_limits.requested")
    # البصمات
    if not HEX64.fullmatch(str(env.get("corpus_sha256", ""))):
        p.append("environment.corpus_sha256 مفقودة أو غير صالحة")
    scripts = env.get("scripts_sha256") or {}
    missing = [s for s in SCRIPTS if not HEX64.fullmatch(str(scripts.get(s, "")))]
    if missing:
        p.append(f"بصماتُ سكربتاتٍ مفقودة {missing}")
    if not env.get("packages"):
        p.append("environment.packages فارغة")
    if "verified_files" not in r or (r.get("engine") != "fake" and not r.get("verified_files")):
        p.append("verified_files مفقودة — لا دليلَ على الملفّات المُحمَّلة")
    # القياسات
    seq = r.get("sequential") or {}
    if (
        seq.get("failed") != 0
        or not isinstance(seq.get("ok"), int)
        or seq["ok"] < 2
        or seq["ok"] != len(r.get("sentences") or [])
    ):
        p.append(
            f"sequential ok={seq.get('ok')!r} failed={seq.get('failed')!r} sentences={len(r.get('sentences') or [])}"
        )
    if not _num((r.get("load") or {}).get("seconds")):
        p.append(f"load.seconds={(r.get('load') or {}).get('seconds')!r}")
    for phase in ("cold_request", "warm_requests"):
        m = seq.get(phase) or {}
        if not (
            isinstance(m.get("n"), int)
            and m["n"] >= 1
            and _num(m.get("median_s"), positive=True)
            and _num(m.get("p95_s"), positive=True)
            and m["p95_s"] >= m["median_s"]
        ):
            p.append(f"sequential.{phase} غيرُ صالح {m}")
    if not _num(seq.get("rtf_warm_median"), positive=True):
        p.append(f"rtf_warm_median={seq.get('rtf_warm_median')!r}")
    conc = r.get("concurrency") or {}
    if not conc:
        p.append("concurrency فارغ")
    for level, c in conc.items():
        lat = c.get("latency") or {}
        ok_counts = (
            isinstance(c.get("requests"), int)
            and c["requests"] > 0
            and all(
                isinstance(c.get(k), int) and c[k] >= 0 for k in ("succeeded", "errors", "timeouts")
            )
        )
        if not ok_counts or c["succeeded"] + c["errors"] + c["timeouts"] != c["requests"]:
            p.append(f"concurrency.{level}: عدّاتٌ ناقصة أو لا تتّسق {c}")
            continue
        # أداءٌ تحت تزامنٍ فشلت فيه طلبات لا يُقارَن: إنتاجيّةُ ما نجح وحده تُجمّل المحرّك الذي يُسقط الطلبات
        if c["errors"] or c["timeouts"]:
            p.append(
                f"concurrency.{level}: أخطاءٌ أو مهلات (errors={c['errors']} timeouts={c['timeouts']} "
                f"من {c['requests']}) — لا مقارنةَ أداءٍ مع طلباتٍ فاشلة"
            )
            continue
        if not (
            lat.get("n") == c["succeeded"]
            and _num(lat.get("median_s"), positive=True)
            and _num(lat.get("p95_s"), positive=True)
            and lat["p95_s"] >= lat["median_s"]
        ):
            p.append(f"concurrency.{level}: الكمونُ ناقص (n · median · p95) أو p95 < الوسيط {lat}")
        span, thr = c.get("span_s"), c.get("throughput_rps")
        if not (_num(span, positive=True) and _num(thr, positive=True)):
            p.append(f"concurrency.{level}: span_s={span!r} throughput_rps={thr!r}")
        elif abs(thr - c["succeeded"] / span) > 0.03 * thr + 0.01:
            p.append(
                f"concurrency.{level}: throughput_rps={thr} لا تتّسق مع {c['succeeded']}/{span}s"
            )
    return p


HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "result_comparable.schema.json"


def schema_problems(r: dict) -> list[str]:
    """عقدُ البنية (JSON Schema 2020-12): الحقولُ الإلزاميّة وأنواعُها ومداها والحالاتُ الثابتة وشروطُ if/then.
    مُكمِّلٌ لـ``evidence_problems`` لا بديل: البنيةُ الصالحة لا تُثبت أنّ القياس نُفِّذ."""
    import jsonschema  # noqa: PLC0415 — غيابُه يُرفع في main لا هنا

    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return [
        f"schema:/{'/'.join(map(str, e.absolute_path))}: {e.message[:160]}"
        for e in sorted(validator.iter_errors(r), key=lambda e: list(map(str, e.absolute_path)))
    ]


def why_not_comparable(r: dict) -> list[str]:
    """علَمٌ ``true`` مع نقص أدلّةٍ = سجلٌّ **متناقض**؛ وعلَمٌ غيرُ ``true`` = غيرُ قابلٍ للمقارنة."""
    problems = schema_problems(r) + evidence_problems(r)
    if r.get("performance_comparable") is True and problems:
        return [f"سجلٌّ متناقض: performance_comparable=true مع {problems}"]
    if r.get("performance_comparable") is not True:
        return problems or ["performance_comparable≠true"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args()

    try:
        import jsonschema  # noqa: F401, PLC0415
    except ImportError:
        print(
            "BLOCKED: jsonschema غيرُ مثبّت — لا تُعتمد مقارنةٌ بلا عقد السجلّ "
            "(pip install -r requirements-gate.txt)",
            file=sys.stderr,
        )
        return 3
    results = []
    for run in args.runs:
        try:
            results.append(load_result(Path(run) / "result.json"))
        except NonFiniteJSON as exc:
            print(f"مرفوض — لا تُعتمد مقارنةُ أداء:\n  {run}: {exc}", file=sys.stderr)
            return 2
    problems = []
    for r in results:
        if why := why_not_comparable(r):
            problems.append(
                f"{r.get('run_id')}: غير قابل للمقارنة — {why} (net={r.get('network_isolation')} "
                f"limits={r.get('resource_limits', {}).get('status')} ro={r.get('files_readonly')} "
                f"status={r.get('harness_status')})"
            )
    keyset = {
        json.dumps(
            {k: r.get("resource_limits", {}).get("requested", {}).get(k) for k in SAME},
            sort_keys=True,
        )
        for r in results
    }
    if len(keyset) > 1:
        problems.append(f"حدودٌ مختلفة بين التشغيلات: {sorted(keyset)}")
    # بصمةُ الحِمل: المستوياتُ **وعددُ طلبات كلٍّ منها** (مراجعةُ Copilot الثانية على #1133) — مستوياتٌ واحدة
    # بـ``--concurrency-items`` مختلف تُنتج إنتاجيّةً وزمنَ انتظارٍ غيرَ متكافئين.
    workloads = {
        json.dumps(
            {lvl: (v or {}).get("requests") for lvl, v in (r.get("concurrency") or {}).items()},
            sort_keys=True,
        )
        for r in results
    }
    if len(workloads) > 1:
        problems.append(
            f"حِملُ التزامن يختلف بين التشغيلات (المستوى ⇒ عدد الطلبات): {sorted(workloads)}"
        )
    # المفسّرُ والمضيف: مقارنةٌ بين تشغيلَين على بايثونَين مختلفَين أو جهازَين مختلفَين ليست مقارنة.
    # والقيدُ حقيقيّ ومقيس: `kokoro-onnx==0.6.1` يشترط بايثون <3.14، و`silma-tts==1.0.5` يثبّت
    # `numpy<=1.26.4` وعجلاتُها تنتهي عند cp312 — فالمحرّكان يُشغَّلان على 3.12 بينما المضيفُ قد
    # يحمل 3.14. وهذه الحقولُ مُسجَّلةٌ أصلاً في `environment`، فما كان ينقص إلّا فرضُ تساويها.
    for field in ("python", "platform", "cpu_model", "cpu_visible", "thread_env"):
        if (
            len({json.dumps(r.get("environment", {}).get(field), sort_keys=True) for r in results})
            > 1
        ):
            problems.append(
                f"environment.{field} يختلف بين التشغيلات: "
                + str(
                    sorted(
                        {
                            json.dumps(r.get("environment", {}).get(field), sort_keys=True)
                            for r in results
                        }
                    )
                )
            )
    for field in ("corpus_sha256", "scripts_sha256"):
        if (
            len({json.dumps(r.get("environment", {}).get(field), sort_keys=True) for r in results})
            > 1
        ):
            problems.append(f"{field} يختلف بين التشغيلات")
    if problems:
        print("مرفوض — لا تُعتمد مقارنةُ أداء:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2

    rows = []
    for r in results:
        seq, cg = r.get("sequential", {}), r.get("coordinator", {}).get("cgroup_stats", {})
        rows.append(
            {
                "engine": r["engine"],
                "run_id": r["run_id"],
                "load_s": r.get("load", {}).get("seconds"),
                "cold_s": seq.get("cold_request", {}).get("median_s"),
                "warm_median_s": seq.get("warm_requests", {}).get("median_s"),
                "warm_p95_s": seq.get("warm_requests", {}).get("p95_s"),
                "rtf_warm": seq.get("rtf_warm_median"),
                "conc": {
                    n: {k: c.get(k) for k in ("throughput_rps", "errors", "timeouts")}
                    | {"p95_s": c.get("latency", {}).get("p95_s")}
                    for n, c in r.get("concurrency", {}).items()
                },
                "peak_mb": cg.get("memory_peak_mb"),
                "throttled_ratio": cg.get("cpu_throttled_ratio"),
                "threads": r.get("threads_at_end"),
            }
        )
    import hashlib  # noqa: PLC0415

    print(
        json.dumps(
            {
                "limits": json.loads(keyset.pop()),
                "schema_sha256": hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest(),
                "runs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
