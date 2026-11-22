"""Pick the ``location`` nginx would choose for a request path, and the upstream URI.

Static model of nginx's selection order for the server that owns the ``/api`` surface:
exact (``=``) first, then the longest plain/``^~`` prefix (``^~`` stops the regex pass),
then regexes in file order, then the remembered prefix. Only what the gateway contracts
need: top-level locations, ``proxy_pass`` to a named single-server upstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from _nginx_contract import expand_upstream_targets

_HEADER = re.compile(r"(?m)^[ \t]*location\s+((?:=|\^~|~\*|~)\s+)?(\S+)\s*\{")
_PASS = re.compile(r"\bproxy_pass\s+http://([\w.:-]+)(/[^\s;]*)?;")


@dataclass(frozen=True)
class Location:
    modifier: str
    path: str
    body: str

    @property
    def key(self) -> str:
        return f"{self.modifier} {self.path}".strip()


def locations(conf: str) -> list[Location]:
    text = re.sub(r"(?m)#[^\n]*", "", expand_upstream_targets(conf))
    found = []
    for match in _HEADER.finditer(text):
        depth, start = 0, text.index("{", match.start())
        for index in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[index], 0)
            if depth == 0:
                found.append(Location((match[1] or "").strip(), match[2], text[start + 1 : index]))
                break
        else:
            raise AssertionError(f"unbalanced braces after location {match[2]}")
    return found


def resolve(conf: str, path: str) -> Location:
    """The location serving ``path`` (no query string)."""
    blocks = locations(conf)
    for block in blocks:
        if block.modifier == "=" and block.path == path:
            return block
    prefixes = [b for b in blocks if b.modifier in {"", "^~"} and path.startswith(b.path)]
    longest = max(prefixes, key=lambda b: len(b.path), default=None)
    if longest is not None and longest.modifier == "^~":
        return longest
    for block in blocks:
        if block.modifier in {"~", "~*"}:
            flags = re.IGNORECASE if block.modifier == "~*" else 0
            if re.search(block.path, path, flags):
                return block
    assert longest is not None, f"no location serves {path}"
    return longest


def upstream(block: Location, path: str) -> tuple[str, str]:
    """``(host:port, uri)`` the block proxies ``path`` to."""
    target = _PASS.search(block.body)
    assert target, f"location {block.key} has no proxy_pass to an upstream"
    host, uri = target[1], target[2]
    if uri is None:
        return host, path
    if block.modifier == "=":
        return host, uri
    assert block.modifier in {"", "^~"}, f"{block.key}: URI rewrite on a regex location"
    return host, uri + path[len(block.path) :]
