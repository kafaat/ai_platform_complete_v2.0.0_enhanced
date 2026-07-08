from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_OWNERSHIP = ROOT / "docs" / "architecture" / "db_ownership.yml"


def _parse_db_ownership(text: str):
    tables = {}
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        table_match = re.match(r"^  ([A-Za-z_][\w]*):\s*$", line)
        if table_match:
            current = table_match.group(1)
            tables[current] = {}
            continue
        field_match = re.match(r"^    (owner|writers|readers):\s*(.*?)\s*$", line)
        if current and field_match:
            key, value = field_match.groups()
            tables[current][key] = value
    return tables


def test_db_ownership_file_exists_and_assigns_single_writer_owner():
    assert DB_OWNERSHIP.exists(), (
        "docs/architecture/db_ownership.yml is required before service extraction."
    )
    tables = _parse_db_ownership(DB_OWNERSHIP.read_text(encoding="utf-8"))
    assert tables, "db_ownership.yml must contain at least one table ownership entry."
    bad = []
    for table, meta in tables.items():
        owner = meta.get("owner", "").strip()
        writers = meta.get("writers", "").strip()
        if not owner or not writers:
            bad.append((table, "missing owner/writers"))
        elif writers != f"[{owner}]":
            bad.append(
                (table, f"writers must be exactly the owner: owner={owner}, writers={writers}")
            )
    assert not bad, repr(bad[:20])


def test_db_ownership_covers_all_create_table_migrations():
    known = set(_parse_db_ownership(DB_OWNERSHIP.read_text(encoding="utf-8")))
    create_re = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w]*)", re.I)
    op_re = re.compile(r"op\.create_table\(\s*[\"']([A-Za-z_][\w]*)[\"']")
    discovered = set()
    for directory in [
        ROOT / "migrations",
        ROOT / "alembic" / "versions",
        ROOT / "services" / "sahool-platform" / "storage",
    ]:
        if not directory.exists():
            continue
        for path in directory.rglob("*.sql"):
            discovered.update(create_re.findall(path.read_text(encoding="utf-8", errors="ignore")))
        for path in directory.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            discovered.update(create_re.findall(text))
            discovered.update(op_re.findall(text))
    missing = sorted(discovered - known)
    assert not missing, "Tables missing from docs/architecture/db_ownership.yml: " + repr(
        missing[:20]
    )
