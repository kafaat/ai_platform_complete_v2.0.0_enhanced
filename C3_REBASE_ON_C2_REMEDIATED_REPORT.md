# C3 rebase on C2-remediated

The uploaded C2-remediated package was compared byte-for-byte with the prior C2 baseline.

## Material C2 remediation preserved
- `internal_service.py`: resolves the active season before requesting verified calibration data.
- Learning fails closed when no active season exists; it does not silently learn across seasons.
- `field_digital_twin.py`: preserves `season_id` and `as_of_time`, including ineligible states.
- C2 tests were strengthened for both properties.

## Packaging finding
The supplied remediation archive also contained hundreds of generated `__pycache__`, `.pyc`,
and `.pytest_cache` files. These are execution debris, not source remediation, and were removed
from this delivery.

## C3 reapplied
C3 precision execution changes were layered over the remediated C2 rather than over the stale C2:
yield processing, VRA lineage, prescription boundary normalization, ISOXML artifact binding,
and fail-closed machinery as-applied verification.

## Verification
125 selected C2+C3 and adjacent contracts passed, 0 failed.
