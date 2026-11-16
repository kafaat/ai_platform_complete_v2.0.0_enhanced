"""Which service-to-service tokens a service has configured, never their values (W3-12).

A missing token does not stop these services from starting: the endpoint that needs it answers
503 at request time (the field-task verification callback, scouting media). /readyz reports the
booleans so an operator sees the gap before a caller does; the production compose preflight
refuses to start without them.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def service_token_status(names: Iterable[str]) -> dict[str, bool]:
    """``{name: configured}`` for each env var; the same non-empty test the endpoints apply."""
    return {name: bool(os.getenv(name)) for name in names}
