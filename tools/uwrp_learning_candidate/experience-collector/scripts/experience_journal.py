#!/usr/bin/env python3
"""Small offline, append-only experience journal. Python standard library only.

No network, Git actions, self-modification, or execution of content from observations.
The local mkdir lock is NOT a distributed lock. Do not break it just because it is old.

Fixed candidate of the v4.3 script (gap UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01): the
credential scan runs on every raw field value, not on the serialized JSON text whose
escaping (``\\n``, ``\\"``) hid secrets, and it covers prefixed names such as
``OPENAI_API_KEY=`` / ``DB_PASSWORD=``, PEM private keys, Slack and Google API tokens,
and ``scheme://user:pass@`` URLs for any scheme. The command-line interface is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "uwrp.experience.v1"
JOURNAL_SCHEMA = "uwrp.experience-event.v1"
MAX_INPUT_BYTES = 4096
MAX_JOURNAL_BYTES = 2_000_000
SHA = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,95}$")
REF = re.compile(r"^(?:receipt|artifact|case|hash):[A-Za-z0-9_.:/-]{2,150}$")
_SECRET_VALUE = r"""\s*[:=]\s*["']?[^\s"',;}]{4,}"""
SECRET_PATTERNS = [
    # Assignment to a credential-named key. No leading \b: in OPENAI_API_KEY or
    # DB_PASSWORD the name is preceded by "_", a word character, so \b never matched.
    re.compile(
        r"(?i)(?:api[_-]?key|password|passwd|passphrase|client[_-]?secret|secret[_-]?key"
        r"|private[_-]?key|access[_-]?key|(?:access|auth|refresh|bot|api)[_-]?token)"
        + _SECRET_VALUE
    ),
    # Environment-variable style names: GITHUB_TOKEN=, AWS_SECRET_ACCESS_KEY=, STRIPE_KEY=.
    re.compile(
        r"\b[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|_KEY|APIKEY)[A-Z0-9_]*" + _SECRET_VALUE
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{10,}"),
    # Provider token prefixes, anchored so "_" or ":" before them (IDs, refs) still match.
    re.compile(
        r"(?<![A-Za-z0-9])(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|glpat-|AKIA)[A-Za-z0-9_-]{8,}"
    ),
    re.compile(r"(?<![A-Za-z0-9])xox[abposre]-[A-Za-z0-9-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY"),
    # Credentials in a URL of any scheme (postgresql://, redis://, amqp://, https://, ...).
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@"),
]
KINDS = {"code", "research", "document", "creative", "operations", "mixed", "other"}
SIGNALS = {
    "false_trigger",
    "missing_evidence",
    "duplicate_effect",
    "latency",
    "resource_exhaustion",
    "stale_state",
    "unsafe_action",
    "regression",
    "recovery",
    "accuracy",
    "usability",
    "other",
}
OUTCOMES = {"success", "failure", "partial", "blocked"}
KEYS = {
    "schema",
    "observation_id",
    "skill_name",
    "skill_digest",
    "task_kind",
    "signal",
    "outcome",
    "summary",
    "evidence_ref",
    "evidence_digest",
}


class JournalError(ValueError):
    pass


def canon(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def validate_observation(o: object) -> dict:
    if not isinstance(o, dict) or set(o) != KEYS or o.get("schema") != SCHEMA:
        raise JournalError("observation requires exactly the v1 schema fields")
    if not isinstance(o["observation_id"], str) or not IDENT.fullmatch(o["observation_id"]):
        raise JournalError("invalid observation ID")
    if not isinstance(o["skill_name"], str) or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", o["skill_name"]
    ):
        raise JournalError("invalid skill name")
    for k in ["skill_digest", "evidence_digest"]:
        if not isinstance(o[k], str) or not SHA.fullmatch(o[k]):
            raise JournalError(f"{k}: expected lowercase SHA-256")
    if o["task_kind"] not in KINDS or o["signal"] not in SIGNALS or o["outcome"] not in OUTCOMES:
        raise JournalError("unknown task kind, signal or outcome")
    if not isinstance(o["summary"], str) or not 12 <= len(o["summary"]) <= 300:
        raise JournalError("summary must be 12–300 characters")
    if not isinstance(o["evidence_ref"], str) or not REF.fullmatch(o["evidence_ref"]):
        raise JournalError("evidence_ref must be an opaque receipt/artifact/case/hash reference")
    if len(canon(o)) > MAX_INPUT_BYTES:
        raise JournalError("observation too large")
    # A denylist is defense-in-depth, NOT proof of complete redaction.
    # Scan each raw value: JSON escaping turns a newline into "\\n" and a quote into
    # '\\"', which defeated the patterns when they ran over json.dumps(o).
    for text in _strings(o):
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise JournalError("possible secret/credential: redact before recording")
    return o


def _strings(value: object):
    """Every string in ``value``: dict keys, dict values and list items, recursively."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise JournalError("journal symlink refused")
    raw = path.read_bytes()
    if len(raw) > MAX_JOURNAL_BYTES:
        raise JournalError("journal size exceeds retention cap; archive through approved policy")
    if raw and not raw.endswith(b"\n"):
        raise JournalError("incomplete journal line; no automatic repair")
    events, previous, ids = [], "0" * 64, {}
    for line_no, raw_line in enumerate(raw.splitlines(), 1):
        try:
            e = json.loads(raw_line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as ex:
            raise JournalError(f"journal line {line_no}: invalid JSON") from ex
        if not isinstance(e, dict) or set(e) != {
            "schema",
            "seq",
            "recorded_at",
            "previous_hash",
            "observation",
            "verification",
            "event_hash",
        }:
            raise JournalError(f"journal line {line_no}: unexpected event fields")
        if e["schema"] != JOURNAL_SCHEMA or type(e["seq"]) is not int or e["seq"] != line_no:
            raise JournalError(f"journal line {line_no}: invalid sequence/schema")
        if e["previous_hash"] != previous:
            raise JournalError(f"journal line {line_no}: broken chain")
        if e["verification"] != "RECORDED_UNVERIFIED":
            raise JournalError(f"journal line {line_no}: unauthorized verification claim")
        validate_observation(e["observation"])
        actual = digest({k: v for k, v in e.items() if k != "event_hash"})
        if e["event_hash"] != actual:
            raise JournalError(f"journal line {line_no}: hash mismatch")
        obs_id = e["observation"]["observation_id"]
        if obs_id in ids:
            raise JournalError(f"journal line {line_no}: duplicate observation ID")
        ids[obs_id] = actual
        previous = actual
        events.append(e)
    return events


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".checkpoint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canon(data) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def record(journal: Path, observation: dict) -> dict:
    validate_observation(observation)
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.is_symlink():
        raise JournalError("journal symlink refused")
    lock = journal.with_name(journal.name + ".lock")
    # Atomic only on a shared filesystem with atomic mkdir; never a distributed lease.
    lock.mkdir(exist_ok=False)
    try:
        events = read_events(journal)
        for e in events:
            if e["observation"]["observation_id"] == observation["observation_id"]:
                if e["observation"] == observation:
                    return {
                        "status": "ALREADY_RECORDED",
                        "seq": e["seq"],
                        "event_hash": e["event_hash"],
                    }
                raise JournalError("observation ID conflict (different content)")
        prev = events[-1]["event_hash"] if events else "0" * 64
        entry = {
            "schema": JOURNAL_SCHEMA,
            "seq": len(events) + 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "previous_hash": prev,
            "observation": observation,
            "verification": "RECORDED_UNVERIFIED",
        }
        entry["event_hash"] = digest(entry)
        line = canon(entry) + b"\n"
        size = journal.stat().st_size if journal.exists() else 0
        if size + len(line) > MAX_JOURNAL_BYTES:
            raise JournalError("journal retention cap; rotate with approved custody process")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(journal, flags, 0o600)
        try:
            with os.fdopen(fd, "ab") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            raise
        snapshot = {
            "schema": "uwrp.experience-checkpoint.v1",
            "entries": len(events) + 1,
            "journal_hash": entry["event_hash"],
            "latest_observation_id": observation["observation_id"],
            "trust": "RECORDED_UNVERIFIED",
            "durable_backup": False,
        }
        atomic_json(journal.with_name(journal.name + ".checkpoint.json"), snapshot)
        return {
            "status": "RECORDED_UNVERIFIED",
            "seq": entry["seq"],
            "event_hash": entry["event_hash"],
        }
    finally:
        lock.rmdir()  # owned by this invocation only; never remove someone else's stale lock


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    add = sub.add_parser("record")
    add.add_argument("--input", type=Path, required=True)
    add.add_argument("--journal", type=Path, required=True)
    for c in ["verify", "summary"]:
        parser = sub.add_parser(c)
        parser.add_argument("--journal", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.command == "record":
            obs = json.loads(a.input.read_text(encoding="utf-8"))
            result = record(a.journal, obs)
        else:
            events = read_events(a.journal)
            result = {
                "status": "CHAIN_VALIDATED" if a.command == "verify" else "RECORDED_ONLY",
                "count": len(events),
                "tip": events[-1]["event_hash"] if events else "0" * 64,
                "verification": "STRUCTURAL_ONLY_NOT_FACT_VERIFICATION",
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as ex:
        print(f"REFUSED: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
