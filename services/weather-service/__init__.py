"""SAHOOL Weather Service package.

Contains the weather API, provider adapters, canonical weather composition,
agrometeorological calculations, caching, observability, and runtime support.

Package presence does not by itself imply production certification; runtime
status is determined by the repository's health, readiness, and evidence gates.

WEATHER-SERVICE-STUB-DOCSTRING-DRIFT: this file previously described the service
as an "empty stub ... registered in docker-compose but with no logic". That was
true when written and later became false, while
``scripts/ci/weather_service_real_contract_gate.py`` enforced the opposite —
rejecting 501 and ``implemented_runtime: False``. A live guard contradicting a
stale description is worse than no description: a reader trusts the text and
acts on it (merge/delete the service) against what the tree actually says.

The replacement states scope, not size, and makes no certification claim: counts
rot exactly the way the original claim did, and certified status is the gates'
call rather than this file's. Enforced repo-wide by
``tests_v9/test_service_stub_claim_truth.py``.

Whether this service's output is actually consumed in the canonical state is a
separate wiring question (CANONICAL-WEATHER-CONSUMPTION) and is not implied by
the package being implemented.
"""
