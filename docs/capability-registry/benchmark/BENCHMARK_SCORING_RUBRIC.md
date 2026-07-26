# Capability Benchmark Scoring Rubric v1.0

This rubric separates an official product claim from the analyst score derived from that claim.
An official URL is evidence that a feature is described by the vendor; it is not an official vendor-issued maturity score.

| Score | Benchmark meaning |
|---:|---|
| 0 | Confirmed absent or no usable capability |
| 1 | Informational or isolated display |
| 2 | Analytical output without an operational workflow |
| 3 | Operational workflow documented by an official source |
| 4 | Integrated or closed workflow across data, action, export, synchronization, or execution monitoring |
| 5 | Closed learning loop with measured outcome feedback and governed adaptation |

## Evidence rules

- Only `comparison_scope=direct` rows with a canonical capability ID may create a competitor score.
- Adjacent capabilities are retained as evidence but cannot affect parity. ETa is not ET0, scouting is not work orders, and satellite crop monitoring is not scene search.
- Scores are provisional analyst assessments. Confidence is recorded separately.
- Duplicate evidence for the same platform and capability must agree on the score.
- Missing evidence remains `Unassessed`; no repository maturity is substituted for competitor evidence.
- Runtime verification and production certification are always separate from benchmark parity.
