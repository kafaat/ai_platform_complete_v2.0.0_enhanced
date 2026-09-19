"""Adapt the canonical frontend routes to Railway's runtime private network.

Both literal proxy_pass targets and the named-upstream DNS fix are supported.
Route bodies, auth_request boundaries and URI replacement stay in nginx.conf.
Only the two required upstreams must be selected by the operator; optional
services can be deployed later without preventing local frontend liveness.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

SERVICE = r"sahool-[a-z0-9-]+:[0-9]+"
DIRECT_PROXY = re.compile(rf"(?m)^(\s*)proxy_pass\s+http://({SERVICE})([^;\s]*);")
UPSTREAM = re.compile(r"(?ms)^upstream ([a-zA-Z0-9_]+) \{\n(.*?)^\}")
LOCATION = re.compile(r"(?ms)^    location (?:= |\^~ |~\* )?(\S+) \{\n(.*?)^    \}")


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
    if not {"sahool-auth:8000", "sahool-platform:8000"}.issubset(services):
        raise ValueError("Canonical config is missing the expected auth/platform upstreams")
    addresses = {}
    for service in sorted(services):
        key = variable_name(service)
        host, upstream_port = service.split(":")
        default = f"{host}.railway.internal:{upstream_port}"
        addresses[service] = authority(env.get(key, default), key)

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
            f"server {addresses[service]} resolve;",
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
                f"upstream {name} {{\n    zone {name} 64k;\n"
                f"    server {addresses[service]} resolve;\n}}\n"
            )

    def location(match: re.Match) -> str:
        prefix, body = match.groups()

        def proxy(target: re.Match) -> str:
            indentation, service, uri = target.groups()
            address = addresses[service]
            result = f"{indentation}proxy_pass http://{groups[service]}{uri};"
            # Named upstreams otherwise change nginx's default redirect authority.
            if not re.search(r"\bproxy_redirect\s+", body):
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
    return resolver + "\n".join(added_groups) + "\n" + config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/opt/sahool/frontend-nginx.conf"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/railway-frontend.conf"))
    parser.add_argument("--resolv-conf", type=Path, default=Path("/etc/resolv.conf"))
    args = parser.parse_args()
    try:
        config = render(
            args.source.read_text(encoding="utf-8"), os.environ, read_nameservers(args.resolv_conf)
        )
        args.output.write_text(config, encoding="utf-8")
        args.output.chmod(0o600)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Railway frontend configuration failed: {exc}") from exc
    print("Railway frontend configuration ready")


if __name__ == "__main__":
    main()
