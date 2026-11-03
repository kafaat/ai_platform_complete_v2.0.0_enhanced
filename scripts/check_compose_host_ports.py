#!/usr/bin/env python3
"""Pre-flight: which host ports published by the compose file(s) are already taken on this machine.

``docker compose up`` fails the whole stack on one busy port, and on Windows the message
does not say which service or how to move it::

    Error response from daemon: ports are not available: exposing port TCP
    127.0.0.1:8554 -> 127.0.0.1:0: listen tcp4 127.0.0.1:8554: bind: Only one usage of
    each socket address (protocol/network address/port) is normally permitted.

This script reads every ``ports:`` entry, expands ``${VAR:-default}`` the way Compose does
(shell environment first, then the ``.env`` next to the first compose file), tries to bind
each host address/port/protocol, and prints the busy ones with the service, the file:line
and the variable that moves the port (for example ``ZLM_RTSP_HOST_PORT=18554`` in ``.env``).

Stdlib only, no bash: runs the same on Windows (``py scripts\\check_compose_host_ports.py``)
and Linux (``python3 scripts/check_compose_host_ports.py``). It never starts, stops or edits
anything; the probe socket is closed straight away.

Usage:
    python scripts/check_compose_host_ports.py [-f docker-compose.v9.yml ...]
        [--env-file .env] [--json] [--verbose]

Files default to ``COMPOSE_FILE`` (split on ``os.pathsep``, as Compose does) or
``docker-compose.v9.yml``. Exit 0 when every port can be bound, 1 when any port is busy,
denied or published twice by the files themselves, 2 on a usage error.

Limits (stated, not hidden): the compose reader is a line scanner for the block/flow forms
used in this repository (no anchors/merge keys inside ``ports:``); every service is checked
whatever its ``profiles:`` (profile-gated entries are labelled); a port already held by this
same stack's running containers is reported busy too (``docker ps --filter publish=<port>``).
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import socket
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE = "docker-compose.v9.yml"

# ${VAR} ${VAR:-d} ${VAR-d} ${VAR:?e} ${VAR?e} ${VAR:+a} ${VAR+a} · $VAR · $$ (literal $).
_VAR_RE = re.compile(
    r"\$\$|\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)(?:(?P<op>:?[-?+])(?P<arg>[^}]*))?\}"
    r"|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)"
)
_KEY_LINE_RE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:(?:\s+(?P<rest>.*))?$")
_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_WIN_EADDRINUSE = 10048
_WIN_EACCES = 10013


# ── compose reader (line scanner; validated against PyYAML in the unit test) ──────────────


@dataclass
class RawPort:
    file: str
    line: int
    service: str
    spec: str | dict[str, str]
    profiles: list[str]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _scalar(raw: str) -> str:
    """A YAML scalar without its quotes or trailing comment."""
    value = raw.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end > 0:
            return value[1:end]
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _flow_items(raw: str) -> list[str]:
    """Items of an inline ``[a, "b", 'c']`` list (comment after the bracket ignored)."""
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end < start:
        return []
    body = raw[start + 1 : end]
    items = re.findall(r'"([^"]*)"|\'([^\']*)\'|([^,\s][^,]*)', body)
    return [a or b or c.strip() for a, b, c in items if (a or b or c.strip())]


def _block_items(lines: list[str], start: int) -> tuple[list[tuple[int, str | dict]], int]:
    """Read ``- item`` lines from ``start``; returns ([(lineno, scalar|mapping)], next index)."""
    items: list[tuple[int, str | dict]] = []
    i = start
    item_indent: int | None = None
    while i < len(lines):
        line = lines[i]
        if not _is_content(line):
            i += 1
            continue
        ind = _indent(line)
        body = line.strip()
        if item_indent is None:
            if not body.startswith("-"):
                break
            item_indent = ind
        if ind < item_indent or (ind == item_indent and not body.startswith("-")):
            break
        if ind > item_indent:  # continuation of a mapping item
            if items and isinstance(items[-1][1], dict):
                m = _KEY_LINE_RE.match(body)
                if m:
                    items[-1][1][m.group("key")] = _scalar(m.group("rest") or "")
            i += 1
            continue
        text = body[1:].strip()
        m = _KEY_LINE_RE.match(text)
        if m and text[:1] not in ("'", '"'):
            items.append((i + 1, {m.group("key"): _scalar(m.group("rest") or "")}))
        else:
            items.append((i + 1, _scalar(text)))
        i += 1
    return items, i


def read_ports(path: Path) -> list[RawPort]:
    """Every ``services.<name>.ports`` entry of one compose file, with its line number."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out: list[RawPort] = []
    i = 0
    while i < len(lines) and not re.match(r"^services:\s*(#.*)?$", lines[i]):
        i += 1
    i += 1
    svc_indent: int | None = None
    key_indent: int | None = None
    service: str | None = None
    pending: list[tuple[int, str | dict]] = []
    profiles: list[str] = []

    def flush() -> None:
        for lineno, spec in pending:
            out.append(RawPort(path.name, lineno, service or "?", spec, list(profiles)))

    while i < len(lines):
        line = lines[i]
        if not _is_content(line):
            i += 1
            continue
        ind = _indent(line)
        if ind == 0:
            break
        if svc_indent is None:
            svc_indent = ind
        if ind == svc_indent:
            flush()
            pending, profiles = [], []
            m = _KEY_LINE_RE.match(line.strip())
            service = m.group("key") if m else None
            key_indent = None
            i += 1
            continue
        if service is None:
            i += 1
            continue
        if key_indent is None:
            key_indent = ind
        m = _KEY_LINE_RE.match(line.strip()) if ind == key_indent else None
        if m and m.group("key") in ("ports", "profiles"):
            rest = (m.group("rest") or "").strip()
            if rest.startswith("["):
                values: list[tuple[int, str | dict]] = [(i + 1, v) for v in _flow_items(rest)]
                i += 1
            else:
                values, i = _block_items(lines, i + 1)
            if m.group("key") == "ports":
                pending.extend(values)
            else:
                profiles = [str(v) for _, v in values]
            continue
        i += 1
    flush()
    return out


# ── interpolation (Compose semantics for the forms used in ports) ─────────────────────────


def read_env_file(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if path is None or not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = _ENV_LINE_RE.match(raw)
        if not m or raw.lstrip().startswith("#"):
            continue
        value = m.group(2).strip()
        if value[:1] in ("'", '"') and value.rfind(value[0]) > 0:
            value = value[1 : value.rfind(value[0])]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[m.group(1)] = value
    return values


def interpolate(text: str, env: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """Return (expanded text, variable names referenced, errors)."""
    names: list[str] = []
    errors: list[str] = []

    def repl(m: re.Match[str]) -> str:
        if m.group(0) == "$$":
            return "$"
        name = m.group("braced") or m.group("bare")
        names.append(name)
        op, arg = m.group("op"), m.group("arg") or ""
        value = env.get(name)
        is_set, non_empty = value is not None, bool(value)
        if op == ":-":
            return value if non_empty else arg
        if op == "-":
            return value if is_set else arg
        if op in (":?", "?"):
            if (op == ":?" and not non_empty) or (op == "?" and not is_set):
                errors.append(f"{name} is required ({arg or 'no message'})")
                return ""
            return value or ""
        if op == ":+":
            return arg if non_empty else ""
        if op == "+":
            return arg if is_set else ""
        return value or ""

    return _VAR_RE.sub(repl, text), names, errors


# ── port specs ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Binding:
    file: str
    line: int
    service: str
    raw: str
    host_ip: str
    host_port: int
    protocol: str
    variables: list[str]
    profiles: list[str]
    status: str = "UNCHECKED"
    detail: str = ""
    suggestion: int | None = None
    conflicts_with: list[str] = field(default_factory=list)


def _split_fields(raw: str) -> list[str]:
    """Split ``IP:HOST:CONTAINER`` on ``:`` outside ``${...}`` and ``[...]`` (IPv6)."""
    fields: list[str] = []
    depth_brace = depth_bracket = 0
    current = ""
    i = 0
    while i < len(raw):
        ch = raw[i]
        if raw.startswith("${", i):
            depth_brace += 1
            current += "${"
            i += 2
            continue
        if ch == "}" and depth_brace:
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]" and depth_bracket:
            depth_bracket -= 1
        elif ch == ":" and not depth_brace and not depth_bracket:
            fields.append(current)
            current = ""
            i += 1
            continue
        current += ch
        i += 1
    fields.append(current)
    return fields


def _ports_of(text: str) -> list[int]:
    text = text.strip()
    if not text:
        return []
    if "-" in text:
        lo, _, hi = text.partition("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(text)]


def resolve(entry: RawPort, env: dict[str, str]) -> tuple[list[Binding], list[str]]:
    """Expand one ``ports:`` entry into concrete host bindings (empty for ephemeral ports)."""
    problems: list[str] = []
    where = f"{entry.file}:{entry.line} {entry.service}"
    if isinstance(entry.spec, dict):
        raw_text = json.dumps(entry.spec, sort_keys=True)
        published = str(entry.spec.get("published", "")).strip()
        host_ip_raw = str(entry.spec.get("host_ip", "")).strip()
        protocol_raw = str(entry.spec.get("protocol", "tcp")).strip() or "tcp"
    else:
        raw_text = entry.spec
        spec, _, protocol_raw = entry.spec.partition("/")
        protocol_raw = protocol_raw or "tcp"
        parts = _split_fields(spec)
        if len(parts) == 1:
            return [], problems  # container port only: Docker picks an ephemeral host port
        published = parts[-2]
        host_ip_raw = ":".join(parts[:-2]) if len(parts) > 2 else ""
    port_text, port_vars, errs1 = interpolate(published, env)
    ip_text, _ip_vars, errs2 = interpolate(host_ip_raw, env)
    protocol, _, errs3 = interpolate(protocol_raw, env)
    for err in errs1 + errs2 + errs3:
        problems.append(f"{where}: {err}")
    if errs1 or errs2:
        return [], problems
    ip_text = ip_text.strip().strip("[]") or "0.0.0.0"
    try:
        ports = _ports_of(port_text)
    except ValueError:
        problems.append(f"{where}: host port {port_text!r} is not a number ({raw_text})")
        return [], problems
    out = [
        Binding(
            entry.file,
            entry.line,
            entry.service,
            raw_text,
            ip_text,
            port,
            protocol.strip().lower() or "tcp",
            port_vars,
            entry.profiles,
        )
        for port in ports
    ]
    return out, problems


# ── probing ────────────────────────────────────────────────────────────────────────────────


def _privileged_limit() -> int:
    try:
        return int(
            Path("/proc/sys/net/ipv4/ip_unprivileged_port_start").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return 1024


def probe(host_ip: str, port: int, protocol: str = "tcp") -> tuple[str, str]:
    """Try to bind like the Docker daemon would. Returns (FREE|BUSY|DENIED|UNKNOWN, detail)."""
    family = socket.AF_INET6 if ":" in host_ip else socket.AF_INET
    kind = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
    try:
        sock = socket.socket(family, kind)
    except OSError as exc:
        return "UNKNOWN", f"cannot open a {protocol} socket: {exc}"
    try:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows: SO_REUSEADDR would let us share a busy port; exclusive use reports it.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif kind == socket.SOCK_STREAM:
            # Linux/macOS: same as dockerd/docker-proxy (Go sets SO_REUSEADDR); a live listener
            # still makes bind fail, a TIME_WAIT leftover does not.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host_ip, port))
        if kind == socket.SOCK_STREAM:
            sock.listen(1)
    except OSError as exc:
        codes = {exc.errno, getattr(exc, "winerror", None)}
        if codes & {errno.EADDRINUSE, _WIN_EADDRINUSE}:
            return "BUSY", "another process (or a running container) holds it"
        if codes & {errno.EACCES, _WIN_EACCES}:
            if os.name == "nt":
                return "DENIED", (
                    "access denied: usually an excluded port range reserved by winnat/Hyper-V "
                    "(netsh interface ipv4 show excludedportrange protocol=tcp)"
                )
            if port < _privileged_limit() and hasattr(os, "geteuid") and os.geteuid() != 0:
                return _connect_probe(host_ip, port, protocol)
            return "DENIED", f"access denied: {exc}"
        if errno.EADDRNOTAVAIL in codes:
            return "UNKNOWN", f"address {host_ip} is not configured on this machine"
        return "UNKNOWN", f"bind failed: {exc}"
    finally:
        sock.close()
    return "FREE", ""


def _connect_probe(host_ip: str, port: int, protocol: str) -> tuple[str, str]:
    """Privileged port probed as non-root (Linux): the daemon can bind it; see if anyone listens."""
    if protocol != "tcp":
        return "UNKNOWN", "privileged UDP port: run as root/admin to probe it"
    target = "127.0.0.1" if host_ip in ("0.0.0.0", "") else host_ip
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((target, port)) == 0:
            return "BUSY", "something already accepts connections on it"
    return "FREE", "privileged port: nothing accepts connections (bind needs root, dockerd has it)"


def suggest_port(binding: Binding, taken: set[tuple[str, int]]) -> int | None:
    """A nearby free port for the override (port+10000 first, as in ZLM_RTSP_HOST_PORT=18554)."""
    bases = [binding.host_port + 10000, binding.host_port + 20000, binding.host_port + 1]
    for base in bases:
        for candidate in range(base, base + 20):
            if not 1024 <= candidate <= 65535 or (binding.protocol, candidate) in taken:
                continue
            if probe(binding.host_ip, candidate, binding.protocol)[0] == "FREE":
                return candidate
    return None


def _overlaps(a: str, b: str) -> bool:
    wildcard = {"0.0.0.0", "::"}
    return a == b or a in wildcard or b in wildcard


def check(bindings: list[Binding]) -> None:
    """Fill status/detail/suggestion/conflicts in place."""
    for i, b in enumerate(bindings):
        for other in bindings[i + 1 :]:
            if b.service == other.service and b.file != other.file:
                continue  # an override file re-stating the same service's port merges, not clashes
            if (
                b.host_port == other.host_port
                and b.protocol == other.protocol
                and _overlaps(b.host_ip, other.host_ip)
            ):
                b.conflicts_with.append(f"{other.service} ({other.file}:{other.line})")
                other.conflicts_with.append(f"{b.service} ({b.file}:{b.line})")
    taken = {(b.protocol, b.host_port) for b in bindings}
    for b in bindings:
        b.status, b.detail = probe(b.host_ip, b.host_port, b.protocol)
        if b.conflicts_with and b.status == "FREE":
            b.status = "CONFLICT"
            b.detail = "published twice by these compose files: " + ", ".join(b.conflicts_with)
        if b.status in ("BUSY", "DENIED", "CONFLICT"):
            b.suggestion = suggest_port(b, taken)


# ── CLI ────────────────────────────────────────────────────────────────────────────────────


def _compose_files(args_files: list[str] | None) -> list[Path]:
    if args_files:
        names = args_files
    elif os.environ.get("COMPOSE_FILE"):
        names = [n for n in os.environ["COMPOSE_FILE"].split(os.pathsep) if n]
    else:
        names = [str(ROOT / DEFAULT_COMPOSE)]
    return [Path(n) if Path(n).is_absolute() else Path.cwd() / n for n in names]


def _advice(b: Binding) -> str:
    port = b.suggestion if b.suggestion is not None else "<free port>"
    if b.variables:
        return f"set {b.variables[0]}={port} in .env (or the shell) and re-run"
    return f"host port is hard-coded in {b.file}:{b.line}: free it, or add an override there"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("-f", "--file", action="append", dest="files", help="compose file")
    parser.add_argument("--env-file", help="default: .env next to the first compose file")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--verbose", action="store_true", help="also list free ports")
    args = parser.parse_args(argv)

    files = _compose_files(args.files)
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        print("compose file not found: " + ", ".join(missing), file=sys.stderr)
        return 2
    env_path = Path(args.env_file) if args.env_file else files[0].parent / ".env"
    if args.env_file and not env_path.is_file():
        print(f"env file not found: {env_path}", file=sys.stderr)
        return 2
    env = {**read_env_file(env_path), **os.environ}  # shell wins over .env, as in Compose

    bindings: list[Binding] = []
    problems: list[str] = []
    for path in files:
        for entry in read_ports(path):
            got, errs = resolve(entry, env)
            bindings.extend(got)
            problems.extend(errs)
    check(bindings)
    blocking = [b for b in bindings if b.status in ("BUSY", "DENIED", "CONFLICT")]

    if args.json:
        print(
            json.dumps(
                {
                    "files": [str(f) for f in files],
                    "env_file": str(env_path) if env_path.is_file() else None,
                    "bindings": [asdict(b) for b in bindings],
                    "problems": problems,
                    "blocking": len(blocking),
                },
                indent=2,
            )
        )
        return 1 if blocking else 0

    print(
        f"compose host-port pre-flight: {len(bindings)} host port(s) in "
        + ", ".join(f.name for f in files)
        + (f" (env: {env_path.name})" if env_path.is_file() else " (no .env found)")
    )
    for b in bindings:
        if b.status == "FREE" and not args.verbose:
            continue
        label = f"{b.host_ip}:{b.host_port}/{b.protocol}"
        profile = f" [profile: {','.join(b.profiles)}]" if b.profiles else ""
        print(f"  {b.status:<8} {label:<24} {b.service}{profile}  ({b.file}:{b.line})")
        if b.detail:
            print(f"           {b.detail}")
        if b.status in ("BUSY", "DENIED", "CONFLICT"):
            print(f"           -> {_advice(b)}")
            if b.status == "BUSY":
                print(
                    f"           who holds it: docker ps --filter publish={b.host_port}  |  "
                    f"Windows: netstat -ano | findstr :{b.host_port}  |  "
                    f"Linux: ss -ltnup 'sport = :{b.host_port}'"
                )
    for p in problems:
        print(f"  WARN     {p}")
    if blocking:
        print(f"{len(blocking)} port(s) would make `docker compose up` fail.")
        return 1
    print("all host ports can be bound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
