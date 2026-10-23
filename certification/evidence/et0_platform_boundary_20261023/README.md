# ET₀ platform boundary evidence

Pinned source and per-file hashes: [verification.json](verification.json). The source head is the implementation tested, not a claim about a later generated-file commit.

The combined command was:

```bash
python -m pytest -q services/weather-service/tests tests_v9/test_et0_http_platform_hop.py tests_v9/test_weather_analytics_engine_delegation.py tests_v9/test_fieldstate_water_canon.py tests_v9/test_etc_dual_canonical.py services/sahool-platform/tests/test_weather_et0_client.py services/sahool-platform/tests/test_field_irrigation_recommendation_endpoint.py services/sahool-platform/tests/test_manual_irrigation_source_boundary.py
```

Result: **926 passed, 1 skipped**. See [raw output](platform-et0-acceptance.txt). The skipped case needs live Redis.

Tenant guard command:

```bash
python -m pytest -q tests_v9/test_tenant_connection_call_shape.py tests_v9/test_tenant_guc_scope_guard.py tests_v9/test_rls_tenant_isolation_live_pg.py
```

Result: **21 passed, 14 skipped**. See [raw output](platform-et0-isolation.txt). PostgreSQL tests were not executed: no admin/restricted-role test URLs were supplied. This is not live tenant-isolation certification.

Existing pinned weather-service, platform API and tests_v9 requirements were installed in a local Python 3.12 virtual environment; dependency manifests were not changed. No deployed environment, external provider, production database or actuator was exercised. Full preflight and remote CI results belong to their own runs.

The final source uses one pure Pydantic input validator in `shared/weather_input_contract.py` for both weather HTTP models and platform BFF models. Router HTTP mapping/provenance moved into the existing weather facade; shrink/module/router baselines were not increased. Additional results: [24 architecture checks](architecture-repaired.txt), [5 ERP cases](erp-environment-rerun.txt), [3 MCP/seed/retrieval cases](mcp-ollama-environment-rerun.txt). The latter eight originally failed because local HTTPX inherited a SOCKS proxy without `socksio`; installing its local optional extra fixed them without production code or manifest changes.

Published canonical source: `235a972938f9f634e228dcd0627f088ca8a3d906`. `verification.json` preserves the actual local execution checkpoints and verifies all accepted Python/route-policy Git blobs against this canonical source. Remote CI belongs to the final PR head.

The final local default preflight completed with **0 failed / 0 skipped gates**, including generated convergence and all three test suites. Raw output: [full-preflight.txt](full-preflight.txt). Live test skips are distinct from skipped gates.
