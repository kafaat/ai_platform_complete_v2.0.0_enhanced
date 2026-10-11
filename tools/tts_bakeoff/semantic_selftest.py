"""يُثبت أنّ مرجعَ الحقائق المعلنة (والفرزَ الآليّ المساعد بـASR) **يكشف** تغيّرَ المعنى ولا يرفض المعادِلَ الصحيح — نصّاً فقط، بلا صوت ولا شبكة.

    python3 semantic_selftest.py

صنفان من الحالات:
  • طفراتٌ يجب أن **تفشل**: قلبُ الجرعة 2/5 · سقوطُ «لا» · قلبُ الحدّ · 2.5→25 · العددُ المجزّأ
    «اثنان , خمسون» · الصفرُ الساقط · المقامُ والوحدة · التكرار · ساعةُ اليوم مقابل المدّة · ترتيبُ المدى.
  • معادِلاتٌ يجب أن **تنجح**: 2.50 = 2.5 عدداً · «اثنان فاصلة خمسة» · أرقامٌ هنديّة · «مليلتران ونصف».
والأصلُ (النصّ الخام لكلّ جملة) يجب أن ينجح كلّه — وإلّا فالمحلّلُ لا الجملةُ هو المعطوب.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import procs
import semantic
from semantic import HERE

FACTS = semantic.load_facts()

# (الجملة، النصّ الطافر، سببُ وجوب الفشل، **سببُ الرفض المتوقَّع** — جزءٌ من نصّ الخطأ يجب أن يظهر)
MUST_FAIL = [
    (
        "D03",
        "الجرعة 5 مل لكل 2 لتر، ولا تزد عليها.",
        "قلبُ الجرعة: 5 مل لكل لترين بدل 2.5 مل لكل لتر",
        "value=",
    ),
    ("D03", "الجرعة 2.5 مل لكل لتر، وزد عليها.", "سقوطُ «لا» من «ولا تزد»", "نفيٌ مفقود"),
    ("N01", "ترش المبيد قبل الحصاد بأقل من ١٤ يوماً.", "سقوطُ «لا» من أوّل الجملة", "نفيٌ مفقود"),
    ("N01", "لا ترش المبيد قبل الحصاد بأكثر من ١٤ يوماً.", "قلبُ الحدّ: أكثر من بدل أقل من", "bound="),
    (
        "N04",
        "لا ترش إذا كانت سرعة الرياح أقل من ١٥ كيلومتراً في الساعة.",
        "قلبُ الحدّ في شرط الرياح",
        "bound=",
    ),
    ("D03", "الجرعة 25 مل لكل لتر، ولا تزد عليها.", "2.5 صارت 25", "value="),
    (
        "D03",
        "الجرعة اثنان , خمسون مل لكل لتر، ولا تزد عليها.",
        "قراءةٌ مجزّأة: «اثنان» ثمّ «خمسون مل»",
        "كمّيّةٌ زائدة",
    ),
    (
        "D05",
        "نسبة الملوحة في البئر ثلاثة , عشرون ديسيسيمنز لكل متر.",
        "قراءةٌ مجزّأة: 3 ثمّ 20",
        "كمّيّةٌ زائدة",
    ),
    (
        "M01",
        "مؤشر NDVI للحقل انخفض من , اثنتان و ستون إلى , إحدى و أربعون خلال أسبوعين.",
        "الصفرُ الساقط: 0.62 تُسمع 62",
        "value=",
    ),
    ("D03", "الجرعة 2.5 مل لكل هكتار، ولا تزد عليها.", "المقامُ تغيّر: لكل هكتار", "per="),
    ("D03", "الجرعة 2.5 لتر لكل لتر، ولا تزد عليها.", "الوحدةُ تغيّرت: لتر بدل مل", "unit="),
    ("D04", "اسقِ النخلة ١٢٠ لتراً ٧ أيام في الصيف.", "سقوطُ التكرار «كل»", "bound="),
    ("T03", "سجّل القراءة كل ٣ ساعات من الساعة ١٨ حتى الساعة ٦.", "ترتيبُ المدى انقلب", "value="),
    ("T03", "سجّل القراءة كل ٣ ساعات من ٦ ساعات حتى الساعة ١٨.", "ساعةُ اليوم صارت مدّة", "unit="),
    (
        "D03",
        "الجرعة 2.5 مل لكل لتر، ولا تنقص عنها.",
        "تغيّر الفعلُ المنفيّ: «لا تنقص» بدل «لا تزد»",
        "نفيٌ مفقود",
    ),
    (
        "N03",
        "لا تخلط هذا المبيد مع الأسمدة الورقية ولا ترش.",
        "نفيٌ زائد لم يكن في الأصل",
        "نفيٌ غيرُ معلن",
    ),
    ("D04", "اسقِ النخلة مئة وعشرون لتراً كل سبعة أيام في الصيف ٣.", "رقمٌ دخيل", "كمّيّةٌ زائدة"),
    ("N05", "يجب ألّا تدخل الحقل قبل مرور ٨٤ ساعة على الرش.", "تبديلُ خانتين: 48→84", "value="),
    ("C04", "أصناف المانجو في الحديدة تُقطف من مايو حتى أكتوبر.", "كلمةٌ حرجة تغيّرت", "عبارةُ محتوى"),
    (
        "T01",
        "موعد الري القادم يوم الثلاثاء الساعة السابعة صباحاً.",
        "الترتيبيّ تغيّر: السابعة بدل السادسة",
        "value=",
    ),
    # v6 — قبولٌ خاطئ أثبته المالك على v5، وما يشبهه
    (
        "M03",
        "نقطة الذبول ٢٢٪ ورطوبة التربة ١٢٪، فالري مطلوب خلال يومين.",
        "تبديلُ الإسناد: القيمتان صحيحتان والمُسنَد إليه انقلب",
        "مُسندةٌ",
    ),
    (
        "N04",
        "لا ترش إذا كانت سرعة الرياح ليست أكثر من ١٥ كيلومتراً في الساعة.",
        "نفيٌ داخل الشرط («ليست») يقلب نطاقه",
        "نطاقُ الشرط",
    ),
    (
        "D03",
        "الجرعة 2.5 مل لكل لتر، ولا تزد عليها. زد عليها.",
        "أمرٌ لاحق «زد عليها» يناقض النهي",
        "أمرٌ يناقض النهي",
    ),
    (
        "C01",
        "زراعة القمح في صعدة تبدأ مع أول مطر في موسم الشتاء.",
        "محصولٌ ومكانٌ وموسمٌ مختلفة",
        "عبارةُ محتوى",
    ),
    (
        "C03",
        "الذرة الشامية تتحمل الجفاف أكثر من الدخن والسمسم.",
        "اتّجاهُ المقارنة انقلب",
        "عبارةُ محتوى",
    ),
    (
        "N04",
        "لا ترش، سرعة الرياح أكثر من ١٥ كيلومتراً في الساعة.",
        "أداةُ الشرط سقطت فصار النهيُ مطلقاً",
        "أداةُ الشرط",
    ),
    (
        "M01",
        "مؤشر NDVI للحقل ارتفع من 0.62 إلى 0.41 خلال أسبوعين.",
        "اتّجاهُ التغيّر انقلب: ارتفع بدل انخفض",
        "«انخفض» مفقودة",
    ),
    ("D01", "لا تخلط مليلترين ونصف من المبيد في كل لتر ماء.", "الأمرُ صار نهياً", "نهيٌ يناقض الأمر"),
    (
        "D06",
        "درجة الحرارة المتوقعة غداً ٤٥ بالمئة والرطوبة ٣٨ درجة مئوية.",
        "تبديلُ الكمّيّتين بين المتغيّرين",
        "value=",
    ),
    # v7 — مثالُ المالك على v6: الشرطُ انتقل إلى «الجهاز» عبر جملةٍ مستقلّة، وصيغتان تربطانه بلا حدّ جملة
    (
        "N04",
        "لا ترش إذا كان الجهاز سليماً. سرعة الرياح أكثر من ١٥ كيلومتراً في الساعة.",
        "الشرطُ عن الجهاز، والكمّيّةُ في جملةٍ مستقلّة",
        "جملةٍ مستقلّة",
    ),
    (
        "N04",
        "لا ترش إذا كان الجهاز سليماً وسرعة الرياح أكثر من ١٥ كيلومتراً في الساعة.",
        "موضوعُ الشرط صار الجهاز (بالواو)",
        "موضوعُ الشرط «إذا» صار",
    ),
    (
        "N04",
        "لا ترش إذا كان الجهاز سليماً، سرعة الرياح أكثر من ١٥ كيلومتراً في الساعة.",
        "موضوعُ الشرط صار الجهاز (بالفاصلة)",
        "موضوعُ الشرط «إذا» صار",
    ),
    (
        "C03",
        "الذرة الشامية والسمسم يتحملان الجفاف أكثر من الدخن.",
        "تبديلُ طرفَي المقارنة وكلُّ الكلمات باقية (الترتيب وحده يكشفه)",
        "في غير موضعها",
    ),
]

MUST_PASS = [
    ("D03", "الجرعة 2.50 مل لكل لتر، ولا تزد عليها.", "2.50 = 2.5 عدداً"),
    ("D03", "الجرعة اثنان فاصلة خمسة مل لكل لتر، ولا تزد عليها.", "فاصلةٌ منطوقة"),
    ("D03", "الجرعة اثنان فاصلة خمسون مل لكل لتر، ولا تزد عليها.", "2.50 منطوقة = 2.5"),
    ("D03", "الجرعة ٢٫٥ مل لكل لتر، ولا تزد عليها.", "أرقامٌ هنديّة وفاصلةٌ عربيّة"),
    ("D01", "اخلط مليلتران ونصف من المبيد في كل لتر ماء.", "صيغةُ الرفع للمثنّى"),
    (
        "D04",
        "اسقِ النخلة مائة و عشرون لتراً كل سبعة أيام في الصيف.",
        "«و» منفصلة كما يكتبها num2words",
    ),
    (
        "M01",
        "مؤشر NDVI للحقل انخفض من صفر فاصلة ستة اثنان إلى صفر فاصلة أربعة واحد خلال أسبوعين.",
        "خاناتٌ بعد الفاصلة واحدةً واحدة",
    ),
    ("T02", "ابدأ الحصاد في الأسبوع الثالث من أكتوبر ألفين وستة وعشرين.", "صيغةُ النصب/الجرّ"),
    (
        "D06",
        "درجة الحرارة المتوقعة غداً ثمانٍ وثلاثون درجة مئوية والرطوبة خمسة وأربعون في المئة.",
        "«في المئة» = ٪",
    ),
    (
        "N04",
        "إذا كانت سرعة الرياح أكثر من ١٥ كيلومتراً في الساعة لا ترش.",
        "الشرطُ قبل النهي: المعنى نفسه",
    ),
]


FAKE_WHISPER_CLI = """#!/usr/bin/env python3
# يحاكي whisper-cli: يقرأ -m و-f، ويطبع التفريغ من «النموذج» (جدولٌ JSON)، ويسجّل argv كما وصله.
import json, sys, pathlib
argv = sys.argv[1:]
model, wav = pathlib.Path(argv[argv.index("-m") + 1]), pathlib.Path(argv[argv.index("-f") + 1])
with open(model.parent / "argv.log", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv, ensure_ascii=False) + "\\n")
table = json.loads(model.read_text(encoding="utf-8"))
action = table.get("_actions", {}).get(wav.stem)
if action == "fail":
    sys.exit("decoder crashed")
if action == "tamper_model":
    model.write_text(model.read_text(encoding="utf-8") + " ", encoding="utf-8")
if action == "hang_with_child":
    import subprocess, time
    child = subprocess.Popen(["sleep", "30"])
    sys.path.insert(0, "@HERE@")
    import procs  # هويّةُ الابن (زمنُ بدئه) تُسجَّل عند إنشائه — إن كان /proc لفضائنا، وإلّا null
    (model.parent / "child.start").write_text(json.dumps(procs.starttime(child.pid)))
    (model.parent / "child.pid").write_text(str(child.pid))
    time.sleep(30)
print(table[wav.stem])
"""

# faster_whisper وهميّة: «النموذج» جدولٌ JSON، و``_sleep`` يؤخّر تفريغَ مقطعٍ بعينه (مكتبةٌ لا تعود في الوقت)
FAKE_FASTER_WHISPER = """
import json, pathlib, time
class _Seg:
    def __init__(self, text): self.text = text
class WhisperModel:
    def __init__(self, path, **kw):
        import os, sys
        assert os.environ.get("HF_HUB_OFFLINE") == "1", "العاملُ لم يُشغَّل بلا شبكة Hub"
        self.table = json.loads((pathlib.Path(path) / "table.json").read_text(encoding="utf-8"))
        if self.table.get("_partial_on_load"):  # حرفٌ بلا نهاية سطر ثمّ تعليقٌ أثناء التحميل
            sys.stdout.write("x"); sys.stdout.flush(); time.sleep(30)
    def transcribe(self, wav, **kw):
        stem = pathlib.Path(wav).stem
        if stem in self.table.get("_partial", []):  # حرفٌ بلا نهاية سطر ثمّ تعليق: readline() كان يحجب هنا
            import sys
            sys.stdout.write("x"); sys.stdout.flush(); time.sleep(30)
        time.sleep(self.table.get("_sleep", {}).get(stem, 0))
        delay = self.table.get("_lazy", {}).get(stem)
        if delay is None:
            return [_Seg(self.table[stem])], None
        def segments():  # كما في faster-whisper: يعود فوراً، والفكُّ الفعليّ عند الاستهلاك
            for word in self.table[stem].split():
                time.sleep(delay)
                yield _Seg(word)
        return segments(), None
"""


def _asr_fixture(
    root: Path, transcripts: dict, actions: dict | None = None, **cfg_over
) -> tuple[Path, Path]:
    run = root / "run"
    (run / "wav").mkdir(parents=True)
    rows = []
    for sid in transcripts:
        path = run / "wav" / f"{sid}.wav"
        with wave.open(str(path), "wb") as w:
            (
                w.setnchannels(1),
                w.setsampwidth(2),
                w.setframerate(16000),
                w.writeframes(b"\x10\x00" * 1600),
            )
        rows.append(
            {"id": sid, "ok": True, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    (run / "result.json").write_text(
        json.dumps({"run_id": "fake-1", "engine": "fake", "sentences": rows}), encoding="utf-8"
    )
    binary = root / "whisper-cli"
    binary.write_text(
        FAKE_WHISPER_CLI.replace("/usr/bin/env python3", sys.executable).replace(
            "@HERE@", str(HERE)
        ),
        encoding="utf-8",
    )
    binary.chmod(0o755)
    model = root / "model.json"
    model.write_text(
        json.dumps(transcripts | {"_actions": actions or {}}, ensure_ascii=False), encoding="utf-8"
    )
    pkg = root / "fakelib" / "faster_whisper"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(FAKE_FASTER_WHISPER, encoding="utf-8")
    cfg = {
        "name": "fake-whisper-cli",
        "version": "0",
        "adapter": "whisper_cpp",
        "binary": str(binary),
        "model_path": str(model),
        "language": "ar",
        "params": {"beam_size": 1, "temperature": 0.0},
    }
    cfg.update(cfg_over)
    if (
        cfg["adapter"] == "faster_whisper"
    ):  # مجلّدُ نموذجٍ كما تطلبه المكتبة: جدولُ الوهم + tokenizer.json
        fw = root / "fwmodel"
        fw.mkdir()
        (fw / "table.json").write_text(model.read_text(encoding="utf-8"), encoding="utf-8")
        (fw / "tokenizer.json").write_text("{}", encoding="utf-8")
        cfg["model_path"] = str(fw)
        cfg.pop("binary", None)
    (root / "asr.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return run, root / "asr.json"


def _table(root: Path) -> Path:
    return root / "fwmodel" / "table.json" if (root / "fwmodel").is_dir() else root / "model.json"


def _screen(
    run: Path,
    cfg: Path,
    out: Path,
    sigchld_ign: bool = False,
    facts: Path | None = None,
    path_prefix: Path | None = None,
):
    env = dict(os.environ, PYTHONPATH=str(cfg.parent / "fakelib"))
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env.get('PATH', '')}"
    done = subprocess.run(
        [
            sys.executable,
            str(HERE / "asr_screen.py"),
            str(run),
            "--asr-config",
            str(cfg),
            "--out",
            str(out),
            *(["--facts", str(facts)] if facts else []),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        preexec_fn=(lambda: signal.signal(signal.SIGCHLD, signal.SIG_IGN)) if sigchld_ign else None,
    )
    report = (
        json.loads((out / "asr_screen.json").read_text(encoding="utf-8"))
        if (out / "asr_screen.json").exists()
        else {}
    )
    return done.returncode, report, done.stderr.strip()[-160:]


def _liveness_verdict(base_ok: bool, group_gone, status: str) -> str:
    """FAIL: الشرطُ لم يتحقّق، أو المجموعةُ باقية، أو الابنُ حيٌّ بهويّته (أو لم يُسجَّل). BLOCKED: تعذّر الإثبات في
    هذا الفضاء — ليس نجاحاً ولا بقاءً. PASS: زوالٌ مُثبَت للمجموعة والابن."""
    if not base_ok or group_gone is False or status not in (*procs.NOT_ALIVE, "unverifiable"):
        return "FAIL"
    if group_gone is None or status == "unverifiable":
        return "BLOCKED"
    return "PASS"


def _hang_child_case(good: dict) -> tuple:
    """v7/v14 — مهلةُ whisper_cpp تُفرض بقتل مجموعة العمليّات، والحكمُ ببقاء الابن بهويّته وفي فضاء PID المختبِر."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run, cfg = _asr_fixture(root, good, actions={"D03": "hang_with_child"}, timeout_s=0.5)
        t0 = time.monotonic()
        rc, rep, err = _screen(run, cfg, root / "out")
        wall = time.monotonic() - t0
        d03 = {x["sentence_id"]: x for x in rep.get("clips", [])}.get("D03", {})
        child = int((root / "child.pid").read_text()) if (root / "child.pid").exists() else None
        start = (
            json.loads((root / "child.start").read_text())
            if (root / "child.start").exists()
            else None
        )
        # الحكمُ في فضاء PID هذه العمليّة وبهويّة الابن: /proc/<رقمه> في فضاءٍ آخر عمليّةٌ أخرى (مراجعةُ المالك على v13:
        # الابنُ sleep برقم 172 و/proc/172 غيرُه ⇒ child_alive=True كاذب). الزومبي ميّت، والرقمُ الموروث ليس الابن.
        status, why = procs.pid_status(child, start) if child else ("missing", "لم يُسجَّل رقمُ الابن")
        verdict = _liveness_verdict(
            rc == 0 and d03.get("screen") == "EVALUATOR_TIMEOUT" and wall < 20,
            (d03.get("timeout") or {}).get("group_gone"),
            status,
        )
        return (
            verdict,
            "ASR whisper_cpp: مقيِّمٌ عالقٌ له ابن ⇒ EVALUATOR_TIMEOUT، والمجموعةُ والابنُ قُتلا "
            "(حكمٌ بهويّة الابن وفي فضاء PID المختبِر)",
            f"screen={d03.get('screen')} timeout={d03.get('timeout')} child={child} start={start} "
            f"status={status} ({why}) wall={wall:.1f}s",
        )


def _fake_proc(root: Path, nspid: list[int], procs_: dict[int, tuple[str, int, int]]) -> Path:
    """/proc مصطنعة: ``self/status`` بسطر NSpid، و``<pid>/stat`` بحالةٍ ومجموعةٍ وزمنِ بدء (الحقل 22)."""
    (root / "self").mkdir(parents=True)
    (root / "self" / "status").write_text("Name:\tx\nNSpid:\t" + "\t".join(map(str, nspid)) + "\n")
    for pid, (state, pgrp, start) in procs_.items():
        (root / str(pid)).mkdir()
        fields = [state, "1", str(pgrp), str(pgrp)] + ["0"] * 15 + [str(start), "0", "0"]
        (root / str(pid) / "stat").write_text(f"{pid} (name with ) paren) " + " ".join(fields))
    return root


def procs_cases(corpus: dict) -> list:
    """v14 — حياةُ العمليّة تُحكم بهويّتها وفي فضاء PID المختبِر (مراجعةُ المالك على v13: /proc/172 كانت عمليّةً
    أخرى غيرَ الابن sleep ذي الرقم 172، فخرج child_alive=True كاذباً)."""
    results = []
    me, pg = os.getpid(), os.getpgrp()
    with tempfile.TemporaryDirectory() as tmp:
        other = _fake_proc(Path(tmp) / "other", [me + 100000], {me: ("R", pg, 5)})
        nested = _fake_proc(Path(tmp) / "nested", [me + 100000, me], {me: ("R", pg, 5)})
        mine = _fake_proc(Path(tmp) / "mine", [me], {me: ("S", pg, 777)})
        zomb = _fake_proc(Path(tmp) / "zomb", [me], {me: ("Z", pg, 777)})
        got = {
            "ns_other": procs.proc_namespace(other)[0],
            "ns_nested": procs.proc_namespace(nested)[0],
            "ns_mine": procs.proc_namespace(mine)[0],
            "other": procs.pid_status(me, 5, other)[0],
            "nested": procs.pid_status(me, 5, nested)[0],
            "same": procs.pid_status(me, 777, mine)[0],
            "reused": procs.pid_status(me, 778, mine)[0],
            "no_start": procs.pid_status(me, None, mine)[0],
            "zombie": procs.pid_status(me, 777, zomb)[0],
            "start_other": procs.starttime(me, other),
            "start_mine": procs.starttime(me, mine),
            "group_other": procs.group_status(pg, other)[0],
            "group_mine": procs.group_status(pg, mine)[0],
        }
    want = {
        "ns_other": False,
        "ns_nested": False,
        "ns_mine": True,
        "other": "unverifiable",
        "nested": "unverifiable",
        "same": "alive",
        "reused": "reused",
        "no_start": "alive",
        "zombie": "dead",
        "start_other": None,
        "start_mine": 777,
        "group_other": "unverifiable",
        "group_mine": "alive",
    }
    bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    results.append(
        (
            "PASS" if not bad else "FAIL",
            "procs: /proc لفضاءٍ آخر (أو أب) ⇒ unverifiable لا «حيّة»؛ زمنُ بدءٍ مختلف ⇒ reused؛ الزومبي ⇒ dead",
            f"خطأ {bad}" if bad else f"{len(want)} حكماً",
        )
    )
    previous = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    try:
        child = os.fork()
        if child == 0:
            os._exit(0)
        os.waitpid(child, 0)
    finally:
        signal.signal(signal.SIGCHLD, previous)
    gone = procs.pid_status(child, None, Path(tempfile.gettempdir()) / "no-such-proc")
    results.append(
        (
            "PASS" if gone[0] == "gone" else "FAIL",
            "procs: عمليّةٌ حُصدت ⇒ gone بـkill(pid, 0) وحده، ولو كان /proc غيرَ مقروء",
            f"{gone}",
        )
    )
    table = {
        (True, True, "gone"): "PASS",
        (True, True, "dead"): "PASS",
        (True, True, "reused"): "PASS",
        (True, None, "gone"): "BLOCKED",
        (True, True, "unverifiable"): "BLOCKED",
        (True, False, "gone"): "FAIL",
        (True, True, "alive"): "FAIL",
        (True, True, "missing"): "FAIL",
        (False, True, "gone"): "FAIL",
        (True, None, "alive"): "FAIL",
    }
    bad = {k: (_liveness_verdict(*k), v) for k, v in table.items() if _liveness_verdict(*k) != v}
    results.append(
        (
            "PASS" if not bad else "FAIL",
            "حكمُ البقاء: تعذّرُ الإثبات ⇒ BLOCKED لا PASS، والحيُّ بهويّته أو المجموعةُ الباقية ⇒ FAIL",
            f"خطأ {bad}" if bad else f"{len(table)} صفّاً",
        )
    )
    # _kill_group لا يدّعي «group_gone» بلا إثبات: تعذّرُ الحكم ⇒ None، وعضوٌ حيّ ⇒ False — لا True في أيٍّ منهما
    import asr_screen

    got = {}
    real_status, real_reap = asr_screen.procs.group_status, asr_screen.procs.reap_group
    try:
        asr_screen.procs.reap_group = lambda pgid: 0
        for label, fake in (
            ("unverifiable", ("unverifiable", [], "/proc لفضاءٍ آخر")),
            ("alive", ("alive", [4242], "حيّ")),
        ):
            asr_screen.procs.group_status = lambda pgid, _f=fake: _f
            proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
            info = asr_screen._kill_group(proc)
            got[label] = (info.get("group_gone"), info.get("alive"), "unverifiable" in info)
    finally:
        asr_screen.procs.group_status, asr_screen.procs.reap_group = real_status, real_reap
    results.append(
        (
            "PASS"
            if got == {"unverifiable": (None, None, True), "alive": (False, [4242], False)}
            else "FAIL",
            "ASR _kill_group: تعذّرُ الإثبات ⇒ group_gone=None مع سببه، وعضوٌ حيّ ⇒ False — لا «قُتلت» بلا دليل",
            f"got={got}",
        )
    )
    # مسبارُ القدرة لا يعلق: أبٌ يخرج وحفيدٌ يُمسك الأنبوب (شكلُ bwrap تحت /proc لفضاءٍ آخر) ⇒ مهلةٌ وقتلُ المجموعة
    # والحفيدُ اليتيم يتبنّاه الاختبار (subreaper) فيُحصَد هنا: موتُه بـSIGKILL يُثبَت بـwaitpid في أيّ فضاء PID —
    # لا بقراءة /proc ولا بـ«غير قابل للتحقّق» (تحت unshare -p -f يصير زومبي لـPID 1 = الاختبار نفسه).
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = Path(tmp) / "grandchild.pid"
        adopted = procs.become_subreaper()
        try:
            t0 = time.monotonic()
            ok, why = procs.probe(
                ["sh", "-c", f"sleep 30 & echo $! > {pidfile}; exit 0"], timeout=0.5
            )
            wall = time.monotonic() - t0
            gpid = int(pidfile.read_text()) if pidfile.exists() else None
            killed_by = None
            for _ in range(200 if gpid else 0):
                try:
                    pid, status = os.waitpid(gpid, os.WNOHANG)
                except ChildProcessError:
                    break  # ليس ابناً لنا (لا subreaper): يُحكم بـpid_status وحده
                if pid:
                    killed_by = (
                        os.WTERMSIG(status)
                        if os.WIFSIGNALED(status)
                        else f"exit {os.WEXITSTATUS(status)}"
                    )
                    break
                time.sleep(0.01)
            gstate = procs.pid_status(gpid)[0] if gpid else "missing"
        finally:
            procs.become_subreaper(False)
    base_ok = not ok and "علِق" in why and wall < 5 and killed_by in (None, signal.SIGKILL)
    verdict = _liveness_verdict(base_ok, True, gstate)
    results.append(
        (
            verdict,
            "procs.probe: أبٌ يخرج وحفيدُه يُمسك الأنبوب ⇒ فشلٌ بمهلة (لا تعليق) والحفيدُ قُتل",
            f"ok={ok} wall={wall:.1f}s grandchild={gpid}:{gstate} subreaper={adopted} "
            f"killed_by={killed_by} {why[:80]}",
        )
    )
    # bwrap لا يُعتمد حين /proc لفضاءٍ آخر (أبوه يفتح /proc/<رقم ابنه>): حكمٌ حتميّ بلا تشغيل
    real_ns = procs.proc_namespace
    try:
        procs.proc_namespace = lambda proc_root=procs.PROC: (False, "مصطنع")
        bw = procs.bwrap_probe(["sh", "-c", "exit 0"])
    finally:
        procs.proc_namespace = real_ns
    results.append(
        (
            "PASS" if bw[0] is False and "bwrap لا يُعتمد" in bw[1] else "FAIL",
            "procs.bwrap_probe: /proc لفضاءٍ آخر ⇒ غيرُ متاح حتميّاً (لا نجاحٌ مرّةً وتعليقٌ مرّة)",
            f"{bw}",
        )
    )
    # إعادةُ إنتاج مراجعة المالك حرفيّاً: فضاءُ PID جديد و/proc المركَّب لفضاء الأب (unshare -p -f بلا --mount-proc)
    good = {sid: corpus[sid] for sid in ("D03", "N01")} | {
        "N04": corpus["N04"].replace("لا ترش", "ترش")
    }
    inner = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); import procs, semantic_selftest as t; "
        "print(json.dumps({'getpid': __import__('os').getpid(), 'ns': procs.proc_namespace(), "
        "'case': t._hang_child_case(json.loads(sys.argv[2]))}, ensure_ascii=False))"
    )
    try:
        done = subprocess.run(
            [
                "unshare",
                "-p",
                "-f",
                "--",
                sys.executable,
                "-c",
                inner,
                str(HERE),
                json.dumps(good, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        done = None
        why = f"{type(exc).__name__}: {exc}"
    if done is None or done.returncode != 0 or not done.stdout.strip():
        results.append(
            (
                "BLOCKED",
                "procs: الابنُ في فضاء PID جديد و/proc لفضاء الأب (unshare -p -f)",
                f"تعذّر إنشاءُ فضاء PID هنا: {why if done is None else (done.stderr.strip() or done.returncode)}"[
                    :200
                ],
            )
        )
    else:
        r = json.loads(done.stdout.strip().splitlines()[-1])
        status, name, detail = r["case"]
        mismatch = r["ns"][0] is False
        results.append(
            (
                "PASS"
                if mismatch and status == "PASS"
                else "FAIL"
                if status == "FAIL" or not mismatch
                else status,
                "procs: مراجعةُ المالك على v13 — عالقٌ له ابن في فضاء PID جديد و/proc لفضاء الأب "
                "⇒ لا «child_alive» كاذب",
                f"getpid={r['getpid']} ns={r['ns']} inner={status}: {detail}"[:400],
            )
        )
    return results


def asr_cases(corpus: dict) -> list:
    import asr_screen

    results = []
    good = {sid: corpus[sid] for sid in ("D03", "N01")} | {
        "N04": corpus["N04"].replace("لا ترش", "ترش")
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run, cfg = _asr_fixture(root, good)
        rc, rep, err = _screen(run, cfg, root / "out")
        clips = {c["sentence_id"]: c for c in rep.get("clips", [])}
        results.append(
            (
                "PASS"
                if rc == 0
                and rep["summary"]
                == {
                    "NO_FLAG_ON_DECLARED_CHECKS": 2,
                    "FLAGGED": 1,
                    "REVIEW_UNCOVERED_CONTENT": 0,
                    "EVALUATOR_FAILED": 0,
                    "EVALUATOR_TIMEOUT": 0,
                }
                and clips["N04"]["screen"] == "FLAGGED"
                else "FAIL",
                "ASR: تفريغٌ أسقط «لا» ⇒ علَم، والسليمان بلا علَم",
                f"rc={rc} {rep.get('summary')} {err}",
            )
        )
        logged = [
            json.loads(line)
            for line in (root / "argv.log").read_text(encoding="utf-8").splitlines()
        ]
        recorded = [c["invocation"]["argv"] for c in rep.get("clips", [])]
        results.append(
            (
                "PASS"
                if recorded == logged
                and all(
                    c["evaluator"].get("model_sha256")
                    and c["evaluator"].get("binary_sha256")
                    and c["reference_text_in_invocation"] is False
                    for c in clips.values()
                )
                else "FAIL",
                "ASR: الاستدعاءُ الفعليّ (argv كما وصل المقيِّم) وبصمتا النموذج والملفّ التنفيذيّ محفوظةٌ لكلّ مقطع",
                f"argv={recorded[:1]}",
            )
        )
        results.append(
            (
                "PASS" if rep.get("network_probe", {}).get("proves_isolation") is False else "FAIL",
                "ASR: مسبارُ الشبكة يُسجَّل مسباراً لا إثباتَ عزل",
                str(rep.get("network_probe")),
            )
        )
        rc, _, err = _screen(run, cfg, root / "out")
        results.append(("PASS" if rc == 5 else "FAIL", "ASR: مجلّدُ ناتجٍ موجود ⇒ رفض", f"rc={rc}"))
    ref = corpus["D03"]
    # كلُّ هجومٍ يجب أن يُرفض **في التحقّق من الإعداد** وبسببه — لا أن يمرّ ثمّ تلتقطه طبقةٌ لاحقة أو ينهار
    attacks = (
        (
            "command حرٌّ فيه --initial-prompt (ثغرةُ v5)",
            {"command": ["whisper-cli", "--initial-prompt", ref, "-f", "{wav}"]},
            "مفاتيحُ غيرُ معروفة",
        ),
        ("وسائطُ إضافيّة extra_args", {"extra_args": ["--prompt", ref]}, "مفاتيحُ غيرُ معروفة"),
        ("معاملٌ غيرُ مسموح initial_prompt", {"params": {"initial_prompt": ref}}, "معاملٌ غيرُ مسموح"),
        ("معاملٌ مسموحٌ بقيمةٍ نصّيّة", {"params": {"beam_size": f"5 --prompt {ref}"}}, "ليس int"),
        ("لغةٌ تحمل وسيطاً", {"language": f"ar --prompt {ref}"}, "لغةٌ غير مسموحة"),
        ("محوّلٌ غيرُ معروف", {"adapter": "command"}, "محوّلٌ غير معروف"),
    )
    for label, over, reason in attacks:
        with tempfile.TemporaryDirectory() as tmp:
            run, cfg = _asr_fixture(Path(tmp), good, **over)
            rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
            results.append(
                (
                    "PASS" if rc != 0 and not rep and reason in err else "FAIL",
                    f"ASR: {label} ⇒ رفضٌ بسببه",
                    f"rc={rc} {err[-80:]}",
                )
            )
    leak = asr_screen.reference_in({"argv": ["whisper-cli", "-f", "x.wav", "--prompt", "تزد"]}, ref)
    clean = asr_screen.reference_in(
        {"argv": ["whisper-cli", "-l", "ar", "-bs", "5", "-f", "D03.wav"]}, ref
    )
    results.append(
        (
            "PASS" if leak and not clean else "FAIL",
            "ASR: reference_text_in_invocation مقيسٌ على الاستدعاء (يكشف كلمةً من المرجع، ولا يُنذر بلا سبب)",
            f"leak={leak} clean={clean}",
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        run, cfg = _asr_fixture(Path(tmp), good)
        (run / "wav" / "D03.wav").write_bytes(b"RIFF-tampered")
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
        results.append(
            ("PASS" if rc != 0 and not rep else "FAIL", "ASR: مقطعٌ تغيّرت بايتاته ⇒ رفض", f"rc={rc}")
        )
    with tempfile.TemporaryDirectory() as tmp:
        run, cfg = _asr_fixture(Path(tmp), good, actions={"N01": "fail"})
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
        n01 = {c["sentence_id"]: c for c in rep.get("clips", [])}.get("N01", {})
        results.append(
            (
                "PASS" if rc == 0 and n01.get("screen") == "EVALUATOR_FAILED" else "FAIL",
                "ASR: فشلُ المقيِّم على مقطع ⇒ EVALUATOR_FAILED لا «بلا علَم»",
                f"{n01.get('screen')}",
            )
        )
    with tempfile.TemporaryDirectory() as tmp:  # v9 — asr_screen نفسُه ورث SIGCHLD=SIG_IGN
        run, cfg = _asr_fixture(Path(tmp), good, actions={"N01": "fail"})
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out", sigchld_ign=True)
        n01 = {c["sentence_id"]: c for c in rep.get("clips", [])}.get("N01", {})
        results.append(
            (
                "PASS" if n01.get("screen") == "EVALUATOR_FAILED" else "FAIL",
                "ASR تحت SIGCHLD=SIG_IGN موروث: مقيِّمٌ يخرج بخطأ ⇒ EVALUATOR_FAILED (لا رمزَ 0 زائفاً)",
                f"screen={n01.get('screen')} error={n01.get('evaluator_error')}",
            )
        )
    with tempfile.TemporaryDirectory() as tmp:
        run, cfg = _asr_fixture(Path(tmp), good, actions={"D03": "tamper_model"})
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
        results.append(
            (
                "PASS" if rc != 0 and not rep else "FAIL",
                "ASR: تغيّرت الأوزان أثناء الفرز ⇒ رفض",
                f"rc={rc} {err[-60:]}",
            )
        )
    # v7 — المحتوى غيرُ المغطّى لا يختفي تحت «بلا علَم»
    owner = "لا ترش إذا كان الجهاز سليماً. سرعة الرياح أكثر من ١٥ كيلومتراً في الساعة."
    texts = {
        "D03": "الجرعة 2.5 مل تقريباً لكل لتر، ولا تزد عليها.",
        "N04": owner,
        "N01": corpus["N01"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        run, cfg = _asr_fixture(Path(tmp), texts)
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
        c = {x["sentence_id"]: x for x in rep.get("clips", [])}
        results.append(
            (
                "PASS"
                if rc == 0
                and c["D03"]["screen"] == "REVIEW_UNCOVERED_CONTENT"
                and "تقريبا" in c["D03"]["uncovered_content"]
                and c["N01"]["screen"] == "NO_FLAG_ON_DECLARED_CHECKS"
                else "FAIL",
                "ASR: تفريغٌ يجتاز المعلن وفيه محتوى غيرُ مغطّى ⇒ REVIEW_UNCOVERED_CONTENT لا «بلا علَم»",
                f"D03={c.get('D03', {}).get('screen')} {c.get('D03', {}).get('uncovered_content')}",
            )
        )
        n04 = c.get("N04", {})
        results.append(
            (
                "PASS"
                if n04.get("screen") == "FLAGGED"
                and {"الجهاز", "سليما"} <= set(n04.get("uncovered_content", []))
                and any("جملةٍ مستقلّة" in f for f in n04.get("flags", []))
                else "FAIL",
                "ASR: مثالُ المالك (الشرطُ انتقل إلى الجهاز عبر جملةٍ مستقلّة) ⇒ FLAGGED بسببه، و«الجهاز، سليماً» مُسجَّلان",
                f"{n04.get('screen')} flags={n04.get('flags')} uncovered={n04.get('uncovered_content')}",
            )
        )
    # v7 — المهلةُ تُفرض بقتل مجموعة العمليّات، للمحوّلين
    results.append(_hang_child_case(good))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run, cfg = _asr_fixture(
            root,
            good,
            adapter="faster_whisper",
            binary=None,
            params={"beam_size": 1},
            timeout_s=0.05,
            load_timeout_s=60,
        )
        table = json.loads(_table(root).read_text(encoding="utf-8"))
        table["_sleep"] = {"D03": 0.2}
        _table(root).write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
        rc, rep, err = _screen(run, cfg, root / "out")
        c = {x["sentence_id"]: x for x in rep.get("clips", [])}
        d03 = c.get("D03", {})
        results.append(
            (
                "PASS"
                if rc == 0
                and d03.get("screen") == "EVALUATOR_TIMEOUT"
                and d03["timeout"].get("group_gone")
                and d03.get("seconds", 1) < 0.2
                and c.get("N01", {}).get("screen") == "NO_FLAG_ON_DECLARED_CHECKS"
                and c["N01"]["invocation"].get("process") == "subprocess"
                else "FAIL",
                "ASR faster_whisper: طلبٌ يكتمل بعد 0.20s ومهلتُه 0.05s ⇒ EVALUATOR_TIMEOUT قبل اكتماله، والمقطعُ التالي "
                "يُفرَّغ بعمليّةٍ جديدة",
                f"rc={rc} D03={d03.get('screen')} {d03.get('seconds')}s "
                f"timeout={d03.get('timeout')} N01={c.get('N01', {}).get('screen')} {err[-80:]}",
            )
        )
    # الزومبي ميّتٌ لم يُحصَد — حالتان: (أ) /proc مصطنعة حتميّة في كلّ بيئة؛ (ب) زومبي حقيقيّ تحت أبٍ مضبوط.
    # v8 كان يفترض أنّ «true» يبقى زومبي؛ في بيئةٍ ورث فيها المشغّلُ SIGCHLD=SIG_IGN تحصده النواة فوراً فيختفي
    # من /proc وتنهار الحالة (مراجعةُ المالك: semantic_selftest.py:279).
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp)
        for pid, state, pgrp in (
            (101, "Z", 777),
            (102, "S", 777),
            (103, "R", 888),
            (104, "Z", 888),
        ):
            (fake / str(pid)).mkdir()
            (fake / str(pid) / "stat").write_text(f"{pid} (proc name) {state} 1 {pgrp} {pgrp} 0 -1")
        (fake / "105").mkdir()  # مجلّدُ عمليّةٍ زالت ملفُّ stat منها
        # تُسرَد ثمّ يفشل فتحُها: stat يطابق النمط ويرفع OSError عند القراءة (رابطٌ معلّق لا يصلح: glob يتجاوزه)
        (fake / "106" / "stat").mkdir(parents=True)
        got = (asr_screen.live_in_group(777, fake), asr_screen.live_in_group(888, fake))
    results.append(
        (
            "PASS" if got == ([102], [103]) else "FAIL",
            "ASR: /proc مصطنعة — الزومبي (Z) ليس حيّاً، والعضوُ الحيّ يُعدّ، والمختفي يُتجاوز",
            f"got={got}",
        )
    )
    previous = signal.signal(
        signal.SIGCHLD, signal.SIG_DFL
    )  # الأبُ المضبوط: بلا هذا تحصد النواةُ الابنَ فوراً
    try:
        child = os.fork()
        if child == 0:
            os.setsid()
            os._exit(0)
        # الحالُ تُقرأ بـprocs (فضاءُ /proc مُتحقَّقٌ أوّلاً): في فضاءٍ آخر /proc/<رقم الابن> عمليّةٌ أخرى
        ours, ns_why = procs.proc_namespace()
        state, alive = "unverifiable", None
        for _ in range(200 if ours else 0):
            state, _ = procs.pid_status(child)
            if state == "dead":
                break
            time.sleep(0.01)
        if ours:
            alive = asr_screen.live_in_group(child)
        os.waitpid(child, 0)
    finally:
        signal.signal(signal.SIGCHLD, previous)
    if state == "dead":
        results.append(
            (
                "PASS" if alive == [] else "FAIL",
                "ASR: زومبي حقيقيّ (fork تحت SIGCHLD=SIG_DFL، بلا waitpid) لا يُعدّ حيّاً",
                f"state={state} alive={alive}",
            )
        )
    else:
        results.append(
            (
                "BLOCKED",
                "ASR: زومبي حقيقيّ",
                f"تعذّر إنشاؤه أو قراءتُه في هذه البيئة (state={state}"
                f"{'' if ours else ' · ' + ns_why}) — الحالةُ المصطنعة تغطّي المنطق",
            )
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run, cfg = _asr_fixture(
            root, good, adapter="faster_whisper", params={"beam_size": 1}, timeout_s=0.3
        )
        table = json.loads(_table(root).read_text(encoding="utf-8"))
        table["_lazy"] = {
            "D03": 0.1,
            "N01": 0.0,
        }  # D03: ثماني كلمات × 0.1s تُستهلك بعد عودة transcribe فوراً
        _table(root).write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
        rc, rep, err = _screen(run, cfg, root / "out")
        c = {x["sentence_id"]: x for x in rep.get("clips", [])}
        results.append(
            (
                "PASS"
                if c.get("D03", {}).get("screen") == "EVALUATOR_TIMEOUT"
                and c.get("N01", {}).get("screen") == "NO_FLAG_ON_DECLARED_CHECKS"
                else "FAIL",
                "ASR faster_whisper: مولِّدُ مقاطع كسول (يعود فوراً ويُفكّ عند الاستهلاك) ⇒ المهلةُ تشمل الاستهلاك",
                f"D03={c.get('D03', {}).get('screen')} {c.get('D03', {}).get('seconds')}s N01={c.get('N01', {}).get('screen')}",
            )
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run, cfg = _asr_fixture(root, good, adapter="faster_whisper", params={"beam_size": 1})
        (root / "fwmodel" / "tokenizer.json").unlink()
        rc, rep, err = _screen(run, cfg, root / "out")
        results.append(
            (
                "PASS" if rc != 0 and not rep and "tokenizer.json" in err else "FAIL",
                "ASR faster_whisper: مجلّدُ نموذجٍ بلا tokenizer.json (المكتبةُ تجلبه من الشبكة بصمت) ⇒ رفضٌ بسببه",
                f"rc={rc} {err[-70:]}",
            )
        )
    # v9 — مهلةٌ تشمل وصولَ السطر كاملاً (مراجعةُ المالك: _readline(0.1) دام أكثر من ثانية على حرفٍ بلا \\n)
    for label, key, value, over in (
        ("أثناء التفريغ", "_partial", ["D03"], {"timeout_s": 0.2}),
        ("أثناء التحميل", "_partial_on_load", True, {"timeout_s": 5, "load_timeout_s": 0.3}),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run, cfg = _asr_fixture(
                root, good, adapter="faster_whisper", params={"beam_size": 1}, **over
            )
            table = json.loads(_table(root).read_text(encoding="utf-8"))
            table[key] = value
            _table(root).write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
            t0 = time.monotonic()
            rc, rep, err = _screen(run, cfg, root / "out")
            wall = time.monotonic() - t0
            c = {x["sentence_id"]: x for x in rep.get("clips", [])}
            d03 = c.get("D03", {})
            limit = over.get("load_timeout_s", over["timeout_s"])
            results.append(
                (
                    "PASS"
                    if d03.get("screen") == "EVALUATOR_TIMEOUT"
                    and d03["timeout"].get("group_gone")
                    and d03.get("seconds", 99) < limit + 0.5
                    and wall < 10
                    else "FAIL",
                    f"ASR faster_whisper: حرفٌ بلا نهاية سطر ثمّ تعليقٌ {label} ⇒ EVALUATOR_TIMEOUT خلال المهلة "
                    f"({limit}s)، والمجموعةُ قُتلت",
                    f"screen={d03.get('screen')} {d03.get('seconds')}s "
                    f"timeout={d03.get('timeout')} wall={wall:.1f}s",
                )
            )
    # مخزنُ القراءة: سطرٌ مجزّأٌ على دفعتين يكتمل، وسطران في دفعةٍ واحدة لا يضيع ثانيهما
    w = asr_screen._PersistentWorker(Path("unused"), {})
    split_writer = (
        "import os, time\n"
        "os.write(1, b'{\"a\"')\n"
        "time.sleep(0.2)\n"
        "os.write(1, b': 1}\\n{\"b\": 2}\\n')\n"
        "time.sleep(5)\n"
    )
    w.proc = subprocess.Popen(
        [sys.executable, "-c", split_writer],
        stdout=subprocess.PIPE,
        bufsize=0,
        start_new_session=True,
    )
    try:
        first, second = w._readline(2.0), w._readline(0.1)
    except Exception as exc:  # noqa: BLE001
        first, second = repr(exc), None
    finally:
        w.kill()
    results.append(
        (
            "PASS" if first == {"a": 1} and second == {"b": 2} else "FAIL",
            "ASR: سطرٌ مجزّأ على دفعتين يكتمل قبل الموعد، والسطرُ الثاني في الدفعة نفسها يبقى للطلب التالي",
            f"first={first} second={second}",
        )
    )
    with tempfile.TemporaryDirectory() as tmp:
        run, cfg = _asr_fixture(Path(tmp), good, timeout_s="0.5; --prompt x")
        rc, rep, err = _screen(run, cfg, Path(tmp) / "out")
        results.append(
            (
                "PASS" if rc != 0 and not rep and "timeout_s" in err else "FAIL",
                "ASR: timeout_s غيرُ عدديّ ⇒ رفضٌ بسببه",
                f"rc={rc} {err[-60:]}",
            )
        )
    # v8 — تلميحُ ASR للمراجع في الورقة العمياء: اختياريّ، مطابَقٌ ببصمة المقطع، لا يقرؤه score.py
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        hinted = {"D03": "الجرعة 2.5 مل تقريباً لكل لتر، ولا تزد عليها.", "N01": corpus["N01"]}
        run, cfg = _asr_fixture(root, hinted)
        doc = json.loads((run / "result.json").read_text(encoding="utf-8"))
        doc.update(
            harness_status="ok",
            network_isolation="PROVEN",
            environment={
                "corpus_sha256": hashlib.sha256((HERE / "corpus.tsv").read_bytes()).hexdigest()
            },
        )
        (run / "result.json").write_text(json.dumps(doc), encoding="utf-8")
        _screen(run, cfg, root / "asr")

        def blind(out, *extra):
            return subprocess.run(
                [
                    sys.executable,
                    str(HERE / "blind.py"),
                    str(run),
                    "--out",
                    str(root / out),
                    *extra,
                ],
                capture_output=True,
                text=True,
            )

        p1, p2 = blind("plain"), blind("hinted", "--asr-hints", str(root / "asr"))

        def read(d: str) -> list:
            return list(
                csv.DictReader(
                    (root / d / "rating_sheet.csv").read_text(encoding="utf-8-sig").splitlines()
                )
            )

        plain, rows = (
            (read("plain") if p1.returncode == 0 else []),
            (read("hinted") if p2.returncode == 0 else []),
        )
        import blind as blind_mod

        col = blind_mod.HINT_COLUMN
        d03 = next((r for r in rows if r["sentence_id"] == "D03"), {})
        keydoc = (
            json.loads((root / "hinted" / "KEY_DO_NOT_SHARE.json").read_text(encoding="utf-8"))
            if p2.returncode == 0
            else {}
        )
        results.append(
            (
                "PASS"
                if plain
                and col not in plain[0]
                and "REVIEW_UNCOVERED_CONTENT" in d03.get(col, "")
                and "تقريبا" in d03.get(col, "")
                and keydoc.get("machine_hints", {}).get("shown_to_reviewers") is True
                else "FAIL",
                "blind: تلميحُ ASR يظهر للمراجع **فقط** بـ--asr-hints، ويُسجَّل في المفتاح أنّه عُرض",
                f"plain_has_col={bool(plain) and col in plain[0]} D03={d03.get(col)} {p2.stderr[-80:]}",
            )
        )
        stale = json.loads((root / "asr" / "asr_screen.json").read_text(encoding="utf-8"))
        stale["clips"][0]["clip_sha256"] = "0" * 64
        (root / "asr_stale").mkdir()
        (root / "asr_stale" / "asr_screen.json").write_text(
            json.dumps(stale, ensure_ascii=False), encoding="utf-8"
        )
        p3 = blind("stale", "--asr-hints", str(root / "asr_stale"))
        results.append(
            (
                "PASS" if p3.returncode != 0 and "تلميحُ ASR" in p3.stderr else "FAIL",
                "blind: تلميحٌ لمقطعٍ بصمتُه مختلفة (قديم أو لتشغيلٍ آخر) ⇒ رفض",
                f"rc={p3.returncode} " + p3.stderr.strip().replace("\n", " ")[-80:],
            )
        )
    results += pocketsphinx_cases()
    readers = [
        f for f in ("score.py", "perf.py") if "asr_screen" in (HERE / f).read_text(encoding="utf-8")
    ]
    results.append(
        (
            "PASS" if not readers else "FAIL",
            "ASR: لا يقرأ الفرزَ score.py ولا perf.py (مساعدٌ لا حَكَم؛ "
            "blind.py يعرضه تلميحاً بطلبٍ صريح فقط)",
            str(readers),
        )
    )
    return results


# نصٌّ يجتاز الفحوص المعلنة لكن فيه محتوى لم تُغطِّه حقيقة — يجب أن **يُسجَّل** في coverage
UNCOVERED = [("D03", "الجرعة 2.5 مل تقريباً لكل لتر، ولا تزد عليها.", "تقريبا")]


def semantic_extra_cases() -> list:
    results = []
    errs = semantic.check("أي نص", {})
    results.append(
        ("PASS" if errs else "FAIL", "جملةٌ بلا حقائقَ معلنة لا تجتاز", errs[0] if errs else "قُبلت!")
    )
    for sid, text, token in UNCOVERED:
        errs, unc = semantic.check(text, FACTS[sid]), semantic.coverage(text, FACTS[sid])
        results.append(
            (
                "PASS" if not errs and token in unc else "FAIL",
                f"[{sid}] يجتاز المعلن ويُسجَّل المحتوى غيرُ المغطّى «{token}»",
                f"errors={errs} uncovered={unc}",
            )
        )
    # نطاقُ الشرط مستقلّاً عن «النفي غير المعلن»: النفيُ معلنٌ هنا، فلا يكشفه إلّا فحصُ النطاق
    text = "لا ترش إذا كانت سرعة الرياح ليست أكثر من ١٥ كيلومتراً في الساعة."
    declared = FACTS["N04"] | {"negations": ["لا ترش", "ليست أكثر"]}
    scoped = semantic.check(text, declared)
    allowed = semantic.check(
        text, declared | {"conditions": [{"marker": "إذا", "quantities": [1], "negated": True}]}
    )
    results.append(
        (
            "PASS" if any("نطاقُ الشرط" in e for e in scoped) and not allowed else "FAIL",
            "نفيٌ معلنٌ داخل الشرط بلا negated ⇒ خطأُ نطاق؛ ومع negated=true ⇒ يجتاز",
            f"scoped={scoped} allowed={allowed}",
        )
    )
    # v8 — ربطُ كمّيّات المصدر بالمحوَّل (مستلهَمٌ من normalize_with_mapping): يقارن القيمة لا الوجودَ وحده
    src = "الجرعة 2.5 مل لكل لتر"
    ok_map = semantic.quantity_mapping(src, "الجرعة اثنان فاصلة خمسة مل لكل لتر")
    bad_map = semantic.quantity_mapping(src, "الجرعة 25 مل لكل لتر")
    split_map = semantic.quantity_mapping(src, "الجرعة اثنان , خمسون مل لكل لتر")
    results.append(
        (
            "PASS"
            if len(ok_map) == 1
            and ok_map[0]["all_same"]
            and bad_map[0]["same_value"] is False
            and bad_map[0]["same_unit"] is True
            and len(split_map) == 2
            and not any(m["all_same"] for m in split_map)
            and split_map[1]["source"] is None
            else "FAIL",
            "mapping: 2.5 مل ↔ «اثنان فاصلة خمسة مل» متطابق · ↔ «25 مل» القيمةُ تختلف والوحدةُ لا · "
            "↔ «اثنان , خمسون» زوجان بلا نظير",
            f"ok={ok_map} bad={bad_map[0]} split={len(split_map)}",
        )
    )
    empty = [sid for sid, f in FACTS.items() if not semantic.has_facts(f)]
    results.append(
        ("PASS" if not empty else "FAIL", "كلُّ جملةٍ في النصوص لها حقائقُ معلنة", str(empty))
    )
    return results


REAL_TRANSCRIPT = "this is a synthetic the ph test for cider lol now field operation is requested"


def _ps_python() -> Path | None:
    """مفسّرٌ فيه pocketsphinx 5.1.1: BAKEOFF_PS_PYTHON أو ../venv_ps بجانب الحزمة — وإلّا تُسجَّل الحالةُ BLOCKED."""
    for cand in (
        os.environ.get("BAKEOFF_PS_PYTHON"),
        str(HERE.parent / "venv_ps" / "bin" / "python"),
    ):
        if (
            cand
            and Path(cand).is_file()
            and subprocess.run([cand, "-c", "import pocketsphinx"], capture_output=True).returncode
            == 0
        ):
            return Path(cand)
    return None


def pocketsphinx_cases() -> list:
    """v10 — محوّلُ PocketSphinx: ASR **حقيقيّ** على مقطع Flite من تشغيل المالك (fixtures/)، بلا نصٍّ مرجعيّ."""
    import asr_screen

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakemodel = root / "en-us"
        (fakemodel / "en-us").mkdir(parents=True)
        (fakemodel / "en-us" / "mdef").write_text("x")
        (fakemodel / "en-us.lm.bin").write_text("x")
        base = {
            "name": "ps",
            "version": "5.1.1",
            "adapter": "pocketsphinx",
            "model_path": str(fakemodel),
            "language": "en",
            "params": {},
        }
        for label, over, reason in (
            ("لغةٌ عربيّة لنموذجٍ إنجليزيّ", {"language": "ar"}, "لغةٌ غير مسموحة"),
            ("نموذجٌ بلا قاموس (Decoder يفكّ بالمضمَّن بصمت)", {}, "hmm وlm وdict"),
            ("معاملٌ غيرُ مسموح", {"params": {"beam": 1e-40}}, "معاملٌ غيرُ مسموح"),
            ("isolate_net غيرُ منطقيّ", {"isolate_net": "yes"}, "isolate_net"),
            ("python غيرُ موجود", {"python": str(root / "nope")}, "python غيرُ موجود"),
        ):
            cfg = root / "c.json"
            cfg.write_text(json.dumps(base | over, ensure_ascii=False), encoding="utf-8")
            try:
                asr_screen.load_config(cfg)
                got = "قُبل"
            except SystemExit as exc:
                got = str(exc)
            results.append(
                (
                    "PASS" if reason in got else "FAIL",
                    f"pocketsphinx: {label} ⇒ رفضٌ بسببه",
                    got[-90:],
                )
            )
    with (
        tempfile.TemporaryDirectory() as tmp
    ):  # ضابطٌ إيجابيّ: تفريغٌ **يحمل** «no field» لا يُرفع له علَمُ نفي
        root = Path(tmp)
        run, cfg = _asr_fixture(
            root, {"E01": "This is a synthetic test. No field operation is requested."}
        )
        rc, rep_, err = _screen(
            run, cfg, root / "out", facts=HERE / "fixtures" / "english_facts.json"
        )
        e01 = (rep_.get("clips") or [{}])[0]
        results.append(
            (
                "PASS"
                if e01.get("screen") == "REVIEW_UNCOVERED_CONTENT" and not e01.get("flags")
                else "FAIL",
                "ASR الإنجليزيّ — ضابطٌ إيجابيّ: «No field» محفوظٌ في التفريغ ⇒ لا علَمَ نفي (يبقى غيرُ المغطّى للمراجعة)",
                f"screen={e01.get('screen')} flags={e01.get('flags')} uncovered={e01.get('uncovered_content')}",
            )
        )
    # «unshare» لا يعزل (مثبَّتٌ معطوب أو مستبدَل): المسبارُ داخل المقيِّم يبلغ الهدف ⇒ يجب الرفض، لا ادّعاءُ عزل
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fakebin = root / "fakebin"
        fakebin.mkdir()
        (fakebin / "unshare").write_text(
            '#!/bin/sh\nwhile [ "$1" != "--" ]; do shift; done; shift; exec "$@"\n'
        )
        (fakebin / "unshare").chmod(0o755)
        run, cfg = _asr_fixture(
            root,
            {"D03": "الجرعة 2.5 مل لكل لتر، ولا تزد عليها."},
            adapter="faster_whisper",
            params={"beam_size": 1},
            isolate_net=True,
        )
        rc, rep_, err = _screen(run, cfg, root / "out", path_prefix=fakebin)
        outside = asr_screen._network_probe()["result"]
        results.append(
            (
                "PASS"
                if rc != 0 and not rep_ and "لا عزل" in err
                else "BLOCKED"
                if outside != "reachable"
                else "FAIL",
                "ASR isolate_net: «unshare» لا يعزل فعلاً ⇒ المسبارُ داخل المقيِّم يبلغ الهدف ⇒ رفض (لا ادّعاءَ عزل)",
                f"rc={rc} outside={outside} {err[-70:]}",
            )
        )
    leak = asr_screen.reference_in(
        {"kwargs": {"hint": "no field operation"}}, "No field operation is requested."
    )
    # مسارٌ بمسافات: لو عُدّت المساراتُ لانقسم إلى كلماتٍ تطابق المرجع («field» · «operation» · «requested»)
    path_only = asr_screen.reference_in(
        {"argv": ["-f", "/tmp/runs/no field operation requested.wav"]},
        "No field operation is requested.",
    )
    results.append(
        (
            "PASS" if leak and not path_only else "FAIL",
            "ASR: تسريبُ نصٍّ **إنجليزيّ** في الاستدعاء يُكشف (v9 كان يتجاوز اللاتينيّة)، وكلماتُ المسارات لا تُعدّ تسريباً",
            f"leak={leak} path_only={path_only}",
        )
    )
    py = _ps_python()
    if py is None:
        results.append(
            (
                "BLOCKED",
                "pocketsphinx: ASR حقيقيّ على مقطع Flite",
                "لا مفسّرَ فيه pocketsphinx (BAKEOFF_PS_PYTHON)",
            )
        )
        return results
    bundled = next(py.parent.parent.glob("lib/python*/site-packages/pocketsphinx/model/en-us"))
    isolate = (
        os.geteuid() == 0
        and shutil.which("unshare") is not None
        and subprocess.run(["unshare", "-n", "true"], capture_output=True).returncode == 0
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model = (
            root / "model-copy" / "en-us"
        )  # نسخةٌ خارج الحزمة: رجوعُ Decoder() الصامت إلى المضمَّن يظهر في المسارات الفعليّة
        shutil.copytree(bundled, model)
        run = root / "run"
        (run / "wav").mkdir(parents=True)
        clip = HERE / "fixtures" / "sahool_flite_test.wav"
        shutil.copyfile(clip, run / "wav" / "E01.wav")
        (run / "result.json").write_text(
            json.dumps(
                {
                    "run_id": "flite-owner",
                    "engine": "flite",
                    "sentences": [
                        {
                            "id": "E01",
                            "ok": True,
                            "sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        cfg = root / "asr.json"
        cfg.write_text(
            json.dumps(
                {
                    "name": "pocketsphinx",
                    "version": "5.1.1",
                    "adapter": "pocketsphinx",
                    "model_path": str(model),
                    "language": "en",
                    "params": {},
                    "python": str(py),
                    "isolate_net": isolate,
                    "timeout_s": 60,
                    "load_timeout_s": 120,
                }
            ),
            encoding="utf-8",
        )
        done = subprocess.run(
            [
                sys.executable,
                str(HERE / "asr_screen.py"),
                str(run),
                "--asr-config",
                str(cfg),
                "--out",
                str(root / "out"),
                "--facts",
                str(HERE / "fixtures" / "english_facts.json"),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        rep = (
            json.loads((root / "out" / "asr_screen.json").read_text(encoding="utf-8"))
            if done.returncode == 0
            else {}
        )
        c = (rep.get("clips") or [{}])[0]
        iso = rep.get("evaluator_network_isolation")
        actual = rep.get("evaluator_runtime", {}).get("decoder_config_actual") or {}
        uses_copy = bool(actual) and all(str(v).startswith(str(model)) for v in actual.values())
        results.append(
            (
                "PASS"
                if c.get("transcript") == REAL_TRANSCRIPT
                and c.get("screen") == "FLAGGED"
                and any("no field" in f for f in c.get("flags", []))
                and "now" in c.get("uncovered_content", [])
                and c.get("reference_text_in_invocation") is False
                and rep.get("evaluator_runtime", {}).get("library_version") == "5.1.1"
                and uses_copy
                and iso == ("PROVEN" if isolate else "NOT_REQUESTED")
                else "FAIL",
                "pocketsphinx **حقيقيّ** على مقطع Flite (بلا نصٍّ مرجعيّ): «No field» فُرِّغ «now field» ⇒ FLAGGED "
                "بسبب النفي المفقود، و«now» مُسجَّلٌ غيرَ مغطّى، وعزلُ شبكة المقيِّم "
                + ("PROVEN" if isolate else "غيرُ مطلوب"),
                f"screen={c.get('screen')} transcript={c.get('transcript')!r} isolation={iso} uses_copy={uses_copy} "
                f"{done.stderr.strip()[-80:]}",
            )
        )
    return results


def main() -> int:
    # مشغّلٌ ورّث SIGCHLD=SIG_IGN يجعل النواةَ تحصد الأبناءَ فوراً: waitpid ⇒ ECHILD ⇒ returncode = 0 لكلِّ ابن،
    # فيضيع فشلُه (مقيسٌ: 13 حالةَ رفضٍ صارت rc=0). يُعاد إلى الافتراضيّ قبل أيِّ عمليّةٍ فرعيّة، ويُسجَّل الموروث.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    results = []
    with (HERE / "corpus.tsv").open(encoding="utf-8") as fh:
        corpus = {r["id"]: r["text"] for r in csv.DictReader(fh, delimiter="\t")}
    raw_bad = {sid: semantic.check(text, FACTS[sid]) for sid, text in corpus.items()}
    raw_bad = {k: v for k, v in raw_bad.items() if v}
    results.append(
        (
            "PASS" if not raw_bad else "FAIL",
            f"الأصل: {len(corpus)} جملة تطابق حقائقها",
            str(raw_bad or ""),
        )
    )
    for sid, text, why, reason in MUST_FAIL:
        errs = semantic.check(text, FACTS[sid])
        hit = next((e for e in errs if reason in e), None)
        results.append(
            (
                "PASS" if hit else "FAIL",
                f"يكشف [{sid}] {why}",
                hit or (f"رُفض لسببٍ آخر لا «{reason}»: {errs}" if errs else "لم يُكشف!"),
            )
        )
    for sid, text, why in MUST_PASS:
        errs = semantic.check(text, FACTS[sid])
        results.append(("PASS" if not errs else "FAIL", f"يقبل [{sid}] {why}", "; ".join(errs)))
    results += semantic_extra_cases()
    results += asr_cases(corpus)
    results += procs_cases(corpus)
    for status, name, detail in results:
        print(f"{status:5} {name}  {detail}")
    failed = sum(s == "FAIL" for s, _, _ in results)
    blocked = sum(s == "BLOCKED" for s, _, _ in results)
    print(f"\n{len(results)} حالة · فشل {failed} · BLOCKED {blocked}")
    print(
        "حدّه: «اجتاز» = اجتاز فحوصَ الحقائق المعلنة لا «المعنى محفوظ». يفحص النصّ قبل التوليد، ولا يرى النحو،\n"
        "ولا يحكم على الصوت ولا يُغني عن المراجع البشريّ."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
