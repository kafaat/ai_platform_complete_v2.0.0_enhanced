"""Re-introduce each 0.4.2 defect on a copy of the package and confirm the tests catch it.
Writes verification/patch_0.4.2/mutations.json and one log per mutation."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

src = Path(__file__).resolve().parents[1]
evidence = src / "verification/patch_0.4.2"
evidence.mkdir(parents=True, exist_ok=True)
W, B, P = "sahool_qa/generators/water.py", "sahool_qa/waterbal.py", "sahool_qa/pipeline.py"
mutations = [
    (
        "stall_check",
        [
            (
                B,
                "            dh >= min_h and dv == 0 and not out_of_service(fw, well, x, y)\n",
                "            False\n",
            )
        ],
    ),
    (
        "stall_ignored_by_depth",
        [
            (
                W,
                "            if ip in VOLUME_PROBLEMS:  # a stalled hour meter",
                "            if False:  # a stalled hour meter",
            )
        ],
    ),
    (
        "zero_flow_without_status",
        [
            (
                W,
                "                ip, _ = instrument_problem(fw, sx, a, D, ctx.rules)",
                "                ip = None",
            ),
            (
                W,
                "                if dv <= 0:  # hours below",
                "                if False:  # hours below",
            ),
            (
                B,
                "            dh >= min_h and dv == 0 and not out_of_service(fw, well, x, y)\n",
                "            False\n",
            ),
        ],
    ),
    (
        "status_never_known",
        [
            (
                B,
                "    return s is not None and bool(days) and all(step_value(s, d) == 0 for d in days)",
                "    return False",
            )
        ],
    ),
    (
        "status_conflict",
        [(B, "        if dv > 0 and out_of_service(fw, well, x, y):", "        if False:")],
    ),
    ("hour_stall", [(B, "        if dv > 0 and dh <= 0:", "        if False:")]),
    ("inventory_warning", [(P, '    if water_inventory["without_inventory"]:', "    if False:")]),
    ("require_flag", [(P, "    if require_well_inventory:", "    if False:")]),
    (
        "flow_window_wording",
        [
            (
                W,
                "بتدفقها المقيس بين نهاية يوم {a} ونهاية يوم {D}، ",
                "بتدفقها المقيس خلال 7 أيام حتى {D}، ",
            )
        ],
    ),
    (
        "probe_wording",
        [(W, "متوسطاً للمنطقة الجذرية كلها أياً كان عمق المجس", "متوسطاً للمنطقة الجذرية")],
    ),
    (
        "parameter_lines",
        [("sahool_qa/preview.py", 'r"|θFC|θWP|Zr|p_table|Ea|fao_crop) = ",', 'r") = ",')],
    ),
    (
        "pumping_days_wording",
        [
            (
                W,
                '\n    "ليس منها"\n)',
                '\n    "منها"\n)',
            )
        ],
    ),
    (
        "hours_missing_from_context",
        [
            (
                W,
                '    cols = list(fw.of("meter").values()) + list(fw.of("pump_hours").values())\n    if cols:',
                '    cols = list(fw.of("meter").values())\n    if cols:',
            )
        ],
    ),
    (
        "status_missing_from_context",
        [
            (
                W,
                '        cards.table(t, recs)\n    if not fw.of("meter"):\n        cards.text(\n            f"{title}',
                '        cards.table(t, recs)\n    return\n    if not fw.of("meter"):\n        cards.text(\n            f"{title}',
            ),
            (W, "    _status_cards(f, fw, D, cards)", "    pass"),
        ],
    ),
]
results = []
for name, edits in mutations:
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "qa"
        shutil.copytree(
            src, dst, ignore=shutil.ignore_patterns("__pycache__", "demo_out", "verification")
        )
        for file, old, new in edits:
            f = dst / file
            s = f.read_text(encoding="utf-8")
            assert s.count(old) == 1, (name, old)
            f.write_text(s.replace(old, new, 1), encoding="utf-8")
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_water_04*.py",
                "-v",
            ],
            cwd=dst,
            text=True,
            capture_output=True,
        )
        log = p.stdout + p.stderr
        (evidence / f"{name}.log").write_text(log, encoding="utf-8")
        results.append(
            {
                "mutation": name,
                "exit_code": p.returncode,
                "caught": p.returncode != 0,
                "summary": log.strip().splitlines()[-1],
            }
        )
(evidence / "mutations.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2, ensure_ascii=False))
assert all(r["caught"] for r in results), [r["mutation"] for r in results if not r["caught"]]
