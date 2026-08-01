"""SAHOOL Indicators Service package.

Contains the indicator ownership contract, the indicator catalog surface, and
the runtime support that serves them.

Package presence does not by itself imply production certification; runtime
status is determined by the repository's health, readiness, and evidence gates.

WEATHER-SERVICE-STUB-DOCSTRING-DRIFT: this file carried the **same sentence,
verbatim**, as ``services/weather-service/__init__.py`` — "empty stub ... no
logic". One description written once and copy-pasted, false in two services. It
was found not by inspection but by generalising the fix into a guard, which is
why the rule matters more than either edit.

Its counterpart guard applies here too:
``scripts/ci/indicators_container_contract_guard.py`` requires an explicit 409
and rejects 501 / ``implemented_runtime: False`` — enforcing that the service is
implemented while this text claimed it was empty.

``"spectral_compute": False`` is **not** "no logic": this service does not
compute spectral values **by design**, because that ownership belongs to
raster-service under ``shared/contracts/indicator_ownership.json``. It is an
ownership boundary, not an absence of implementation — reading it as emptiness
would repeat the original error in a new form.

Enforced repo-wide by ``tests_v9/test_service_stub_claim_truth.py``.
"""
