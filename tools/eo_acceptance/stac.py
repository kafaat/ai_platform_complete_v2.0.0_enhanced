"""Uncached STAC comparison. Never changes SAHOOL provider configuration."""

from __future__ import annotations

import time
from collections import deque
from urllib.parse import urljoin, urlsplit


class Limiter:
    """One shared rolling-window limiter for both endpoints, including retries."""

    def __init__(self, authenticated=False, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.minute_limit = 240 if authenticated else 60
        self.calls = deque()

    def acquire(self):
        while True:
            now = self.clock()
            while self.calls and now - self.calls[0] >= 60:
                self.calls.popleft()
            recent = [t for t in self.calls if now - t < 1]
            waits = [0.0]
            if len(recent) >= 10:
                waits.append(1 - (now - recent[0]))
            if len(self.calls) >= self.minute_limit:
                waits.append(60 - (now - self.calls[0]))
            delay = max(waits)
            if delay <= 0:
                self.calls.append(now)
                return
            self.sleep(delay)


def crawl(client, endpoint, payload, limiter, token=None, max_pages=10000):
    """Fail on incomplete/cyclic pagination, duplicate identities or unsafe links.

    STAC POST next bodies replace the original unless merge=true. GET links use
    their full query string. Tokens are sent only to the original origin.
    """
    origin = urlsplit(endpoint)
    url, method, body = endpoint.rstrip("/") + "/search", "POST", payload
    seen, items, requests, throttles = set(), {}, 0, 0
    matched = None
    start = time.perf_counter()
    for _ in range(max_pages):
        import json

        signature = (method, url, json.dumps(body, sort_keys=True))
        if signature in seen:
            raise ValueError("pagination cycle")
        seen.add(signature)
        for _attempt in range(4):
            limiter.acquire()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = client.request(
                method,
                url,
                json=body if method == "POST" else None,
                headers=headers,
                follow_redirects=False,
            )
            requests += 1
            if response.status_code != 429:
                break
            throttles += 1
            # A bounded numeric Retry-After; limiter still accounts for retry.
            try:
                delay = float(response.headers.get("Retry-After", 1))
            except ValueError:
                delay = 1
            if not 0 <= delay <= 60:
                raise ValueError("Retry-After outside test budget")
            limiter.sleep(delay)
        response.raise_for_status()
        page = response.json()
        if page.get("type") != "FeatureCollection" or not isinstance(page.get("features"), list):
            raise ValueError("invalid STAC page")
        declared = page.get("numberMatched", page.get("context", {}).get("matched"))
        if isinstance(declared, int) and not isinstance(declared, bool):
            if matched is not None and matched != declared:
                raise ValueError("catalogue size changed during pagination")
            matched = declared
        returned = page.get("numberReturned")
        if returned is not None and returned != len(page["features"]):
            raise ValueError("returned count disagrees with page")
        for item in page["features"]:
            identity = (item["collection"], item["id"])
            if identity in items:
                raise ValueError("duplicate STAC identity across pages")
            items[identity] = item
        links = [link for link in page.get("links", []) if link.get("rel") == "next"]
        if not links:
            if matched is not None and matched != len(items):
                raise ValueError("missing pages: matched count differs from collected identities")
            return items, {
                "seconds": time.perf_counter() - start,
                "requests": requests,
                "429": throttles,
                "pages": len(seen),
            }
        if len(links) != 1:
            raise ValueError("ambiguous next link")
        link = links[0]
        url = urljoin(url, link["href"])
        parsed = urlsplit(url)
        if (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
            raise ValueError("cross-origin next link")
        method = link.get("method", "GET").upper()
        if method not in {"GET", "POST"}:
            raise ValueError("unsupported pagination method")
        next_body = link.get("body", {})
        body = {**(body or {}), **next_body} if link.get("merge") else next_body
    raise ValueError("pagination budget exhausted; result incomplete")


def compare(old, new):
    """URLs may legitimately differ; expose metadata deltas for review."""

    def fingerprint(item):
        return {
            "datetime": item.get("properties", {}).get("datetime"),
            "assets": {
                k: {p: a.get(p) for p in ("type", "roles", "raster:bands", "eo:bands")}
                for k, a in item.get("assets", {}).items()
            },
        }

    common = old.keys() & new.keys()
    changed = [list(k) for k in sorted(common) if fingerprint(old[k]) != fingerprint(new[k])]
    return {
        "old_count": len(old),
        "new_count": len(new),
        "old_only": [list(k) for k in sorted(old.keys() - new.keys())],
        "new_only": [list(k) for k in sorted(new.keys() - old.keys())],
        "metadata_changed": changed,
        "correctness_pass": bool(common) and old.keys() == new.keys() and not changed,
    }
