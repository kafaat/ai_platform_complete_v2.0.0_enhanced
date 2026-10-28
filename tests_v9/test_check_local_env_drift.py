"""scripts/check_local_env_drift.py names missing keys, flags startup blockers, never prints values."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_local_env_drift", ROOT / "scripts" / "check_local_env_drift.py"
)
drift = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = drift
_spec.loader.exec_module(drift)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_old_env_without_the_s3_opt_in_is_flagged_as_startup_blocking(tmp_path, capsys):
    example = _write(
        tmp_path,
        ".env.example",
        "# comment\nS3_ENDPOINT=http://sahool-minio:9000\nS3_ALLOW_PLAINTEXT_INTERNAL=true\n",
    )
    env = _write(tmp_path, ".env", "S3_ENDPOINT=http://sahool-minio:9000\n")
    rc = drift.main(["--env", str(env), "--example", str(example)])
    out = capsys.readouterr().out
    assert rc == 0  # advisory by default
    assert "MISSING S3_ALLOW_PLAINTEXT_INTERNAL" in out


def test_strict_mode_fails_on_a_missing_key(tmp_path):
    example = _write(tmp_path, ".env.example", "A=1\nB=2\n")
    env = _write(tmp_path, ".env", "A=1\n")
    assert drift.main(["--env", str(env), "--example", str(example), "--strict"]) == 1


def test_values_are_never_printed(tmp_path, capsys):
    example = _write(tmp_path, ".env.example", "JWT_SECRET=example-secret-value\nNEW_KEY=x\n")
    env = _write(tmp_path, ".env", "export JWT_SECRET=super-secret-local-value\n")
    drift.main(["--env", str(env), "--example", str(example)])
    out = capsys.readouterr().out
    assert "NEW_KEY" in out
    assert "secret-value" not in out and "secret-local" not in out


def test_commented_and_exported_keys(tmp_path):
    env = _write(tmp_path, ".env", "# S3_ALLOW_PLAINTEXT_INTERNAL=true\nexport A = 1\nA=2\n")
    assert drift.env_keys(env) == ["A"]


def test_complete_env_reports_no_drift(tmp_path, capsys):
    example = _write(tmp_path, ".env.example", "A=1\n")
    env = _write(tmp_path, ".env", "A=other\nEXTRA=1\n")
    assert drift.main(["--env", str(env), "--example", str(example), "--strict"]) == 0
    assert "has every key" in capsys.readouterr().out


def test_missing_files_skip_quietly(tmp_path, capsys):
    rc = drift.main(["--env", str(tmp_path / "nope"), "--example", str(tmp_path / "nada")])
    assert rc == 0 and "skipped" in capsys.readouterr().out


def test_repo_example_still_carries_the_startup_blocking_keys():
    # If .env.example drops one of these, the blocker list is describing nothing.
    keys = set(drift.env_keys(ROOT / ".env.example"))
    assert set(drift.STARTUP_BLOCKING) <= keys
