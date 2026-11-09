#!/usr/bin/env python3
"""Owner-side helper for GATE-01 signed authorizations (runbook: docs/runbooks/GATE01_OWNER_SIGNING.md).

Anyone may run ``prepare`` and ``envelope``; only the owner runs ``ssh-keygen -Y sign``
between them, with a key that never enters the repository or the agent environment.

    prepare   build the canonical payload from base/head/tree and the diff, and write
              the exact DSSE PAE bytes the owner signs (<id>.pae)
    envelope  wrap payload + the owner's <id>.pae.sig into <id>.dsse.json
    reserve   atomically record the decision in the consumed ledger (single use)

All formats and checks live in ``scripts/ci/gate01_owner_signature_guard.py`` — this
file only drives them, so the helper and the verifier cannot drift apart.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "gate01_owner_signature_guard", ROOT / "scripts" / "ci" / "gate01_owner_signature_guard.py"
)
sig = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("gate01_owner_signature_guard", sig)
_spec.loader.exec_module(sig)


def build_payload(
    root: Path,
    *,
    base_ref: str,
    head: str,
    action: str,
    decision_id: str,
    repository: str,
    repository_id: int,
    pr_number: int,
    signer: str,
    evidence_manifest: str,
    not_before: datetime,
    valid_days: float,
    nonce: str | None = None,
) -> dict:
    head_sha = sig.rev_parse(root, head)
    if head_sha is None:
        raise SystemExit(f"{head!r} is not a commit")
    base_sha = sig.merge_base(root, base_ref, head_sha)
    if base_sha is None:
        raise SystemExit(f"no merge-base between {base_ref!r} and {head_sha}")
    evidence = sig.show_bytes(root, head_sha, evidence_manifest)
    if evidence is None:
        raise SystemExit(f"evidence manifest {evidence_manifest!r} is absent at {head_sha}")
    payload = {
        "schema": sig.SCHEMA,
        "decision_id": decision_id,
        "action": action,
        "identity": {
            "repository": repository,
            "repository_id": repository_id,
            "pr_number": pr_number,
            "signer": signer,
            "signer_role": sig.SIGNER_ROLE,
        },
        "subject": {
            "base_sha": base_sha,
            "head_sha": head_sha,
            "tree_sha": sig.tree_of(root, head_sha),
            "scope": sig.derive_scope(root, base_sha, head_sha),
        },
        "evidence": {
            "manifest_path": evidence_manifest,
            "manifest_sha256": sig.sha256_hex(evidence),
        },
        "validity": {
            "not_before": sig.format_time(not_before),
            "expires_at": sig.format_time(not_before + timedelta(days=valid_days)),
        },
        "use": {"max_uses": 1, "single_use": True},
        "nonce": nonce or secrets.token_hex(16),
    }
    errs = sig.payload_schema_errors(payload)
    if errs:
        raise SystemExit("payload would be refused: " + "; ".join(errs))
    return payload


def _cmd_prepare(args) -> int:
    root = Path(args.root).resolve()
    nb = (
        sig.parse_time(args.not_before)
        if args.not_before
        else datetime.now(UTC).replace(microsecond=0)
    )
    if nb is None:
        raise SystemExit("--not-before must be YYYY-MM-DDTHH:MM:SSZ")
    payload = build_payload(
        root,
        base_ref=args.base_ref,
        head=args.head,
        action=args.action,
        decision_id=args.decision_id,
        repository=args.repository,
        repository_id=args.repository_id,
        pr_number=args.pr_number,
        signer=args.signer,
        evidence_manifest=args.evidence_manifest,
        not_before=nb,
        valid_days=args.valid_days,
        nonce=args.nonce,
    )
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    body = sig.canonical_json(payload)
    (out / f"{args.decision_id}.payload.json").write_bytes(body)
    (out / f"{args.decision_id}.pae").write_bytes(sig.pae(sig.PAYLOAD_TYPE, body))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(
        f"\nwrote {out / (args.decision_id + '.payload.json')} and {out / (args.decision_id + '.pae')}"
    )
    print(
        "owner signs (offline key, never in the repo):\n"
        f"  ssh-keygen -Y sign -f <owner_key> -n {sig.NAMESPACE_DEFAULT} {out / (args.decision_id + '.pae')}"
    )
    return 0


def _cmd_envelope(args) -> int:
    body = Path(args.payload).read_bytes()
    payload = sig.strict_loads(body)
    if sig.canonical_json(payload) != body:
        raise SystemExit("payload file is not canonical — re-run prepare, do not hand-edit it")
    pae_path = Path(args.payload).with_name(f"{payload['decision_id']}.pae")
    if pae_path.exists() and pae_path.read_bytes() != sig.pae(sig.PAYLOAD_TYPE, body):
        raise SystemExit(f"{pae_path} does not match the payload — the signature would not verify")
    armored = Path(args.signature).read_bytes()
    if b"BEGIN SSH SIGNATURE" not in armored:
        raise SystemExit("signature file is not an armored SSH signature")
    out = (
        Path(args.out)
        if args.out
        else Path(args.root)
        / sig.DEFAULT_CONFIG["authorizations_dir"]
        / (payload["decision_id"] + sig.ENVELOPE_SUFFIX)
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(sig.build_envelope(body, armored, payload["identity"]["signer"]))
    print(f"wrote {out}")
    return 0


def _cmd_reserve(args) -> int:
    raw = Path(args.envelope).read_bytes()
    _body, payload, _armored, _keyid = sig.parse_envelope(raw)
    entry = sig.ledger_entry(payload, raw, args.reserved_at or sig.format_time(datetime.now(UTC)))
    won = sig.reserve_consumption(Path(args.ledger), entry)
    print("RESERVED" if won else "ALREADY-RESERVED", payload["decision_id"])
    return 0 if won else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="build payload + PAE bytes to sign")
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--base-ref", default="origin/main")
    p.add_argument(
        "--head", default="HEAD", help="the tested commit (before the authorization commit)"
    )
    p.add_argument("--action", required=True, choices=sig.ACTIONS)
    p.add_argument("--decision-id", required=True, help="GATE01-AUTH-YYYY-MM-DD-NNN")
    p.add_argument("--repository", required=True, help="owner/name")
    p.add_argument("--repository-id", required=True, type=int, help="numeric GitHub repository id")
    p.add_argument("--pr-number", required=True, type=int)
    p.add_argument("--signer", required=True, help="principal in owner_allowed_signers")
    p.add_argument(
        "--evidence-manifest", required=True, help="repo path of the accepted evidence manifest"
    )
    p.add_argument("--not-before", default=None, help="YYYY-MM-DDTHH:MM:SSZ (default: now)")
    p.add_argument("--valid-days", type=float, default=3.0)
    p.add_argument("--nonce", default=None)
    p.add_argument("--out-dir", default=".")
    p.set_defaults(func=_cmd_prepare)

    e = sub.add_parser("envelope", help="wrap payload + owner signature into a DSSE envelope")
    e.add_argument("--root", default=str(ROOT))
    e.add_argument("--payload", required=True)
    e.add_argument("--signature", required=True, help="<id>.pae.sig produced by ssh-keygen -Y sign")
    e.add_argument("--out", default=None)
    e.set_defaults(func=_cmd_envelope)

    r = sub.add_parser("reserve", help="atomically record the decision in the consumed ledger")
    r.add_argument("--envelope", required=True)
    r.add_argument("--ledger", default=str(ROOT / sig.DEFAULT_CONFIG["consumed_ledger_path"]))
    r.add_argument("--reserved-at", default=None)
    r.set_defaults(func=_cmd_reserve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
