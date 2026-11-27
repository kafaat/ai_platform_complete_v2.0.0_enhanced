"""Bounded actual-Git controls for the inspection clone's CSV whitespace policy."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", type=Path, default=Path(__file__).with_name("build_candidate.py"))
    parser.add_argument("--repository-policy", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("inspection_csv_policy_builder", args.builder)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reference_base = module.CONFIG["main"]
    policy = (args.repository_policy.read_bytes() if args.repository_policy else
              subprocess.check_output(["git", "-C", str(module.WORK), "show",
                                       f"{reference_base}:.gitattributes"]))
    report = {
        "schema": "sahool.inspection-csv-whitespace-controls.v1",
        "status": "RUNNING", "scope": "Synthetic Git fixtures only; no source generation or full preflight.",
        "builder_sha256": hashlib.sha256(args.builder.read_bytes()).hexdigest(),
        "repository_policy_commit": reference_base,
        "repository_policy_sha256": hashlib.sha256(policy).hexdigest(),
        "cases": [], "production_accepted": False,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="inspection-csv-policy-controls-") as folder:
            area = Path(folder)
            source = area / "source"
            source.mkdir()
            env = dict(os.environ)
            for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR"):
                env.pop(key, None)

            def git(*cmd, data=None):
                return subprocess.check_output(["git", *cmd], cwd=source, env=env, input=data)

            git("init", "-q")
            git("config", "user.name", "Synthetic inspection CSV control")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "core.autocrlf", "false")
            (source / ".gitattributes").write_bytes(policy)
            (source / "seed.txt").write_bytes(b"baseline\n")
            git("add", ".gitattributes", "seed.txt")
            git("commit", "-qm", "Synthetic policy fixture")
            base = git("rev-parse", "HEAD").decode().strip()
            module.SOURCE = source
            module.OUT = area / "evidence"
            module.CONFIG = {**module.CONFIG, "main": base}
            # git/gt default arguments bind at definition, so point only those defaults
            # at this owned fixture; the production script remains byte-for-byte intact.
            module.git.__kwdefaults__["cwd"] = source
            module.gt.__kwdefaults__["cwd"] = source
            module.configure_csv_whitespace_policy()
            policy_receipt = json.loads((module.OUT / "whitespace-policy.json").read_text())
            cases = [
                ("legal_crlf_csv", "nested/fixture.csv", b"a,b\r\n1,2\r\n", 0),
                ("space_before_crlf_csv", "nested/fixture.csv", b"a,b \r\n", 2),
                ("tab_before_crlf_csv", "nested/fixture.csv", b"a,b\t\r\n", 2),
                ("blank_eof_csv", "nested/fixture.csv", b"a,b\r\n\r\n", 2),
                ("space_before_tab_csv", "nested/fixture.csv", b" \tvalue\r\n", 2),
                ("non_csv_trailing_space", "fixture.py", b"value = 1 \n", 2),
                ("non_csv_crlf", "fixture.py", b"value = 1\r\n", 2),
            ]
            for label, path, data, expected in cases:
                git("read-tree", base)
                oid = git("hash-object", "-w", "--stdin", data=data).decode().strip()
                git("update-index", "--add", "--cacheinfo", "100644", oid, path)
                result = subprocess.run(["git", "diff", "--cached", "--check"],
                                        cwd=source, env=env, capture_output=True)
                report["cases"].append({
                    "name": label, "path": path, "expected_returncode": expected,
                    "actual_returncode": result.returncode,
                    "stdout": result.stdout.decode(errors="replace"),
                    "stderr": result.stderr.decode(errors="replace"),
                })
                require(result.returncode == expected, f"Whitespace control failed: {label}")
            captured = io.StringIO()
            observed = None
            with redirect_stderr(captured):
                try:
                    module.git("diff", "--cached", "--check", cwd=source)
                except subprocess.CalledProcessError as exc:
                    observed = exc.returncode
            require(observed == 2 and "trailing whitespace" in captured.getvalue(),
                    "Git helper lost captured stdout or swallowed the native failure")
            require((source / ".gitattributes").read_bytes() == policy,
                    "The checker modified repository attributes")
            require(git("show", f"{base}:.gitattributes") == policy, "Committed policy changed")
            require(git("rev-parse", "HEAD").decode().strip() == base, "Fixture HEAD changed")
            report.update(
                status="PASS", expected_rejections_verified=6, legal_crlf_cases_passed=1,
                failed_git_stdout_forwarded=True, failed_git_returncode_preserved=True,
                source_attributes_unchanged=True, non_csv_crlf_rejected=True,
                private_attributes_rule=policy_receipt["applied_rule"],
            )
    except BaseException as exc:
        report.update(status="FAIL", exception_type=type(exc).__name__, message=str(exc))
        raise
    finally:
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(output)
        print(output, end="")


if __name__ == "__main__":
    main()
