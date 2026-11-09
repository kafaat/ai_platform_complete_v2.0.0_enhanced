#!/usr/bin/env python3
"""Owner-signature verifier for GATE-01 authorizations (library + CLI).

Gap: ``GATE01-AUTHORIZATION-ORIGIN-UNENFORCED-01``. Every PR the agent opens is
authored by the owner's GitHub account, so neither the PR author nor an approval from
that account can tell the owner apart from the agent, and a field such as
``approved_by: owner`` or ``ruling_source`` is just text the agent can write. This
module makes an authorization *provable*: it must carry a signature made with a key
the agent does not hold, checked against a trust root read from the **base** branch.

Format (DSSE-shaped, OpenSSH transport)
---------------------------------------
No DSSE/Ed25519 verifier exists in this repository, and the GATE-01 job installs no
Python packages, so the signature transport is ``ssh-keygen -Y sign/verify`` (OpenSSH,
present on GitHub ubuntu runners). What is signed is the DSSE pre-authentication
encoding ``PAE(payloadType, payload)``; the committed file is a DSSE envelope::

    {"payloadType": PAYLOAD_TYPE,
     "payload": base64(canonical JSON),
     "signatures": [{"keyid": <signer>, "sig": base64(<armored SSHSIG over PAE>)}]}

No cryptography is implemented here: parsing, canonical bytes and comparisons only.

Verdicts
--------
``VERIFIED``   signature, trust root, identity, subject, validity and ledger all hold.
``UNVERIFIED`` it could not be checked (no trusted key configured, ssh-keygen absent,
               CI context missing). Never treated as authorization.
``INVALID``    it was checked and something does not hold.

Honesty limit: this proves the *origin* of a decision (the holder of the owner key
signed these exact bytes). It is not an independent review, and the very first
installation of the trust root still relies on the owner checking the key fingerprint
in the PR that adds it (after that, rotation needs a signature by the trusted key).
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]

SCHEMA = "sahool.gate01_owner_authorization/v1"
PAYLOAD_TYPE = "application/vnd.sahool.gate01-authorization+json;version=1"
NAMESPACE_DEFAULT = "sahool-gate01-authorization-v1"
LEDGER_SCHEMA = "sahool.gate01_consumed_authorizations/v1"
REVOCATION_SCHEMA = "sahool.gate01_revoked_authorizations/v1"

POLICY_PATH = "docs/architecture/gate01_policy.json"
DEFAULT_CONFIG = {
    "required_for": ["state_transition"],
    "required_for_bounded": False,
    "namespace": NAMESPACE_DEFAULT,
    "allowed_signers_path": "docs/architecture/gates/owner_allowed_signers",
    "authorizations_dir": "docs/architecture/gates/authorizations",
    "consumed_ledger_path": "docs/architecture/gates/consumed_authorizations.json",
    "revocations_path": "docs/architecture/gates/revoked_authorizations.json",
    "max_validity_days": 14,
}
#: Config keys whose change is a weakening unless it only strengthens (see below).
_CONFIG_IDENTITY_KEYS = (
    "namespace",
    "allowed_signers_path",
    "authorizations_dir",
    "consumed_ledger_path",
    "revocations_path",
)

ACTIONS = ("state_transition", "bounded_change", "policy_change", "trust_root_change")
CHANGE_TYPES = ("add", "modify", "delete", "rename")
SIGNER_ROLE = "owner"
ENVELOPE_SUFFIX = ".dsse.json"
ALLOWED_KEY_TYPES = ("ssh-ed25519", "sk-ssh-ed25519@openssh.com")
CLOCK_SKEW = timedelta(minutes=5)

VERIFIED, UNVERIFIED, INVALID = "VERIFIED", "UNVERIFIED", "INVALID"
NOT_CONFIGURED = "owner signing key not configured"

_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DECISION_ID = re.compile(r"^GATE01-AUTH-\d{4}-\d{2}-\d{2}-\d{3}$")
_NONCE = re.compile(r"^[0-9a-f]{32,128}$")
_ZERO_DIGEST = re.compile(r"^(sha256:)?0{64}$")


class AuthorizationError(ValueError):
    """A document that cannot be read as an authorization at all."""


# ── canonical bytes ─────────────────────────────────────────────────────────────
def canonical_json(obj) -> bytes:
    """The only accepted serialization: sorted keys, no spaces, ASCII, trailing LF."""
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("ascii")


def pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE v1 pre-authentication encoding (the exact bytes the owner signs)."""
    t = payload_type.encode("utf-8")
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(payload), payload)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise AuthorizationError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def strict_loads(raw: bytes):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)


def subject_digest(payload: dict) -> str:
    """What a ledger entry is bound to: the signed identity + subject."""
    return sha256_hex(
        canonical_json({"identity": payload.get("identity"), "subject": payload.get("subject")})
    )


def parse_time(value) -> datetime | None:
    """``YYYY-MM-DDTHH:MM:SSZ`` only — an unparseable instant is not a bound."""
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def format_time(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── trust root ──────────────────────────────────────────────────────────────────
def parse_allowed_signers(text: str | None) -> dict[str, list[str]]:
    """Map principal -> key lines. Empty ⇒ not configured.

    Raises :class:`AuthorizationError` on any malformed or non-Ed25519 line, and on
    ``cert-authority`` (a CA line would trust every certificate it signs).
    """
    out: dict[str, list[str]] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as exc:
            raise AuthorizationError(f"allowed_signers: unparsable line ({exc})") from exc
        idx = next((i for i, tok in enumerate(tokens) if tok in ALLOWED_KEY_TYPES), None)
        if idx is None or idx < 1 or idx + 1 >= len(tokens):
            raise AuthorizationError("allowed_signers: line without an Ed25519 public key")
        options = " ".join(tokens[1:idx]).lower()
        if "cert-authority" in options:
            raise AuthorizationError("allowed_signers: cert-authority lines are not accepted")
        try:
            base64.b64decode(tokens[idx + 1], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise AuthorizationError("allowed_signers: public key is not base64") from exc
        for principal in tokens[0].split(","):
            if principal:
                out.setdefault(principal, []).append(line)
    return out


def ssh_keygen_available() -> bool:
    return shutil.which("ssh-keygen") is not None


def ssh_verify(
    message: bytes, armored_sig: bytes, allowed_signers: str, principal: str, namespace: str
):
    """``ssh-keygen -Y verify``. Returns ``(ok, detail)``; never raises on a bad signature."""
    with tempfile.TemporaryDirectory(prefix="g01sig-") as tmp:
        signers = Path(tmp) / "allowed_signers"
        sig = Path(tmp) / "message.sig"
        signers.write_text(allowed_signers, encoding="utf-8")
        sig.write_bytes(armored_sig)
        proc = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(signers),
                "-I",
                principal,
                "-n",
                namespace,
                "-s",
                str(sig),
            ],
            input=message,
            capture_output=True,
            check=False,
            timeout=30,
        )
    detail = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
    return proc.returncode == 0, detail


# ── git helpers ─────────────────────────────────────────────────────────────────
def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise AuthorizationError(
            f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc


def rev_parse(root: Path, ref: str) -> str | None:
    proc = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    out = proc.stdout.decode().strip()
    return out if proc.returncode == 0 and _SHA1.match(out) else None


def tree_of(root: Path, commit: str) -> str | None:
    proc = _git(root, "rev-parse", "--verify", "--quiet", f"{commit}^{{tree}}", check=False)
    out = proc.stdout.decode().strip()
    return out if proc.returncode == 0 else None


def merge_base(root: Path, a: str, b: str) -> str | None:
    proc = _git(root, "merge-base", a, b, check=False)
    out = proc.stdout.decode().strip()
    return out if proc.returncode == 0 and _SHA1.match(out) else None


def is_ancestor(root: Path, a: str, b: str) -> bool:
    return _git(root, "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def show_bytes(root: Path, commit: str, path: str) -> bytes | None:
    proc = _git(root, "show", f"{commit}:{path}", check=False)
    return proc.stdout if proc.returncode == 0 else None


def changed_paths(root: Path, a: str, b: str) -> list[str]:
    proc = _git(root, "diff", "--no-renames", "--name-only", "-z", a, b)
    return sorted(p for p in proc.stdout.decode("utf-8").split("\0") if p)


def derive_scope(root: Path, base: str, head: str) -> list[dict]:
    """The exact change set ``base..head`` with before/after sha256 of the bytes."""
    proc = _git(root, "diff", "--no-ext-diff", "--name-status", "-M", "-z", base, head)
    fields = [f for f in proc.stdout.decode("utf-8").split("\0")]
    scope: list[dict] = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        kind = status[0]
        if kind == "R":
            src, dst = fields[i + 1], fields[i + 2]
            i += 3
            before, after = show_bytes(root, base, src), show_bytes(root, head, dst)
            scope.append(
                {
                    "path": dst,
                    "from_path": src,
                    "change": "rename",
                    "before_sha256": sha256_hex(before) if before is not None else None,
                    "after_sha256": sha256_hex(after) if after is not None else None,
                }
            )
            continue
        path = fields[i + 1]
        i += 2
        change = {"A": "add", "D": "delete"}.get(kind, "modify")
        before = None if change == "add" else show_bytes(root, base, path)
        after = None if change == "delete" else show_bytes(root, head, path)
        scope.append(
            {
                "path": path,
                "change": change,
                "before_sha256": sha256_hex(before) if before is not None else None,
                "after_sha256": sha256_hex(after) if after is not None else None,
            }
        )
    return sorted(scope, key=lambda e: e["path"])


# ── envelope + payload ──────────────────────────────────────────────────────────
def build_envelope(payload_bytes: bytes, armored_sig: bytes, keyid: str) -> bytes:
    return canonical_json(
        {
            "payloadType": PAYLOAD_TYPE,
            "payload": base64.b64encode(payload_bytes).decode("ascii"),
            "signatures": [{"keyid": keyid, "sig": base64.b64encode(armored_sig).decode("ascii")}],
        }
    )


def parse_envelope(raw: bytes) -> tuple[bytes, dict, bytes, str]:
    """``(payload_bytes, payload, armored_sig, keyid)`` or :class:`AuthorizationError`."""
    try:
        env = strict_loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"envelope is not JSON ({exc})") from exc
    if not isinstance(env, dict) or set(env) != {"payloadType", "payload", "signatures"}:
        raise AuthorizationError("envelope must have exactly payloadType, payload, signatures")
    if env["payloadType"] != PAYLOAD_TYPE:
        raise AuthorizationError(f"payloadType {env['payloadType']!r} is not {PAYLOAD_TYPE!r}")
    sigs = env["signatures"]
    if not isinstance(sigs, list) or len(sigs) != 1 or not isinstance(sigs[0], dict):
        raise AuthorizationError("envelope must carry exactly one signature")
    if set(sigs[0]) != {"keyid", "sig"}:
        raise AuthorizationError("signature entry must have exactly keyid and sig")
    try:
        payload_bytes = base64.b64decode(env["payload"], validate=True)
        armored = base64.b64decode(sigs[0]["sig"], validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise AuthorizationError("payload or sig is not base64") from exc
    try:
        payload = strict_loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorizationError(f"payload is not JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise AuthorizationError("payload is not an object")
    if canonical_json(payload) != payload_bytes:
        raise AuthorizationError("payload bytes are not canonical JSON")
    return payload_bytes, payload, armored, str(sigs[0]["keyid"])


def _exact_keys(obj, keys: set[str], where: str) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{where}: not an object"]
    missing, extra = sorted(keys - set(obj)), sorted(set(obj) - keys)
    out = []
    if missing:
        out.append(f"{where}: missing field(s) {missing}")
    if extra:
        out.append(f"{where}: unknown field(s) {extra}")
    return out


def payload_schema_errors(p: dict) -> list[str]:
    """Strict shape: every field present, nothing unknown, every value well-formed."""
    errs = _exact_keys(
        p,
        {
            "schema",
            "decision_id",
            "action",
            "identity",
            "subject",
            "evidence",
            "validity",
            "use",
            "nonce",
        },
        "payload",
    )
    if errs:
        return errs
    if p["schema"] != SCHEMA:
        errs.append(f"schema {p['schema']!r} is not {SCHEMA!r}")
    if not isinstance(p["decision_id"], str) or not _DECISION_ID.match(p["decision_id"]):
        errs.append("decision_id must look like GATE01-AUTH-YYYY-MM-DD-NNN")
    if p["action"] not in ACTIONS:
        errs.append(f"action {p['action']!r} not in {list(ACTIONS)}")
    if not isinstance(p["nonce"], str) or not _NONCE.match(p["nonce"]):
        errs.append("nonce must be 32..128 lowercase hex characters")

    ident = p["identity"]
    e = _exact_keys(
        ident, {"repository", "repository_id", "pr_number", "signer", "signer_role"}, "identity"
    )
    errs += e
    if not e:
        if not isinstance(ident["repository"], str) or "/" not in ident["repository"]:
            errs.append("identity.repository must be owner/name")
        for key in ("repository_id", "pr_number"):
            if not isinstance(ident[key], int) or isinstance(ident[key], bool) or ident[key] <= 0:
                errs.append(f"identity.{key} must be a positive integer")
        if not isinstance(ident["signer"], str) or not ident["signer"]:
            errs.append("identity.signer must be a non-empty principal")
        if ident["signer_role"] != SIGNER_ROLE:
            errs.append(f"identity.signer_role must be {SIGNER_ROLE!r}")

    subj = p["subject"]
    e = _exact_keys(subj, {"base_sha", "head_sha", "tree_sha", "scope"}, "subject")
    errs += e
    if not e:
        for key in ("base_sha", "head_sha", "tree_sha"):
            if not isinstance(subj[key], str) or not _SHA1.match(subj[key]):
                errs.append(f"subject.{key} must be a 40-hex object id")
        scope = subj["scope"]
        if not isinstance(scope, list) or not scope:
            errs.append("subject.scope must be a non-empty list")
        else:
            for n, entry in enumerate(scope):
                want = {"path", "change", "before_sha256", "after_sha256"}
                if isinstance(entry, dict) and entry.get("change") == "rename":
                    want = want | {"from_path"}
                ee = _exact_keys(entry, want, f"subject.scope[{n}]")
                errs += ee
                if ee:
                    continue
                if entry["change"] not in CHANGE_TYPES:
                    errs.append(
                        f"subject.scope[{n}].change {entry['change']!r} not in {list(CHANGE_TYPES)}"
                    )
                for key in ("before_sha256", "after_sha256"):
                    v = entry[key]
                    if v is not None and (not isinstance(v, str) or not _SHA256.match(v)):
                        errs.append(f"subject.scope[{n}].{key} must be 64-hex or null")
                if entry["change"] == "add" and entry["before_sha256"] is not None:
                    errs.append(f"subject.scope[{n}]: add with a before digest")
                if entry["change"] == "delete" and entry["after_sha256"] is not None:
                    errs.append(f"subject.scope[{n}]: delete with an after digest")

    ev = p["evidence"]
    e = _exact_keys(ev, {"manifest_path", "manifest_sha256"}, "evidence")
    errs += e
    if not e:
        if not isinstance(ev["manifest_path"], str) or not ev["manifest_path"]:
            errs.append("evidence.manifest_path must be a repository path")
        if not isinstance(ev["manifest_sha256"], str) or not _SHA256.match(ev["manifest_sha256"]):
            errs.append("evidence.manifest_sha256 must be 64-hex")
        elif _ZERO_DIGEST.match(ev["manifest_sha256"]):
            errs.append("evidence.manifest_sha256 is all zeros")

    val = p["validity"]
    e = _exact_keys(val, {"not_before", "expires_at"}, "validity")
    errs += e
    if not e:
        nb, ex = parse_time(val["not_before"]), parse_time(val["expires_at"])
        if nb is None or ex is None:
            errs.append("validity times must be YYYY-MM-DDTHH:MM:SSZ")
        elif ex <= nb:
            errs.append("validity.expires_at must be after not_before")

    use = p["use"]
    e = _exact_keys(use, {"max_uses", "single_use"}, "use")
    errs += e
    if not e:
        if use["single_use"] is not True:
            errs.append("use.single_use must be true")
        if use["max_uses"] != 1 or isinstance(use["max_uses"], bool):
            errs.append("use.max_uses must be 1 (multi-use authorizations are not implemented)")
    return errs


# ── ledger + revocations ────────────────────────────────────────────────────────
def load_json_bytes(raw: bytes | None, default):
    if raw is None:
        return default
    return strict_loads(raw)


def ledger_entries(doc) -> list[dict]:
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != LEDGER_SCHEMA
        or not isinstance(doc.get("entries"), list)
    ):
        raise AuthorizationError("consumed ledger: wrong schema or no entries list")
    return doc["entries"]


def revoked_ids(doc) -> set[str]:
    if (
        not isinstance(doc, dict)
        or doc.get("schema") != REVOCATION_SCHEMA
        or not isinstance(doc.get("revoked"), list)
    ):
        raise AuthorizationError("revocation list: wrong schema or no revoked list")
    return {str(r.get("decision_id")) for r in doc["revoked"] if isinstance(r, dict)}


def append_only_errors(base_list: list, head_list: list, what: str) -> list[str]:
    """Base entries must be an unchanged prefix of head entries."""
    if head_list[: len(base_list)] != base_list:
        return [f"{what} is append-only: an existing entry was removed, edited or reordered"]
    return []


def ledger_entry(payload: dict, envelope_bytes: bytes, reserved_at: str) -> dict:
    return {
        "decision_id": payload["decision_id"],
        "action": payload["action"],
        "pr_number": payload["identity"]["pr_number"],
        "head_sha": payload["subject"]["head_sha"],
        "subject_sha256": subject_digest(payload),
        "envelope_sha256": sha256_hex(envelope_bytes),
        "reserved_at": reserved_at,
    }


def reserve_consumption(ledger_path: Path, entry: dict, *, timeout: float = 10.0) -> bool:
    """Atomically append ``entry`` unless its decision_id is already there.

    Exactly one of N concurrent callers wins: an ``O_CREAT|O_EXCL`` lock file
    serializes read-check-append, and the write goes through ``os.replace``.
    Returns ``True`` for the winner, ``False`` if the decision was already reserved.
    """
    lock = ledger_path.with_name(ledger_path.name + ".lock")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"ledger lock {lock} held for more than {timeout}s") from None
            time.sleep(0.005)
    try:
        os.write(fd, str(os.getpid()).encode())
        if ledger_path.exists():
            doc = strict_loads(ledger_path.read_bytes())
        else:
            doc = {"schema": LEDGER_SCHEMA, "entries": []}
        entries = ledger_entries(doc)
        if any(e.get("decision_id") == entry["decision_id"] for e in entries):
            return False
        entries.append(entry)
        tmp = ledger_path.with_name(ledger_path.name + f".tmp{os.getpid()}.{id(entry)}")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, ledger_path)
        return True
    finally:
        os.close(fd)
        os.unlink(lock)


# ── verification of one envelope ────────────────────────────────────────────────
@dataclass
class Context:
    """Everything a verdict depends on that is not inside the envelope."""

    root: Path
    config: dict
    allowed_signers: str | None  # trust root text read from the trusted base
    now: datetime
    repository: str | None = None
    repository_id: int | None = None
    pr_number: int | None = None
    base_ref: str | None = None  # trusted base (e.g. origin/main)
    pr_head: str | None = None  # the PR head that carries the envelope
    base_ledger: list = field(default_factory=list)
    head_ledger: list = field(default_factory=list)
    revoked: set = field(default_factory=set)


@dataclass
class Verdict:
    status: str
    path: str
    decision_id: str | None = None
    action: str | None = None
    reasons: list = field(default_factory=list)
    payload: dict | None = None

    def scope_paths(self) -> dict[str, dict]:
        scope = ((self.payload or {}).get("subject") or {}).get("scope") or []
        return {e.get("path"): e for e in scope if isinstance(e, dict)}


def _trailer_paths(config: dict, envelope_path: str) -> set[str]:
    return {envelope_path, config["consumed_ledger_path"], config["revocations_path"]}


def verify_envelope(raw: bytes, envelope_path: str, ctx: Context) -> Verdict:
    """Verify one committed envelope against the trusted context. Never raises."""
    v = Verdict(UNVERIFIED, envelope_path)
    try:
        payload_bytes, payload, armored, keyid = parse_envelope(raw)
    except AuthorizationError as exc:
        v.status, v.reasons = INVALID, [str(exc)]
        return v
    v.payload, v.decision_id, v.action = payload, payload.get("decision_id"), payload.get("action")

    schema = payload_schema_errors(payload)
    if schema:
        v.status, v.reasons = INVALID, schema
        return v
    if Path(envelope_path).name != payload["decision_id"] + ENVELOPE_SUFFIX:
        v.status, v.reasons = (
            INVALID,
            [f"file name must be {payload['decision_id']}{ENVELOPE_SUFFIX}"],
        )
        return v

    # Trust root first: without a trusted key nothing below can mean "owner".
    try:
        signers = parse_allowed_signers(ctx.allowed_signers)
    except AuthorizationError as exc:
        v.reasons = [f"{NOT_CONFIGURED} (trust root unreadable: {exc})"]
        return v
    if not signers:
        v.reasons = [NOT_CONFIGURED]
        return v
    if not ssh_keygen_available():
        v.reasons = ["ssh-keygen is not available — signature cannot be checked"]
        return v

    signer = payload["identity"]["signer"]
    if keyid != signer:
        v.status, v.reasons = (
            INVALID,
            [f"envelope keyid {keyid!r} differs from signed identity.signer {signer!r}"],
        )
        return v
    if signer not in signers:
        v.status, v.reasons = (
            INVALID,
            [f"unknown signer {signer!r}: not in the trusted allowed_signers"],
        )
        return v
    ok, detail = ssh_verify(
        pae(PAYLOAD_TYPE, payload_bytes),
        armored,
        ctx.allowed_signers or "",
        signer,
        ctx.config["namespace"],
    )
    if not ok:
        v.status, v.reasons = (
            INVALID,
            [
                f"signature does not verify for {signer!r} in namespace "
                f"{ctx.config['namespace']!r}: {detail}"
            ],
        )
        return v

    reasons: list[str] = []
    # Validity window.
    nb, ex = (
        parse_time(payload["validity"]["not_before"]),
        parse_time(payload["validity"]["expires_at"]),
    )
    if ctx.now + CLOCK_SKEW < nb:
        reasons.append(f"not yet valid (not_before {format_time(nb)} > now {format_time(ctx.now)})")
    if ctx.now >= ex:
        reasons.append(f"expired (expires_at {format_time(ex)} <= now {format_time(ctx.now)})")
    if ex - nb > timedelta(days=int(ctx.config["max_validity_days"])):
        reasons.append(f"validity window longer than {ctx.config['max_validity_days']} days")
    if payload["decision_id"] in ctx.revoked:
        reasons.append("decision is revoked")

    # Identity binding: unknown CI context is UNVERIFIED, never assumed.
    ident = payload["identity"]
    missing_ctx = [
        name
        for name, value in (
            ("repository", ctx.repository),
            ("repository_id", ctx.repository_id),
            ("pr_number", ctx.pr_number),
            ("base_ref", ctx.base_ref),
            ("pr_head", ctx.pr_head),
        )
        if value in (None, "")
    ]
    if missing_ctx:
        v.reasons = reasons + [f"CI context missing: {missing_ctx} — subject cannot be bound"]
        v.status = INVALID if reasons else UNVERIFIED
        return v
    if ident["repository"] != ctx.repository:
        reasons.append(f"signed for repository {ident['repository']!r}, this is {ctx.repository!r}")
    if ident["repository_id"] != ctx.repository_id:
        reasons.append(
            f"signed for repository_id {ident['repository_id']}, this is {ctx.repository_id}"
        )
    if ident["pr_number"] != ctx.pr_number:
        reasons.append(f"signed for PR #{ident['pr_number']}, this is PR #{ctx.pr_number}")

    # Subject binding against git, not against anything the PR declares.
    subj = payload["subject"]
    root = ctx.root
    pr_head = rev_parse(root, ctx.pr_head)
    if pr_head is None or rev_parse(root, ctx.base_ref) is None:
        reasons.append("base_ref or pr_head is not a commit in this clone")
    elif rev_parse(root, subj["head_sha"]) is None:
        reasons.append(f"signed head_sha {subj['head_sha']} is not in this clone")
    else:
        actual_base = merge_base(root, ctx.base_ref, pr_head)
        if subj["base_sha"] != actual_base:
            reasons.append(
                f"base changed after approval: signed base_sha {subj['base_sha']}, "
                f"merge-base is now {actual_base} — re-sign after a rebase or merge from base"
            )
        if not is_ancestor(root, subj["head_sha"], pr_head):
            reasons.append(f"signed head_sha {subj['head_sha']} is not an ancestor of the PR head")
        else:
            extra = sorted(
                set(changed_paths(root, subj["head_sha"], pr_head))
                - _trailer_paths(ctx.config, envelope_path)
            )
            if extra:
                reasons.append(
                    f"commits after the signed head change more than the authorization files: {extra}"
                )
        if tree_of(root, subj["head_sha"]) != subj["tree_sha"]:
            reasons.append("signed tree_sha is not the tree of the signed head_sha")
        if subj["base_sha"] == actual_base:
            actual_scope = derive_scope(root, subj["base_sha"], subj["head_sha"])
            if actual_scope != sorted(subj["scope"], key=lambda e: e.get("path", "")):
                signed = {e["path"]: e for e in subj["scope"]}
                real = {e["path"]: e for e in actual_scope}
                diff = sorted(p for p in set(signed) | set(real) if signed.get(p) != real.get(p))
                reasons.append(f"signed scope differs from the actual change set at: {diff}")
        evidence = show_bytes(root, subj["head_sha"], payload["evidence"]["manifest_path"])
        if evidence is None:
            reasons.append(
                f"evidence manifest {payload['evidence']['manifest_path']!r} absent at the signed head"
            )
        elif sha256_hex(evidence) != payload["evidence"]["manifest_sha256"]:
            reasons.append("evidence manifest bytes differ from the signed manifest_sha256")

    # Single use: consumed on base ⇒ refused; reserved exactly once in this PR.
    did = payload["decision_id"]
    if any(e.get("decision_id") == did for e in ctx.base_ledger if isinstance(e, dict)):
        reasons.append("decision already consumed (present in the base consumed ledger)")
    mine = [e for e in ctx.head_ledger if isinstance(e, dict) and e.get("decision_id") == did]
    if len(mine) != 1:
        reasons.append(
            f"decision must be reserved exactly once in the consumed ledger (found {len(mine)})"
        )
    else:
        if mine[0].get("subject_sha256") != subject_digest(payload):
            reasons.append("ledger reservation is for another subject")
        if mine[0].get("envelope_sha256") != sha256_hex(raw):
            reasons.append("ledger reservation names another envelope")

    v.status, v.reasons = (INVALID, reasons) if reasons else (VERIFIED, [])
    return v


# ── policy-level checks used by gate01_frozen_path_guard ───────────────────────
def effective_config(base_policy: dict | None, head_policy: dict) -> dict | None:
    """The base policy's config governs a PR; the head's is used only without a base."""
    block = (base_policy or {}).get("owner_signature")
    if block is None:
        block = head_policy.get("owner_signature")
    if block is None:
        return None
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in block.items() if not str(k).startswith("$")})
    return cfg


def config_weakenings(base_block: dict | None, head_block: dict | None) -> list[str]:
    """Changes to ``owner_signature`` that reduce enforcement (need a signed policy_change)."""
    if base_block is None:
        return []
    if head_block is None:
        return ["owner_signature block removed"]
    out = []
    base_req, head_req = (
        set(base_block.get("required_for") or []),
        set(head_block.get("required_for") or []),
    )
    if base_req - head_req:
        out.append(f"required_for dropped {sorted(base_req - head_req)}")
    if (
        base_block.get("required_for_bounded") is True
        and head_block.get("required_for_bounded") is not True
    ):
        out.append("required_for_bounded turned off")
    for key in _CONFIG_IDENTITY_KEYS:
        if base_block.get(key) != head_block.get(key):
            out.append(f"{key} changed")
    if (head_block.get("max_validity_days") or 0) > (base_block.get("max_validity_days") or 0):
        out.append("max_validity_days increased")
    return out


def transition_content_errors(policy: dict, decision_id: str | None, config: dict) -> list[str]:
    """An OPEN policy must name its signed decision and carry real phase-0 evidence fields."""
    gate = policy.get("gate") or {}
    base = policy.get("phase0_baseline") or {}
    errs = []
    want = f"{config['authorizations_dir']}/{decision_id}{ENVELOPE_SUFFIX}" if decision_id else None
    if not want or gate.get("ruling_source") != want:
        errs.append(
            f"gate.ruling_source must name the signed decision envelope ({want or '<none verified>'})"
        )
    if parse_time(f"{gate.get('owner_ruling_on')}T00:00:00Z") is None:
        errs.append("gate.owner_ruling_on must be a YYYY-MM-DD date")
    for key in (
        "commit_sha",
        "tree_sha",
        "evidence_run_id",
        "evidence_conclusion",
        "evidence_status",
    ):
        if not base.get(key):
            errs.append(f"phase0_baseline.{key} missing")
    if base.get("evidence_status") != "FROZEN":
        errs.append("phase0_baseline.evidence_status must be FROZEN")
    if base.get("evidence_conclusion") != "success":
        errs.append("phase0_baseline.evidence_conclusion must be success")
    for key in ("commit_sha", "tree_sha"):
        val = str(base.get(key) or "")
        if not _SHA1.match(val) or set(val) == {"0"}:
            errs.append(f"phase0_baseline.{key} must be a non-zero 40-hex id")
    digests = base.get("artifact_digests")
    if not isinstance(digests, dict) or not digests:
        errs.append("phase0_baseline.artifact_digests missing")
    else:
        for name, value in digests.items():
            if not re.match(r"^sha256:[0-9a-f]{64}$", str(value)) or _ZERO_DIGEST.match(str(value)):
                errs.append(f"phase0_baseline.artifact_digests[{name!r}] is not a real sha256")
    return errs


def _is_open(policy: dict | None) -> bool:
    return str(((policy or {}).get("gate") or {}).get("state", "")).strip().upper() == "OPEN"


def _read_head(root: Path, rel: str) -> bytes | None:
    path = root / rel
    return path.read_bytes() if path.is_file() else None


def build_context(
    root: Path,
    head_policy: dict,
    *,
    base_ref: str | None,
    pr_head: str | None,
    repository: str | None,
    repository_id: int | None,
    pr_number: int | None,
    now: datetime,
) -> tuple[Context | None, dict | None, list[str]]:
    """Read the trusted half (base) and the PR half (working tree). Returns (ctx, base_policy, errors)."""
    errors: list[str] = []
    base_policy = None
    base_commit = rev_parse(root, base_ref) if base_ref else None
    if base_ref and base_commit is None:
        errors.append(
            f"--base-ref {base_ref!r} is not a commit in this clone — cannot read the trusted base"
        )
    if base_commit:
        raw = show_bytes(root, base_commit, POLICY_PATH)
        base_policy = json.loads(raw.decode("utf-8")) if raw else None
    cfg = effective_config(base_policy, head_policy)
    if cfg is None:
        return None, base_policy, errors
    signers_text = None
    base_ledger, head_ledger, revoked = [], [], set()
    try:
        if base_commit:
            raw = show_bytes(root, base_commit, cfg["allowed_signers_path"])
            signers_text = raw.decode("utf-8") if raw is not None else None
            base_ledger = ledger_entries(
                load_json_bytes(
                    show_bytes(root, base_commit, cfg["consumed_ledger_path"]),
                    {"schema": LEDGER_SCHEMA, "entries": []},
                )
            )
            base_revoked_doc = load_json_bytes(
                show_bytes(root, base_commit, cfg["revocations_path"]),
                {"schema": REVOCATION_SCHEMA, "revoked": []},
            )
            revoked |= revoked_ids(base_revoked_doc)
        head_ledger = ledger_entries(
            load_json_bytes(
                _read_head(root, cfg["consumed_ledger_path"]),
                {"schema": LEDGER_SCHEMA, "entries": []},
            )
        )
        head_revoked_doc = load_json_bytes(
            _read_head(root, cfg["revocations_path"]), {"schema": REVOCATION_SCHEMA, "revoked": []}
        )
        revoked |= revoked_ids(head_revoked_doc)
        if base_commit:
            errors += append_only_errors(base_ledger, head_ledger, cfg["consumed_ledger_path"])
            errors += append_only_errors(
                base_revoked_doc["revoked"], head_revoked_doc["revoked"], cfg["revocations_path"]
            )
    except (AuthorizationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(f"owner-signature records unreadable: {exc}")
    ctx = Context(
        root=root,
        config=cfg,
        allowed_signers=signers_text,
        now=now,
        repository=repository,
        repository_id=repository_id,
        pr_number=pr_number,
        base_ref=base_commit,
        pr_head=pr_head,
        base_ledger=base_ledger,
        head_ledger=head_ledger,
        revoked=revoked,
    )
    return ctx, base_policy, errors


def owner_signature_findings(
    root: Path,
    changed: list[str],
    head_policy: dict,
    frozen_touched: set[str],
    *,
    base_ref: str | None = None,
    pr_head: str | None = None,
    repository: str | None = None,
    repository_id: int | None = None,
    pr_number: int | None = None,
    now: datetime | None = None,
) -> tuple[list[str], list[str]]:
    """``(errors, notes)`` for one PR. Errors block; notes are printed advisories."""
    now = now or datetime.now(UTC)
    ctx, base_policy, errors = build_context(
        root,
        head_policy,
        base_ref=base_ref,
        pr_head=pr_head,
        repository=repository,
        repository_id=repository_id,
        pr_number=pr_number,
        now=now,
    )
    notes: list[str] = []
    if ctx is None:
        return errors, notes
    cfg = ctx.config
    has_base = ctx.base_ref is not None
    configured = False
    try:
        configured = bool(parse_allowed_signers(ctx.allowed_signers))
    except AuthorizationError:
        configured = False
    if not configured:
        where = (
            "on the trusted base" if has_base else "(no --base-ref: the trusted base was not read)"
        )
        notes.append(
            f"GATE-01 owner signature: {NOT_CONFIGURED} {where} — every authorization is UNVERIFIED"
        )

    prefix = cfg["authorizations_dir"].rstrip("/") + "/"
    verdicts: list[Verdict] = []
    for rel in sorted(set(changed)):
        if not rel.startswith(prefix):
            continue
        if not rel.endswith(ENVELOPE_SUFFIX):
            errors.append(f"{rel}: only *{ENVELOPE_SUFFIX} envelopes belong in {prefix}")
            continue
        raw = _read_head(root, rel)
        if raw is None:
            errors.append(
                f"{rel}: an authorization envelope was deleted or is missing — records are append-only"
            )
            continue
        verdicts.append(verify_envelope(raw, rel, ctx))
    for v in verdicts:
        if v.status == INVALID:
            errors.append(f"{v.path}: INVALID owner authorization — " + "; ".join(v.reasons))
        elif v.status == UNVERIFIED:
            notes.append(f"{v.path}: UNVERIFIED — " + "; ".join(v.reasons))

    def satisfied(action: str, paths: set[str]) -> Verdict | None:
        for v in verdicts:
            if v.status == VERIFIED and v.action == action and paths <= set(v.scope_paths()):
                return v
        return None

    def why_not(action: str) -> str:
        if not configured:
            return NOT_CONFIGURED
        if not verdicts:
            return f"no signed {action} envelope in {prefix} in this PR"
        return "no VERIFIED envelope for this action and scope"

    # 1) CLOSED → OPEN.
    base_open = _is_open(base_policy) if has_base else None
    transition = POLICY_PATH in changed and _is_open(head_policy) and base_open is not True
    if transition:
        if "state_transition" in (cfg.get("required_for") or []):
            hit = satisfied("state_transition", {POLICY_PATH})
            if hit is None:
                errors.append(
                    "GATE-01 CLOSED→OPEN refused: a verified owner-signed state_transition authorization "
                    f"for this exact policy change is required ({why_not('state_transition')})"
                    + ("" if has_base else "; no --base-ref, so a transition cannot be ruled out")
                )
            else:
                errors += [
                    f"GATE-01 OPEN policy: {e}"
                    for e in transition_content_errors(head_policy, hit.decision_id, cfg)
                ]
        else:
            notes.append(
                "GATE-01 CLOSED→OPEN without owner signature: state_transition is not in required_for"
            )

    # 2) weakening the owner_signature block itself.
    if POLICY_PATH in changed:
        if has_base:
            weak = config_weakenings(
                (base_policy or {}).get("owner_signature"), head_policy.get("owner_signature")
            )
            if weak and satisfied("policy_change", {POLICY_PATH}) is None:
                errors.append(
                    f"owner_signature weakened ({'; '.join(weak)}) without a verified owner-signed policy_change "
                    f"({why_not('policy_change')})"
                )
        else:
            notes.append("owner_signature weakening not evaluated: no --base-ref")

    # 3) trust root changes after the first installation need the trusted key.
    signers_path = cfg["allowed_signers_path"]
    if signers_path in changed:
        if not has_base:
            try:
                head_keys = parse_allowed_signers(
                    (_read_head(root, signers_path) or b"").decode("utf-8")
                )
            except AuthorizationError:
                head_keys = {"<malformed>": []}
            if head_keys:
                errors.append(
                    f"{signers_path} changed and carries keys, with no --base-ref: trust-root change cannot be "
                    "judged (fail closed)"
                )
            else:
                notes.append(f"{signers_path} changed but holds no key — nothing is trusted")
        elif configured:
            if satisfied("trust_root_change", {signers_path}) is None:
                errors.append(
                    f"{signers_path} changed: rotating the owner key needs an authorization signed by the "
                    f"currently trusted key ({why_not('trust_root_change')})"
                )
        else:
            notes.append(
                f"{signers_path}: INITIAL trust-root installation — not signature-checked; the owner must "
                "verify the key fingerprint in this PR (runbook GATE01_OWNER_SIGNING.md)"
            )

    # 4) bounded adjudications (frozen path touched while CLOSED).
    if frozen_touched and not _is_open(head_policy):
        hit = satisfied("bounded_change", set(frozen_touched))
        if hit is None:
            msg = (
                f"bounded GATE-01 change to {sorted(frozen_touched)} carries no verified owner signature "
                f"({why_not('bounded_change')})"
            )
            if cfg.get("required_for_bounded") is True:
                errors.append(msg)
            else:
                notes.append(msg + " — advisory until required_for_bounded=true")
        else:
            notes.append(f"bounded GATE-01 change owner-signed: {hit.decision_id}")
    return errors, notes


# ── CLI ─────────────────────────────────────────────────────────────────────────
def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = parse_time(value)
    if parsed is None:
        raise SystemExit(f"--now must be YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify one owner-signed GATE-01 authorization envelope."
    )
    parser.add_argument(
        "envelope", help=f"path to <decision_id>{ENVELOPE_SUFFIX} (relative to --root)"
    )
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--base-ref", required=True, help="trusted base, e.g. origin/main")
    parser.add_argument("--pr-head", default="HEAD")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--repository-id", default=os.environ.get("GITHUB_REPOSITORY_ID"))
    parser.add_argument("--pr-number", default=None)
    parser.add_argument("--now", default=None, help="YYYY-MM-DDTHH:MM:SSZ (default: wall clock)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    head_policy = json.loads((root / POLICY_PATH).read_text(encoding="utf-8"))
    ctx, _base_policy, errors = build_context(
        root,
        head_policy,
        base_ref=args.base_ref,
        pr_head=args.pr_head,
        repository=args.repository,
        repository_id=_int_or_none(args.repository_id),
        pr_number=_int_or_none(args.pr_number),
        now=_parse_now(args.now),
    )
    if ctx is None:
        print("UNVERIFIED: no owner_signature block in the policy")
        return 2
    rel = Path(args.envelope).as_posix()
    raw = _read_head(root, rel)
    if raw is None:
        print(f"INVALID: {rel} not found")
        return 1
    verdict = verify_envelope(raw, rel, ctx)
    for e in errors:
        print(f"- {e}")
    print(f"{verdict.status}: {verdict.decision_id or rel} ({verdict.action or '?'})")
    for r in verdict.reasons:
        print(f"  - {r}")
    if errors and verdict.status == VERIFIED:
        return 1
    return {VERIFIED: 0, INVALID: 1}.get(verdict.status, 2)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
