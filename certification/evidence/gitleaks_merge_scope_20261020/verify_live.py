"""Reproduce PR merge omissions using the pinned scanner and disposable Git repos."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def prove(binary: str, mode: str) -> dict:
    with tempfile.TemporaryDirectory() as directory:
        repo = Path(directory)

        def git(*args):
            return subprocess.check_output(
                ["git", *args], cwd=repo, text=True, encoding="utf-8", stderr=subprocess.DEVNULL
            ).strip()

        def commit(path, text):
            (repo / path).write_text(text, encoding="utf-8")
            git("add", path)
            git("commit", "-qm", "synthetic fixture")

        git("init", "-q", "-b", "main")
        git("config", "user.name", "Fixture")
        git("config", "user.email", "fixture@example.invalid")
        commit("readme", "clean base\n")
        base = git("rev-parse", "HEAD")
        git("checkout", "-qb", "side")
        # A scanner witness, never an issued credential; do not print its value.
        token = "ghp_" + "aB3dE7gH9jK2mN5pQ8sT1vW4yZ6cD0fG3iL7oP9r"
        payload = "access_token = '" + token + "'\n"
        commit("side.txt", payload if mode in {"second_parent", "removed_later"} else "clean\n")
        git("checkout", "-qb", "pr", base)
        commit("topic.txt", "clean topic\n")
        git("merge", "--no-ff", "--no-commit", "side")
        if mode == "merge_resolution":
            (repo / "merge.txt").write_text(payload, encoding="utf-8")
            git("add", "merge.txt")
        git("commit", "-qm", "merge")
        if mode == "removed_later":
            commit("side.txt", "removed\n")
        head = git("rev-parse", "HEAD")
        results = {}
        for label, options in (
            ("pinned_action", "--no-merges --first-parent"),
            ("supplemental", "--full-history --diff-merges=first-parent"),
        ):
            report = repo / (label + ".json")
            process = subprocess.run(
                [
                    binary,
                    "git",
                    "--redact",
                    "--exit-code=2",
                    "--no-banner",
                    "--report-format=json",
                    "--report-path=" + str(report),
                    "--log-opts=" + options + " " + base + ".." + head,
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            findings = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
            results[label] = {
                "exit_code": process.returncode,
                "findings": len(findings),
                "rules": sorted({finding["RuleID"] for finding in findings}),
            }
        assert results["pinned_action"]["exit_code"] == 0, results
        assert results["supplemental"]["exit_code"] == (0 if mode == "clean" else 2), results
        return {"case": mode, **results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gitleaks", required=True)
    args = parser.parse_args()
    binary = str(Path(args.gitleaks).resolve())
    version = subprocess.check_output([binary, "version"], text=True, encoding="utf-8").strip()
    assert version == "8.30.1", version
    print(
        json.dumps(
            {
                "scanner": version,
                "cases": [
                    prove(binary, mode)
                    for mode in ("second_parent", "merge_resolution", "removed_later", "clean")
                ],
                "scope": "disposable Git fixtures with synthetic credentials; no production access",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
