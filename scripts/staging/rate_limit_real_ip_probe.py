#!/usr/bin/env python3
"""Owner-run probe: does Railway's edge overwrite a client-supplied X-Real-IP?

Gap RATE-LIMIT-KEY-IS-A-RAILWAY-NODE-NOT-THE-CLIENT-01. Runbook:
docs/runbooks/RATE_LIMIT_REAL_IP_MEASUREMENT.md.

Sends exactly two read-only ``GET /`` requests (the SPA shell: no backend, no auth, no
rate-limited location) to the gateway, each tagged in its query string:

1. ``<tag>-spoofed`` with ``X-Real-IP: 203.0.113.7`` (TEST-NET-3, never a real client);
2. ``<tag>-plain`` without it.

It then prints what to look for in the gateway's access log and exits. It reads no logs,
holds no credentials, and writes nothing. The verdict comes from the log line ``xrip="..."``
that only the gateway can see, so this script cannot and does not decide it.

Refuses to run unless BOTH ``--i-am-the-owner-run`` and ``--target`` are given, and refuses in
CI (``CI`` or ``GITHUB_ACTIONS`` set): no workflow may run it.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence

SPOOFED_REAL_IP = "203.0.113.7"
OWNER_FLAG = "--i-am-the-owner-run"
CI_VARIABLES = ("CI", "GITHUB_ACTIONS")
REFUSED = 2
TIMEOUT_SECONDS = 15

Send = Callable[[str, Mapping[str, str]], int]


class Refused(Exception):
    """The run is refused before any network request."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        OWNER_FLAG,
        dest="owner_run",
        action="store_true",
        help="required: the owner is running this by hand against a gateway they chose",
    )
    parser.add_argument("--target", help="required: gateway base URL, e.g. https://<host>")
    parser.add_argument(
        "--tag", help="query-string tag to find the two log lines (default: random)"
    )
    parser.add_argument(
        "--allow-non-staging-target",
        action="store_true",
        help="allow a host whose name does not contain 'staging' (the runbook measures staging)",
    )
    return parser


def validate(args: argparse.Namespace, env: Mapping[str, str]) -> str:
    """Return the normalised base URL, or raise :class:`Refused` naming the reason."""
    ci = [
        name for name in CI_VARIABLES if env.get(name, "").strip().lower() not in {"", "0", "false"}
    ]
    if ci:
        raise Refused(
            f"refusing to run in CI ({', '.join(ci)} is set): this probe is owner-run only"
        )
    if not args.owner_run:
        raise Refused(f"refusing to run without {OWNER_FLAG}")
    if not args.target:
        raise Refused("refusing to run without --target <gateway base URL>")
    url = urllib.parse.urlsplit(args.target)
    if url.scheme != "https" or not url.hostname:
        raise Refused("--target must be an https:// URL with a host")
    if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise Refused("--target must be a bare origin: no credentials, path, query or fragment")
    if "staging" not in url.hostname and not args.allow_non_staging_target:
        raise Refused(
            f"--target host {url.hostname!r} does not look like staging; "
            "pass --allow-non-staging-target to measure it anyway"
        )
    if args.tag is not None and not (args.tag.isascii() and args.tag.replace("-", "").isalnum()):
        raise Refused("--tag may contain only ASCII letters, digits and '-'")
    return f"https://{url.netloc}"


def _send(url: str, headers: Mapping[str, str]) -> int:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (https only, validated)
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def probe(base: str, tag: str, send: Send) -> list[tuple[str, str, int]]:
    """Send the two tagged requests; return (label, url, status) for each."""
    results = []
    for label, headers in (
        ("spoofed", {"X-Real-IP": SPOOFED_REAL_IP}),
        ("plain", {}),
    ):
        url = f"{base}/?sahool_real_ip_probe={tag}-{label}"
        results.append(
            (label, url, send(url, {"User-Agent": f"sahool-real-ip-probe/{tag}", **headers}))
        )
    return results


def instructions(tag: str) -> str:
    return f"""
Now read the gateway (sahool-frontend) access log for the two lines tagged
  sahool_real_ip_probe={tag}-spoofed   and   sahool_real_ip_probe={tag}-plain
Each line ends:  "<X-Forwarded-For>" xrip="<X-Real-IP as received>" rl_key="<limiter key>"

Compare the two xrip values (full reading: docs/runbooks/RATE_LIMIT_REAL_IP_MEASUREMENT.md):
  A. spoofed xrip == plain xrip == your real address (the LEFT X-Forwarded-For element),
     and {SPOOFED_REAL_IP} appears nowhere in it
       -> the edge OVERWRITES X-Real-IP: key on X-Real-IP.
  B. spoofed xrip contains {SPOOFED_REAL_IP}
       -> the edge does NOT overwrite it (a client picks its own bucket): do not key on it;
          key on the 2nd-from-right X-Forwarded-For element, 152.233.30.0/24 trusted in auth.
  C. plain xrip is "-" (absent)
       -> the edge does not set X-Real-IP at all: same decision as B.
  Anything else (lines missing, values differ between runs) -> inconclusive; run again.
"""


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    send: Send = _send,
) -> int:
    args = _parser().parse_args(argv)
    try:
        base = validate(args, os.environ if env is None else env)
    except Refused as exc:
        print(f"rate_limit_real_ip_probe: refused: {exc}", file=sys.stderr)
        return REFUSED
    tag = args.tag or secrets.token_hex(6)
    print(f"Probing {base} (two GET / requests, tag {tag})")
    for label, url, status in probe(base, tag, send):
        print(f"  {label:<8} {status}  {url}")
    print(instructions(tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
