"""أعطالٌ مزروعة لإصلاح v14 (هويّةُ العمليّة وفضاءُ PID): كلُّ طفرةٍ نسخةٌ معدَّلة من الحزمة في مجلّدٍ مؤقّت.

    python3 mutations_v14.py .

«قُتلت» = تغيّر حكمُ حالةٍ واحدةٍ على الأقلّ عن الأساس (PASS→FAIL أو PASS→BLOCKED)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(sys.argv[1]).resolve()
MUTS = [
    (
        "M1 procs: الفضاءُ «لنا» دائماً",
        "procs.py",
        'return ns == [me], f"NSpid={ns} getpid={me}"',
        'return True, f"NSpid={ns} getpid={me}"',
    ),
    (
        "M2 procs: آخرُ NSpid يكفي (فضاءٌ أب يمرّ)",
        "procs.py",
        "return ns == [me],",
        "return ns[-1] == me,",
    ),
    (
        "M3 procs: pid_status بلا فحص الفضاء",
        "procs.py",
        '    if not ours:\n        return (\n            "unverifiable",\n            f"الرقمُ',
        '    if False:\n        return (\n            "unverifiable",\n            f"الرقمُ',
    ),
    (
        "M4 procs: الهويّةُ مُتجاهَلة (لا reused)",
        "procs.py",
        "if start is not None and len(fields) > 19 and int(fields[19]) != start:",
        "if False:",
    ),
    ("M5 procs: الزومبي حيّ", "procs.py", 'DEAD_STATES = ("Z", "X")', 'DEAD_STATES = ("X",)'),
    (
        "M6 procs: ESRCH لا يُعدّ زوالاً",
        "procs.py",
        '        return "gone", "kill(pid, 0): ESRCH في فضاء PID هذه العمليّة"',
        "        pass",
    ),
    (
        "M7 procs: starttime بلا فحص الفضاء",
        "procs.py",
        "    if not proc_namespace(proc_root)[0]:\n        return None\n    fields",
        "    fields",
    ),
    (
        "M8 procs: group_status بلا فحص الفضاء",
        "procs.py",
        '    if not ours:\n        return (\n            "unverifiable",\n            [],',
        '    if False:\n        return (\n            "unverifiable",\n            [],',
    ),
    (
        "M9 asr_screen: لا subreaper",
        "asr_screen.py",
        '"subreaper": procs.become_subreaper()',
        '"subreaper": False',
    ),
    (
        "M10 asr_screen: تعذّرُ الإثبات ⇒ True",
        "asr_screen.py",
        'return {"killed_pgid": pgid, "group_gone": None, "unverifiable": why}',
        'return {"killed_pgid": pgid, "group_gone": True, "unverifiable": why}',
    ),
    (
        "M11 asr_screen: عضوٌ حيّ ⇒ True",
        "asr_screen.py",
        'return {"killed_pgid": pgid, "group_gone": False, "alive": alive, "evidence": why}',
        'return {"killed_pgid": pgid, "group_gone": True, "alive": alive, "evidence": why}',
    ),
    ("M12 asr_screen: لا حصدَ للمجموعة", "asr_screen.py", "        procs.reap_group(pgid)\n", ""),
    (
        "M13 selftest: unverifiable يُحسب نجاحاً",
        "semantic_selftest.py",
        '        return "BLOCKED"\n    return "PASS"\n',
        '        return "PASS"\n    return "PASS"\n',
    ),
    (
        "M14 selftest: الابنُ يُقرأ من /proc/<رقم> أعمى (v13)",
        "semantic_selftest.py",
        "status, why = procs.pid_status(child, start) if child else",
        'status, why = ("alive" if Path(f"/proc/{child}").exists() and Path(f"/proc/{child}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z" else "gone", "v13") if child else',
    ),
    (
        "M15 procs.probe: قتلُ الأب وحده لا المجموعة",
        "procs.py",
        "            os.killpg(proc.pid, signal.SIGKILL)",
        "            proc.kill()",
    ),
    (
        "M16 procs.probe: بلا مهلة",
        "procs.py",
        "_, err = proc.communicate(timeout=timeout)",
        "_, err = proc.communicate()",
    ),
    (
        "M17 procs.bwrap_probe: بلا فحص الفضاء",
        "procs.py",
        '    if not ours:\n        return False, f"/proc لفضاء PID آخر',
        '    if False:\n        return False, f"/proc لفضاء PID آخر',
    ),
]
DRIVER = """
import csv, sys; sys.path.insert(0, '.')
import semantic_selftest as t
c = {r['id']: r['text'] for r in csv.DictReader(open('corpus.tsv', encoding='utf-8'), delimiter='\\t')}
good = {sid: c[sid] for sid in ('D03', 'N01')} | {'N04': c['N04'].replace('لا ترش', 'ترش')}
res = t.procs_cases(c) + [t._hang_child_case(good)]
for s, n, d in res: print(s, '|', n[:70], '|', d[:160])
"""


def run(d):
    p = subprocess.run(
        [sys.executable, "-c", DRIVER], cwd=d, capture_output=True, text=True, timeout=300
    )
    return [
        line.split(" | ")[0] for line in p.stdout.splitlines() if " | " in line
    ], p.stdout + p.stderr[-300:]


base, _ = run(SRC)
print("الأساس:", base)
killed = 0
for name, f, old, new in MUTS:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "m"
        shutil.copytree(SRC, d, ignore=shutil.ignore_patterns("results", "__pycache__"))
        text = (d / f).read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"تعذّر   {name}: النمط ظهر {text.count(old)} مرّة")
            continue
        (d / f).write_text(text.replace(old, new), encoding="utf-8")
        got, out = run(d)
        diff = [
            f"#{i}:{a}→{b}" for i, (a, b) in enumerate(zip(base, got, strict=False)) if a != b
        ] or ([f"عددٌ {len(base)}→{len(got)}"] if len(got) != len(base) else [])
        k = bool(diff)
        killed += k
        print(
            f"{'قُتلت ' if k else 'نجت  '} {name}: {' '.join(diff) or 'لا فرق'}"
            + ("" if got else f"  [{out[-200:]}]")
        )
print(f"\nقُتلت {killed}/{len(MUTS)}")
