from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

MAX_CLOCK_SKEW = timedelta(minutes=5)


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        validate_default=True,
    )
