"""Adapt the canonical frontend routes to Railway's runtime private network.

Both literal proxy_pass targets and the named-upstream DNS fix are supported.
Route bodies, auth_request boundaries and URI replacement stay in nginx.conf.
Only the two required upstreams must be selected by the operator; optional
services can be deployed later without preventing local frontend liveness.

An optional service that has no Railway service at all can be declared
``SAHOOL_<SERVICE>_UPSTREAM=absent``. Measured on staging (2026-09-29): three
undeployed hosts made nginx log "could not be resolved" every 10 s each, burying
real errors, and their routes answered an opaque 502. An absent service is
routed to a local stub that answers 503 ``service_not_deployed`` with no DNS
lookup. It is an explicit declaration, never inferred from a failed lookup, so a
service deployed later still needs only its variable removed.

Dedicated service tokens (W0-09) appear in the canonical config as ``@NAME@``
placeholders, never as ``${NAME}`` (nginx would read that as an unknown variable
and refuse to start the unrendered development image). Each is filled from the
environment variable of the same name. An unset token renders as an empty header
value, which the owning service refuses (fail closed, the route answers 401/503
instead of reaching data). A token of an absent service is never written into
the config. A value outside a conservative token alphabet is refused, since it
would otherwise be pasted into an nginx string. A placeholder this adapter does
not know is refused too, so a new one cannot reach a backend as a literal.

It also stamps the deployment into ``/build-info.json`` (written at build time by
``frontend/scripts/write-build-info.mjs``). Railway gives ``RAILWAY_DEPLOYMENT_ID``
only at runtime (the build logs show it empty), and an image Railway reuses
without rebuilding keeps the old build-time value, so ``build_id`` is set here at
container start: ``railway-<deployment id>``. Only that key changes; ``git_sha``
stays the build-time value. Without a valid id the build-time value is kept. This
step never stops nginx from starting: a missing or unreadable file is reported
and left alone.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

SERVICE = r"sahool-[a-z0-9-]+:[0-9]+"
ABSENT = "absent"
ABSENT_SOCKET = "/tmp/sahool-absent-upstream.sock"
REQUIRED = ("sahool-auth:8000", "sahool-platform:8000")
DIRECT_PROXY = re.compile(rf"(?m)^(\s*)proxy_pass\s+http://({SERVICE})([^;\s]*);")
UPSTREAM = re.compile(r"(?ms)^upstream ([a-zA-Z0-9_]+) \{\n(.*?)^\}")
LOCATION = re.compile(r"(?ms)^    location (?:= |\^~ |~\* |~ )?(\S+) \{\n(.*?)^    \}")
# Placeholder -> (environment variable, the service that verifies the token).
TOKENS = {
    "@SCOUT_MEDIA_SERVICE_TOKEN@": ("SCOUT_MEDIA_SERVICE_TOKEN", "sahool-scout-ingest:8000"),
    "@SEASON_ENTRY_SERVICE_TOKEN@": ("SEASON_ENTRY_SERVICE_TOKEN", "sahool-scout-ingest:8000"),
    "@FIELD_TASKS_SERVICE_TOKEN@": ("FIELD_TASKS_SERVICE_TOKEN", "sahool-field-management:8000"),
}
TOKEN_PLACEHOLDER = re.compile(r"@[A-Z][A-Z0-9_]*_TOKEN@")
TOKEN_VALUE = re.compile(r"[A-Za-z0-9._~+/=-]{1,512}")


def variable_name(service: str) -> str:
    return service.split(":", 1)[0].upper().replace("-", "_") + "_UPSTREAM"


def authority(value: str, key: str) -> str:
    """Accept a host and port, never a URI or nginx configuration fragment."""
    match = re.fullmatch(
        r"(\[[0-9a-fA-F:]+\]|[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?):([0-9]+)", value
    )
    if not match or not 1 <= int(match[2]) <= 65535:
        raise ValueError(f"{key} must be a host:port address")
    if match[1].startswith("["):
        ipaddress.IPv6Address(match[1][1:-1])
    elif ".." in match[1]:
        raise ValueError(f"{key} contains an invalid host")
    return value


def fill_tokens(config: str, env: Mapping[str, str], absent: set[str]) -> str:
    """Replace each known token placeholder; refuse unknown placeholders and unsafe values."""
    for placeholder, (key, service) in TOKENS.items():
        if placeholder not in config:
            continue
        value = "" if service in absent else env.get(key, "")
        if value and not TOKEN_VALUE.fullmatch(value):
            raise ValueError(f"{key} contains characters outside the token alphabet")
        config = config.replace(placeholder, value)
    leftover = TOKEN_PLACEHOLDER.search(config)
    if leftover:
        raise ValueError(f"Unknown service token placeholder {leftover[0]}")
    return config


def unset_tokens(source: str, env: Mapping[str, str]) -> list[str]:
    """Names of tokens the config uses whose service is present but whose value is unset."""
    names = set()
    for placeholder, (key, service) in TOKENS.items():
        if placeholder in source and env.get(variable_name(service)) != ABSENT:
            if not env.get(key):
                names.add(key)
    return sorted(names)


def read_nameservers(path: Path) -> list[str]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "nameserver":
            address = ipaddress.ip_address(words[1])
            result.append(f"[{address}]" if address.version == 6 else str(address))
    if not result:
        raise ValueError("No nameservers in resolver configuration")
    return result


def render(source: str, env: Mapping[str, str], nameservers: Sequence[str]) -> str:
    # Resolver values come from resolv.conf; tests may append a DNS fixture port.
    if not nameservers:
        raise ValueError("At least one DNS resolver is required")
    for item in nameservers:
        if not re.fullmatch(r"(?:[0-9.]+|\[[0-9a-fA-F:]+\])(?::[0-9]+)?", item):
            raise ValueError("Invalid DNS resolver address")
    port = env.get("PORT", "8080")
    if not re.fullmatch(r"[0-9]+", port) or not 1024 <= int(port) <= 65535:
        raise ValueError("PORT must be between 1024 and 65535 for non-root nginx")
    ipv6 = env.get("SAHOOL_DNS_IPV6", "off")
    if ipv6 not in {"on", "off"}:
        raise ValueError("SAHOOL_DNS_IPV6 must be on or off")
    for key in ("SAHOOL_AUTH_UPSTREAM", "SAHOOL_PLATFORM_UPSTREAM"):
        if not env.get(key):
            raise ValueError(f"{key} must explicitly select the deployed service")

    services = set(re.findall(rf"(?:proxy_pass\s+http://|server\s+)({SERVICE})", source))
    if not set(REQUIRED).issubset(services):
        raise ValueError("Canonical config is missing the expected auth/platform upstreams")
    addresses = {}
    absent = set()
    for service in sorted(services):
        key = variable_name(service)
        host, upstream_port = service.split(":")
        default = f"{host}.railway.internal:{upstream_port}"
        value = env.get(key, default)
        if value == ABSENT:
            if service in REQUIRED:
                raise ValueError(f"{key} cannot be absent: the frontend requires it")
            absent.add(service)
            value = default  # proxy_redirect/Host text only; the stub answers
        addresses[service] = authority(value, key)

    def server_line(service: str) -> str:
        if service in absent:
            return f"server unix:{ABSENT_SOCKET};"
        return f"server {addresses[service]} resolve;"

    # Remove the Docker-only resolver if the canonical runtime DNS fix is present.
    config = re.sub(r"(?m)^resolver(?:_timeout)?\s+[^;]+;\n", "", source)
    groups = {}

    def existing_upstream(match: re.Match) -> str:
        name, body = match.groups()
        servers = re.findall(rf"(?m)^\s*server\s+({SERVICE})(?:\s+resolve)?;", body)
        if len(servers) != 1:
            raise ValueError(f"Unsupported canonical upstream shape: {name}")
        service = servers[0]
        groups[service] = name
        body = re.sub(
            rf"server\s+{re.escape(service)}(?:\s+resolve)?;",
            server_line(service),
            body,
        )
        if not re.search(r"\bzone\s+", body):
            body = f"    zone {name} 64k;\n" + body
        return f"upstream {name} {{\n{body}}}"

    config = UPSTREAM.sub(existing_upstream, config)
    added_groups = []
    for service in sorted(services):
        if service not in groups:
            name = "railway_" + service.split(":")[0].replace("-", "_")
            groups[service] = name
            added_groups.append(
                f"upstream {name} {{\n    zone {name} 64k;\n    {server_line(service)}\n}}\n"
            )

    def location(match: re.Match) -> str:
        prefix, body = match.groups()

        def proxy(target: re.Match) -> str:
            indentation, service, uri = target.groups()
            address = addresses[service]
            result = f"{indentation}proxy_pass http://{groups[service]}{uri};"
            # Named upstreams otherwise change nginx's default redirect authority. A target
            # built from variables has no default redirect to preserve, so none is added.
            if "$" not in uri and not re.search(r"\bproxy_redirect\s+", body):
                result += f"\n        proxy_redirect http://{address}{uri or '/'} {prefix if uri else '/'};"
            if not re.search(r"\bproxy_set_header\s+Host\s+", body):
                result += f"\n        proxy_set_header Host {address};"
            return result

        updated = DIRECT_PROXY.sub(proxy, body)
        return match[0].replace(body, updated, 1)

    config = LOCATION.sub(location, config)
    if DIRECT_PROXY.search(config):
        raise ValueError("Unconverted proxy target in canonical config")
    # The named-upstream version already has explicit redirects and auth Host.
    for service, address in addresses.items():
        config = re.sub(re.escape(service) + r"(?=[/;\s])", address, config)
    for original, replacement in (
        ("listen 8080;", f"listen {port};"),
        ("listen [::]:8080;", f"listen [::]:{port};"),
    ):
        if config.count(original) != 1:
            raise ValueError("Canonical frontend listener contract changed")
        config = config.replace(original, replacement)
    resolver = f"resolver {' '.join(nameservers)} valid=10s ipv6={ipv6};\nresolver_timeout 5s;\n"
    stub = ""
    if absent:
        names = ", ".join(sorted(s.split(":")[0] for s in absent))
        stub = (
            f"# Declared absent on this deployment: {names}\n"
            f"server {{\n    listen unix:{ABSENT_SOCKET};\n"
            "    default_type application/json;\n"
            '    return 503 \'{"error":"service_not_deployed"}\';\n}\n'
        )
    config = fill_tokens(config, env, absent)
    return resolver + "\n".join(added_groups) + "\n" + stub + config


BUILD_INFO = Path("/usr/share/nginx/html/build-info.json")
# Same safe pattern as write-build-info.mjs and the platform's build id.
BUILD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def stamp_build_id(path: Path, env: Mapping[str, str]) -> str:
    """Set build_id to the runtime Railway deployment; return what happened."""
    deployment = env.get("RAILWAY_DEPLOYMENT_ID", "").strip()
    build_id = f"railway-{deployment}"
    if not deployment or not BUILD_ID.fullmatch(build_id):
        return "kept the build-time build_id (no valid RAILWAY_DEPLOYMENT_ID)"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(info, dict):
            raise ValueError("not a JSON object")
        info["build_id"] = build_id
        # Rewritten in place: only this file is writable by the nginx user, not the web root.
        path.write_text(json.dumps(info, separators=(",", ":")) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        return f"left build-info.json unchanged ({type(exc).__name__})"
    return f"stamped build_id={build_id}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/opt/sahool/frontend-nginx.conf"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/railway-frontend.conf"))
    parser.add_argument("--resolv-conf", type=Path, default=Path("/etc/resolv.conf"))
    parser.add_argument("--build-info", type=Path, default=BUILD_INFO)
    args = parser.parse_args()
    try:
        source = args.source.read_text(encoding="utf-8")
        config = render(source, os.environ, read_nameservers(args.resolv_conf))
        args.output.write_text(config, encoding="utf-8")
        args.output.chmod(0o600)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Railway frontend configuration failed: {exc}") from exc
    for key in unset_tokens(source, os.environ):
        # Names only, never values. The owning service refuses the empty token.
        print(f"Railway frontend: {key} is unset; its routes will be refused upstream")
    print(f"Railway frontend: {stamp_build_id(args.build_info, os.environ)}")
    print("Railway frontend configuration ready")


if __name__ == "__main__":
    main()
