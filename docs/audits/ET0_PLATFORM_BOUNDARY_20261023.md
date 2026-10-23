# ET₀ platform boundary — 2026-10-23

Base: `d23b320ae6c437273a8c8a6a1ba9fc5f111b1e1c`.
Published source checkpoint: `235a972938f9f634e228dcd0627f088ca8a3d906`. Its Python and route-policy blobs match the local acceptance source recorded in the evidence manifest.

## Ownership and behavior

`services/weather-service/et0.py:168` remains the numerical owner. The calculator's JavaScript equations and its Python advisory consumer are **not** installed as another platform engine. Platform consumers use `get_et0_product` / `get_et0_series` through the existing service facade (`services/sahool-platform/api/weather_service_client.py:213`). No coefficients or regional calibration records change.

| Condition | Platform behavior |
|---|---|
| Complete, physically accepted PM inputs | Existing PM result; numerical input eligibility does not certify local calibration. |
| PM variable absent/rejected | Existing Hargreaves fallback remains explicitly degraded and advisory. |
| Elevation unknown | Existing sea-level numerical assumption remains disclosed; PM quality becomes degraded, elevation is named missing. Explicit elevation zero remains distinct. |
| Core temperature/geography absent | No numeric ET₀; missing inputs remain named. |
| Physical core inputs rejected | No numeric ET₀; rejection details survive the client and existing 422 mapping. |
| Malformed successful service response | Client fails with 502; no local formula or fabricated value. |
| Day missing or input arrays unequal | Declared day retained as `null`; daily diagnostic describes missing/rejected inputs. |
| Incomplete/empty ET₀ period | Full `accumulated_et0_mm` is `null`. `computed_et0_total_mm` is an explicitly partial subtotal, or `null` if nothing was computed. |
| Complete period whose actual values are zero | Full total remains numeric `0.0`. |

`input_completeness` measures availability of radiation, RH, wind and elevation (four PM inputs), **not** statistical accuracy. Series `coverage_status`, `missing_day_indices` and `daily_diagnostics` describe temporal coverage separately from method quality (`services/weather-service/et0.py:355`). Consumers must migrate any reliance on the former partial accumulated total to the explicitly named subtotal.

Weather ET₀ HTTP models and the platform BFF weather input models reject coercible booleans/text and nonfinite numbers before computation (`shared/weather_input_contract.py:1`). The client also validates method/quality consistency and completeness; unknown numeric ET₀ never becomes zero. The weather-log consumer withholds full ET₀ totals, annualization and ET₀-dependent deficit products when any daily ET₀ is missing, malformed or the response length differs from the input log (`services/sahool-platform/api/weather_analytics.py:75`).

Two existing adapters no longer rename maximum wind at 10 m as mean wind at 2 m. Without a documented mean the PM wind input is absent; raw cached weather cannot enable dual-Kc evaporation and its existing `dual_inputs_unavailable` limitation remains visible (`services/sahool-platform/api/field_state_projection.py:211`, `:269`; `field_irrigation_weather_snapshot` in the weather facade). This is a deliberate reduction in claimed input completeness, with no new wind conversion formula.

## Advisory and execution separation

The field recommendation route retains degraded ET₀ for display, but explicit `submit_to_decision` is blocked with `blocked_et0_advisory_only` unless the product is PM with validated inputs. The guard runs before building/persisting a manual execution specification or submitting the candidate. Full ET₀ diagnostics are retained in output and candidate provenance (`services/sahool-platform/api/weather_service_client.py:355`; `services/sahool-platform/api/routers/irrigation_recommendation.py:184`).

A qualifying PM candidate still requires explicit submission and authoritative persistence as `pending_approval`; it remains `calibrated=False`. Neither PM input acceptance nor this PR validates Yemen's regional defaults. No actuator, production database, dispatch policy or deployment is changed. This guard covers this recommendation submission boundary, not a claim of universal calibration enforcement across all platform products.

Authenticated tenant context is forwarded by the irrigation recommendation and water-balance routes. Body-supplied tenant values do not replace the authenticated user (`services/sahool-platform/api/routers/water_balance.py:33`).

## Verification and limits

- New `tests_v9/test_et0_http_platform_hop.py` serializes production client requests into the actual weather ASGI app and mounts the real water-balance router with only authentication overridden. It covers complete PM, individual/multiple omissions, invalid and missing core data, genuine zero, provenance and tenant forwarding. No equation or ET₀ response is mocked in these hop cases.
- Series, response-validation and advisory-submission regressions were observed failing before their fixes. Manual-source negative tests assert no specification write or decision submission occurs for degraded ET₀.
- The weather-service baseline was **403 passed / 1 skipped**; the service suite after the initial implementation was **444 passed / 1 skipped**. The skipped case requires live Redis.
- Local tenant-context/guard checks: **21 passed / 14 skipped**. The skipped live PostgreSQL isolation suite requires an admin test URL and a restricted-role test URL; it does **not** constitute successful live tenant isolation.
- Full preflight and generated-file convergence are reported separately in the PR on its tested head. Local success is not a claim of green remote CI.

ASGI transport verifies software HTTP contracts, not a deployed network, provider station observations, application lifespan, Redis/PostGIS integration or production irrigation. Existing consumer defaults and scalar field-state projections are not a complete per-input station provenance model. Rainfall completeness in legacy weather-log analytics and regional calibration acceptance remain separate work; this change does not certify their outputs or local agronomic accuracy.


After consolidating validation across both services and extracting HTTP/provenance helpers from the router, local acceptance checkpoint `2e5b48160f09e8e06625f3906b8a54ec20d66095` passed **926 acceptance cases / 1 Redis skip** and **24 architecture checks**. Eight unrelated environment failures were reproduced and repaired by installing local optional SOCKS support; no production dependency manifest changed. The shared validator is used by both services; no architecture baseline or ceiling was increased. The router now has 776 lines.

The shared finite-number contract (`shared/weather_input_contract.py:1`) preserves field locations with JSON-safe validation errors for both services. Rain/non-ET₀ fields and legacy defaults remain unchanged.

Local Git checkpoints in the acceptance receipt identify the actual executions. The published canonical checkpoint above has identical accepted source blobs; remote CI validates the final PR head independently.
