"""Resolve named single-server upstreams for existing endpoint contract checks.

The live nginx suite checks DNS and request handling. This helper lets the
existing static contracts keep checking canonical service names and URI suffixes
after proxy_pass is wired through named upstreams.
"""

from __future__ import annotations

import re


def expand_upstream_targets(conf: str) -> str:
    uncommented = re.sub(r"#[^\n]*", "", conf)
    targets = {}
    for name, body in re.findall(r"upstream\s+(\w+)\s*\{([^{}]*)\}", uncommented):
        servers = re.findall(r"\bserver\s+([^\s;]+)[^;]*;", body)
        assert len(servers) == 1, f"{name}: expected exactly one service binding"
        targets[name] = servers[0]

    def expand(match: re.Match[str]) -> str:
        prefix, host = match.groups()
        if host.startswith("frontend_"):
            assert host in targets, f"undeclared frontend upstream: {host}"
        return prefix + targets.get(host, host)

    return re.sub(r"(\bproxy_pass\s+http://)([\w.:-]+)(?=[/;])", expand, conf)
