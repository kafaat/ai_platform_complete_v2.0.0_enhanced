"""Validation shared by the budget and revenue writes in the farm ledger."""

from math import isfinite
from typing import Annotated

from fastapi import HTTPException
from pydantic import Field, ValidationError, WrapValidator

LedgerNumber = Annotated[float, Field(ge=0, allow_inf_nan=False)]


def checked_ledger_amount(
    amount: float, quantity: float | None, price: float | None, field: str
) -> float:
    """An explicit nonzero amount takes precedence; zero derives it when both factors exist."""
    if amount or quantity is None or price is None:
        return amount
    product = quantity * price
    if not isfinite(product):
        raise ValueError(f"{field} must be finite")
    return product


def _validate_finance_request(value, handler):
    try:
        return handler(value)
    except ValidationError as exc:
        # An invalid input or context may itself contain NaN/Infinity that JSON cannot encode.
        details = exc.errors(include_input=False, include_context=False, include_url=False)
        for detail in details:
            detail["loc"] = ("body", *detail["loc"])
        raise HTTPException(status_code=422, detail=details) from exc


finance_request_errors = WrapValidator(_validate_finance_request)
