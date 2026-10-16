import hashlib
import json
import subprocess
from pathlib import Path

WORKSPACE = Path("/workspace/scratch/881ca3efb91d")
BASE = WORKSPACE / "sahool"
FINAL = WORKSPACE / "governance-final"
OUT = WORKSPACE / "evidence/final-witness-encoding"
PYTHON = WORKSPACE / "ci-venv/bin/python"
PIN = "239c01a47442df13d9cbb492017afae103b98dc8"
FILES = [
    "tests_v9/test_readiness_http_status.py",
    "tests_v9/test_learning_review_persistence_gap.py",
]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


assert git(BASE, "rev-parse", "HEAD") == PIN
assert not git(BASE, "status", "--porcelain", "--untracked-files=no"), "base tracked files dirty"
receipt = {
    "base_sha": PIN,
    "scope": "ASGI handlers/probe doubles for readiness; real writer with fake DB for U07; no deployment proof",
    "witnesses": [],
}
for relative in FILES:
    source = FINAL / relative
    data = source.read_bytes()
    destination = BASE / relative
    previous = destination.read_bytes() if destination.exists() else None
    item = {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob": git(FINAL, "hash-object", relative),
    }
    (OUT / (source.name + ".txt")).write_bytes(data)
    try:
        destination.write_bytes(data)
        assert destination.read_bytes() == source.read_bytes()
        for mode, root in [("red-main", BASE), ("green-final", FINAL)]:
            log = OUT / f"{source.stem}-{mode}.log"
            with log.open("wb") as output:
                result = subprocess.run(
                    [str(PYTHON), "-m", "pytest", relative, "-m", "unit", "-q"],
                    cwd=root,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
            item[mode] = {"exit_code": result.returncode, "log": log.name}
            assert (root / relative).read_bytes() == data
        assert item["red-main"]["exit_code"] == 1, item
        assert item["green-final"]["exit_code"] == 0, item
    finally:
        if previous is None:
            destination.unlink()
        else:
            destination.write_bytes(previous)
    receipt["witnesses"].append(item)
assert not git(BASE, "status", "--porcelain", "--untracked-files=no")
assert git(BASE, "rev-parse", "HEAD") == PIN
receipt["base_tracked_files_unchanged_before_and_after"] = True
(OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
