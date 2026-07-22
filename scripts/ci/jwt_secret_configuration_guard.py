#!/usr/bin/env python3
"""Fail closed on tracked/release-bundled secrets and unsafe JWT configuration."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf", ".pyc", ".woff", ".woff2"}
SECRET_FILENAMES = {".env", ".env.production", ".env.staging", ".env.local"}
SECRET_NAMES = {
    "JWT_SECRET",
    "SAHOOL_JWT_SECRET",
    "JWT_PRIVATE_KEY",
    "TELEGRAM_BOT_TOKEN",
    "CDSE_CLIENT_SECRET",
    "SH_CLIENT_SECRET",
    "SAHOOL_AGENT_TOKEN",
    "SMTP_PASSWORD",
    "DATABASE_PASSWORD",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "GRAFANA_PASSWORD",
}
SAFE_PREFIXES = ("$", "${", "<", "secret://", "vault://", "file://")
PLACEHOLDER_WORDS = (
    "changeme",
    "change_me",
    "change-me",
    "placeholder",
    "replace_me",
    "replace-me",
    "your_",
)


def candidate_files() -> list[Path]:
    git = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True)
    if git.returncode == 0 and git.stdout:
        return [ROOT / p.decode() for p in git.stdout.split(b"\0") if p]
    return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]


def unsafe_assignment(line: str) -> str | None:
    m = re.match(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
    if not m or m.group(1) not in SECRET_NAMES:
        return None
    raw_value = m.group(2).strip()
    if any(token in raw_value for token in ("os.getenv(", "env(", " if ", " else ", "||", "&&")):
        return None
    value = raw_value.strip("'\"")
    if not value or value.startswith(SAFE_PREFIXES) or value.startswith("$("):
        return None
    lower = value.lower()
    if any(word in lower for word in PLACEHOLDER_WORDS):
        return f"placeholder {m.group(1)}"
    if len(value) >= 8:
        return f"literal {m.group(1)}"
    return None


files = candidate_files()
assert files, "secret guard found no files to scan"
for path in files:
    rel = path.relative_to(ROOT)
    assert path.name not in SECRET_FILENAMES, f"secret file bundled/tracked: {rel}"
    if path.suffix.lower() in BINARY_SUFFIXES or path.stat().st_size > 5_000_000:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    exempt_example = (
        any(part.startswith("test") for part in rel.parts)
        or "fixtures" in rel.parts
        or rel.suffix in {".md", ".example"}
    )
    if not exempt_example:
        assignment_surface = (
            path.suffix.lower() in {".sh", ".ps1", ".env", ".yaml", ".yml", ".toml"}
            or "compose" in path.name.lower()
        )
        if assignment_surface:
            for line in text.splitlines():
                issue = unsafe_assignment(line)
                if issue:
                    raise AssertionError(f"{issue} in {rel}")
        if re.search(r"-----BEGIN (?:RSA )?PRIVATE KEY-----", text):
            raise AssertionError(f"embedded private key in {rel}")
        if re.search(
            r"(?im)^\s*JWT_PUBLIC_KEY\s*=\s*['\"]?(?:aasd\w*|placeholder|changeme|replace[_-]?me)",
            text,
        ):
            raise AssertionError(f"JWT placeholder in {rel}")
print(f"JWT and secret configuration guard: PASS ({len(files)} files scanned)")
