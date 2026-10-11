"""فحصُ بوّابة مقارنة الأداء (perf.py) **بلا root ولا unshare** — على سجلٍّ حقيقيٍّ قابلٍ للمقارنة في fixtures/.

    python3 -m pip install -r requirements-gate.txt && python3 gate_selftest.py

``fixtures/comparable_result.json`` سجلٌّ أنتجه ``run.py --sandbox bwrap`` هنا (محرّكٌ وهميّ، عزلٌ PROVEN). كلُّ حالةٍ
تُعدّل نسخةً منه وتتوقّع رفضاً **بسببٍ مسمّى**؛ والضابطُ الإيجابيّ يتوقّع القبول. هذا يُثبت سلوكَ البوّابة وحدها، لا العزل.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FIXTURE = HERE / "fixtures" / "comparable_result.json"
CONSTANTS = {"NaN": float("nan"), "Infinity": float("inf"), "-Infinity": float("-inf")}
# ما يكتبه أيُّ مولِّدٍ في ملفّ: الثوابتُ الثلاثة (ليست JSON صالحاً) والأعدادُ التي تفيض عن float (1e309 > 1.8e308 ⇒ inf بصمت)
TOKENS = {**CONSTANTS, "1e309": float("inf"), "-1e309": float("-inf")}


def perf_on(doc_text: str, tmp: Path, name: str) -> tuple[int, str]:
    d = tmp / name
    d.mkdir()
    (d / "result.json").write_text(doc_text, encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(HERE / "perf.py"), str(d), str(d)], capture_output=True, text=True
    )
    return p.returncode, p.stderr


def numeric_leaves(obj, path=()):
    """كلُّ قيمةٍ عدديّة (لا منطقيّة) في السجلّ — مدداً ومقاييسَ وعدّاتٍ وحدوداً."""
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [path]
    if isinstance(obj, dict):
        return [p for k, v in obj.items() for p in numeric_leaves(v, path + (k,))]
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in numeric_leaves(v, path + (i,))]
    return []


def set_at(doc, path, value):
    for k in path[:-1]:
        doc = doc[k]
    doc[path[-1]] = value


def main() -> int:
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    results = []
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("BLOCKED: jsonschema غيرُ مثبّت — pip install -r requirements-gate.txt")
        return 3
    import perf

    base_text = FIXTURE.read_text(encoding="utf-8")
    base = json.loads(base_text)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rc, err = perf_on(base_text, tmp, "control")
        results.append(
            (
                "PASS" if rc == 0 else "FAIL",
                "الضابطُ الإيجابيّ: السجلُّ الحقيقيّ كما هو يُقبل",
                f"rc={rc} {err[-120:]}",
            )
        )

        # حالةُ المالك حرفيّاً، ثمّ أخواتُها في الحقل نفسه — كما تُكتب في الملفّ نصّاً
        for token in TOKENS:
            doc = json.loads(base_text)
            set_at(doc, ("sentences", 0, "wall_s"), "__X__")
            rc, err = perf_on(json.dumps(doc).replace('"__X__"', token), tmp, f"owner-{token}")
            reason = "يفيض" if token.lstrip("-")[0].isdigit() else "غيرُ منتهية"
            results.append(
                (
                    "PASS" if rc == 2 and token in err and reason in err else "FAIL",
                    f"sentences[0].wall_s = {token} ⇒ رفضٌ عند القراءة (رمز 2)",
                    f"rc={rc} " + err.strip().replace(chr(10), " ")[-90:],
                )
            )
        rc, err = perf_on(
            base_text.replace('"wall_s": ', '"wall_s": 1e999, "_x": ', 1), tmp, "overflow"
        )
        results.append(
            (
                "PASS" if rc == 2 and "يفيض" in err else "FAIL",
                "عددٌ يفيض (1e999 ⇒ inf بصمت) ⇒ رفض",
                f"rc={rc} " + err.strip().replace(chr(10), " ")[-90:],
            )
        )

        # كلُّ حقلٍ عدديّ × كلُّ قيمةٍ غير منتهية: (أ) القارئُ الصارم يرفض نصَّ الملفّ، (ب) فحصُ الأدلّة يرفض السجلَّ في الذاكرة
        leaves = numeric_leaves(base)
        missed_load, missed_mem = [], []
        strict = hasattr(perf, "load_result") and hasattr(perf, "NonFiniteJSON")
        if not strict:  # perf.py أقدم من v11: لا قارئَ صارماً — يُسجَّل فشلاً لا انهياراً
            results.append(
                (
                    "FAIL",
                    "perf.py بلا قارئٍ صارم (load_result/NonFiniteJSON) — NaN/Infinity تُقبل عند القراءة",
                    "",
                )
            )
            leaves = []
        for path in leaves:
            for token, value in TOKENS.items():
                doc = json.loads(base_text)
                set_at(doc, path, "__X__")
                target = tmp / "leaf.json"
                target.write_text(json.dumps(doc).replace('"__X__"', token), encoding="utf-8")
                set_at(doc, path, value)
                try:
                    perf.load_result(target)
                    missed_load.append(f"{'/'.join(map(str, path))}={token}")
                except perf.NonFiniteJSON:
                    pass
                slash = "/" + "/".join(map(str, path))
                if not any(slash in q for q in perf.evidence_problems(doc)):
                    missed_mem.append(f"{slash}={token}")
        total = len(leaves) * len(TOKENS)
        results.append(
            (
                "PASS" if not missed_load and total > 100 else "FAIL",
                f"كلُّ حقلٍ عدديّ ({len(leaves)}) × NaN/±Infinity/±1e309 ⇒ القارئُ الصارم يرفض {total - len(missed_load)}/{total}",
                "; ".join(missed_load[:5]),
            )
        )
        results.append(
            (
                "PASS" if not missed_mem and total > 100 else "FAIL",
                f"والسجلُّ نفسه في الذاكرة (كما يقرؤه run.py) ⇒ فحصُ الأدلّة يسمّي المسار {total - len(missed_mem)}/{total}",
                "; ".join(missed_mem[:5]),
            )
        )

        # حالاتُ v9 (فشلُ التزامن ومقاييسُ مستحيلة) — قابلةٌ للتحقّق هنا بلا root
        def forged(mutate):
            d = json.loads(base_text)
            mutate(d)
            return json.dumps(d, ensure_ascii=False)

        st = base["coordinator"]["cgroup_stats"]
        cases = (
            (
                "كلُّ طلبات التزامن فشلت",
                lambda d: [
                    c.update(succeeded=0, errors=c["requests"], throughput_rps=0.0, latency={})
                    for c in d["concurrency"].values()
                ],
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
                    cpu_throttled_ratio=0.5 if st["cpu_throttled_ratio"] < 0.2 else 0.0
                ),
                "لا تتّسق مع",
            ),
            (
                "إنتاجيّةٌ لا تتّسق",
                lambda d: d["concurrency"]["1"].update(throughput_rps=999.0),
                "throughput_rps=999.0 لا تتّسق",
            ),
            (
                "ذروةُ ذاكرةٍ فوق الحدّ",
                lambda d: d["coordinator"]["cgroup_stats"].update(memory_peak_mb=10**6),
                "> حدّ الذاكرة",
            ),
            (
                "مقطعٌ فاشلٌ داخل سجلٍّ ناجح",
                lambda d: d["sentences"][3].update(ok=False),
                "schema:/sentences/3/ok",
            ),
            (
                "حالاتُ نجاحٍ بلا قياسات",
                lambda d: [d.pop(k) for k in ("sequential", "concurrency", "load")],
                "sequential",
            ),
            (
                "أنويةٌ فعليّة مشوّهة (نصٌّ لا عدد) — رفضٌ لا انهيار",
                lambda d: d["resource_limits"]["in_effect"].update(cpu_affinity=["x"]),
                "in_effect.cpu_affinity",
            ),
        )
        for i, (label, mutate, reason) in enumerate(cases):
            rc, err = perf_on(forged(mutate), tmp, f"v9-{i}")
            results.append(
                (
                    "PASS" if rc == 2 and reason in err else "FAIL",
                    f"{label} ⇒ رفضٌ بسببه",
                    f"rc={rc} {err.strip().replace(chr(10), ' ')[-90:]}",
                )
            )

    for status, name, detail in results:
        print(f"{status:5} {name}  {detail}")
    failed = sum(s == "FAIL" for s, _, _ in results)
    print(f"\n{len(results)} حالة · فشل {failed}")
    print(
        "حدّه: يُثبت سلوكَ بوّابة المقارنة وحدها على سجلٍّ ثابت — لا العزل ولا القياس ولا أيَّ محرّكٍ حقيقيّ."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
