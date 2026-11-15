"""Decode jsonb values read through asyncpg.

asyncpg returns ``jsonb`` as ``str`` unless a codec is registered on the connection, and this
service registers none: every write passes an already-serialised ``json.dumps(...)`` string to
a ``$n::jsonb`` parameter, so a pool-wide codec would double-encode those writes. Reads are
therefore decoded here, at the store boundary. ``dict(row["payload"])`` on the raw string raised
``ValueError`` (500 on most P1/P2/P3 endpoints, ``/hydraulic-profile/rebuild`` always), and
observation values reached the composed profile as the string ``"7.2"`` instead of ``7.2``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

OBSERVATION_JSONB_COLUMNS = ("value_json", "quality_flags", "provenance")


def decode_jsonb(value: Any) -> Any:
    """``str``/``bytes`` from asyncpg ⇒ the JSON value; anything else is already decoded."""
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


def decode_jsonb_object(value: Any) -> dict[str, Any] | None:
    """A jsonb column that must hold an object: ``None`` stays ``None``, anything else fails."""
    decoded = decode_jsonb(value)
    if decoded is None:
        return None
    if not isinstance(decoded, Mapping):
        raise TypeError(f"expected a jsonb object, got {type(decoded).__name__}")
    return dict(decoded)


def decode_observation_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """A ``soil_observations`` row as a dict with its jsonb columns decoded."""
    out = dict(row)
    for column in OBSERVATION_JSONB_COLUMNS:
        if column in out:
            out[column] = decode_jsonb(out[column])
    return out
