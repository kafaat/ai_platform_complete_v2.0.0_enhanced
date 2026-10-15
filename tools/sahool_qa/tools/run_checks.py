"""Run the offline suite and verify two independently generated demo exports."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_TESTS = 128  # 126 from the 0.4.2 release + 2 for migrations/init_v8.sql columns
DEMO_ITEMS = 538

# Arabic in the report must not depend on the runner's locale (LC_ALL=C, UTF-8 mode off).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-postgres", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    evidence = ROOT / "verification" / "integration"
    evidence.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (evidence / "tests.log").open("w", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": [{"test": str(t), "reason": why} for t, why in result.skipped],
        "require_postgres": args.require_postgres,
        "demo_verified": False,
    }
    ok = result.wasSuccessful() and result.testsRun >= MIN_TESTS
    if args.require_postgres and result.skipped:
        ok = False
    for test, trace in result.failures + result.errors:
        print(f"FAILED {test}\n{trace}", file=sys.stderr)
    if ok:
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for name in ("first", "second"):
                out = Path(tmp) / name
                run = subprocess.run(
                    [sys.executable, "-m", "sahool_qa", "demo", "--out", str(out)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    cwd=ROOT,
                )
                (evidence / f"{name}.log").write_text(run.stdout + run.stderr, encoding="utf-8")
                if run.returncode:
                    ok = False
                    break
                outputs.append(out / "qa")
            if len(outputs) == 2:
                manifests = [
                    json.loads((out / "manifest.json").read_text(encoding="utf-8"))
                    for out in outputs
                ]
                hashes = {}
                for split in ("train", "val", "test"):
                    payloads = [(out / f"{split}.jsonl").read_bytes() for out in outputs]
                    ok = ok and payloads[0] == payloads[1] and bool(payloads[0])
                    hashes[split] = hashlib.sha256(payloads[0]).hexdigest()
                for manifest in manifests:
                    ok = ok and not manifest["family_errors"] and not manifest.get("case_errors")
                    ok = ok and manifest["counts"]["items_total"] == DEMO_ITEMS
                report.update(
                    demo_verified=bool(ok), demo_hashes=hashes, counts=manifests[0]["counts"]
                )
                (evidence / "manifest.json").write_text(
                    json.dumps(manifests[0], ensure_ascii=False, indent=2), encoding="utf-8"
                )
    report["passed"] = bool(ok)
    (evidence / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
