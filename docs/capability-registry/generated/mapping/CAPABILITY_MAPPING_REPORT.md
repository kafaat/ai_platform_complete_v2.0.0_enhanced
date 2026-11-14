# Capability Mapping — Raw Scanner Candidates (NOT authoritative)

> Raw static repository scan only. `mapped` here means the scanner found specific
> implementation-dimension evidence (backend/routes/db/events/web/mobile/tests) — an honest
> LOWER BOUND. The AUTHORITATIVE mapped/unmapped state is the management matrix
> (`docs/capability-registry/generated/management/coverage_dashboard.json`), which also
> credits registry-declared on-disk evidence this scanner cannot attribute. `governance` and
> `other_evidence` are reported but never promote a capability. This report does not assert
> runtime verification or production certification.

- Capabilities: **81**
- Mapped: **77**
- Unmapped: **4**
- Multi-dimensional mappings: **43**
- Files scanned: **7347**
- Ambiguous artifacts queued: **239**
- Unmapped artifacts queued: **3491**

## Capability coverage

| ID | Domain | Backend | Routes | DB | Events | Web | Mobile | Tests | Dimensions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DEC-001 | decision | 2 | 0 | 0 | 3 | 0 | 0 | 3 | 3 |
| DEC-002 | decision | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| DEC-003 | decision | 2 | 0 | 0 | 0 | 0 | 0 | 3 | 2 |
| DEC-004 | decision | 6 | 4 | 16 | 4 | 0 | 0 | 8 | 5 |
| DEC-005 | decision | 0 | 0 | 10 | 1 | 0 | 0 | 2 | 3 |
| DEC-006 | decision | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| DEC-007 | decision | 4 | 8 | 4 | 3 | 1 | 0 | 4 | 6 |
| DEC-008 | decision | 0 | 1 | 2 | 1 | 0 | 0 | 1 | 4 |
| DEC-009 | decision | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| DEC-010 | decision | 4 | 93 | 49 | 7 | 0 | 0 | 7 | 5 |
| FM-001 | farm_management | 16 | 2 | 28 | 12 | 1 | 0 | 43 | 6 |
| FM-002 | farm_management | 36 | 44 | 100 | 26 | 19 | 35 | 52 | 7 |
| FM-003 | farm_management | 14 | 56 | 5 | 65 | 3 | 2 | 16 | 7 |
| FM-004 | farm_management | 32 | 82 | 84 | 43 | 18 | 15 | 55 | 7 |
| FM-005 | farm_management | 10 | 0 | 0 | 8 | 6 | 1 | 8 | 5 |
| FM-006 | farm_management | 1 | 0 | 0 | 0 | 2 | 0 | 1 | 3 |
| FM-007 | farm_management | 8 | 19 | 8 | 0 | 1 | 4 | 6 | 6 |
| FM-008 | farm_management | 10 | 31 | 5 | 2 | 0 | 0 | 11 | 5 |
| GIS-001 | gis | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |
| GIS-002 | gis | 2 | 4 | 0 | 0 | 4 | 0 | 2 | 4 |
| GIS-003 | gis | 33 | 100 | 16 | 67 | 13 | 4 | 43 | 7 |
| GIS-004 | gis | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 3 |
| INT-001 | farm_management | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 2 |
| INT-002 | farm_management | 7 | 15 | 2 | 100 | 0 | 0 | 22 | 5 |
| INT-003 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 1 |
| INT-004 | precision | 5 | 9 | 8 | 12 | 0 | 0 | 3 | 5 |
| IRR-001 | irrigation | 0 | 0 | 8 | 0 | 0 | 0 | 1 | 2 |
| IRR-002 | irrigation | 1 | 6 | 8 | 1 | 0 | 0 | 2 | 5 |
| IRR-003 | irrigation | 1 | 0 | 4 | 0 | 0 | 0 | 3 | 3 |
| IRR-004 | irrigation | 3 | 1 | 0 | 0 | 0 | 0 | 2 | 3 |
| IRR-005 | irrigation | 2 | 2 | 0 | 7 | 0 | 0 | 5 | 4 |
| IRR-006 | irrigation | 0 | 0 | 0 | 4 | 0 | 0 | 4 | 2 |
| IRR-007 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-008 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-009 | irrigation | 8 | 1 | 7 | 9 | 2 | 0 | 13 | 6 |
| IRR-010 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-001 | operations | 0 | 0 | 7 | 6 | 0 | 1 | 1 | 4 |
| OPS-002 | operations | 3 | 7 | 6 | 3 | 1 | 0 | 7 | 6 |
| OPS-003 | operations | 5 | 13 | 19 | 8 | 6 | 17 | 17 | 7 |
| OPS-004 | operations | 3 | 12 | 14 | 12 | 0 | 21 | 28 | 6 |
| OPS-005 | operations | 2 | 2 | 9 | 14 | 1 | 13 | 12 | 7 |
| OPS-006 | operations | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| OPS-007 | operations | 0 | 0 | 3 | 0 | 0 | 1 | 0 | 2 |
| OPS-008 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PA-001 | precision | 10 | 34 | 8 | 2 | 1 | 0 | 11 | 6 |
| PA-002 | precision | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| PA-003 | precision | 4 | 4 | 12 | 1 | 0 | 0 | 5 | 5 |
| PA-004 | precision | 1 | 0 | 18 | 2 | 0 | 0 | 1 | 4 |
| PA-005 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| SAT-001 | satellite | 42 | 100 | 5 | 43 | 6 | 0 | 59 | 6 |
| SAT-002 | satellite | 0 | 1 | 0 | 1 | 1 | 0 | 5 | 4 |
| SAT-003 | satellite | 59 | 43 | 6 | 97 | 38 | 5 | 65 | 7 |
| SAT-004 | satellite | 9 | 4 | 5 | 13 | 3 | 0 | 8 | 6 |
| SAT-005 | satellite | 6 | 6 | 0 | 1 | 0 | 0 | 14 | 4 |
| SAT-006 | satellite | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 3 |
| SAT-007 | satellite | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 3 |
| SAT-008 | satellite | 3 | 1 | 7 | 4 | 0 | 0 | 6 | 5 |
| SAT-009 | satellite | 12 | 52 | 0 | 15 | 2 | 1 | 28 | 6 |
| SEC-001 | security | 12 | 16 | 100 | 75 | 0 | 0 | 86 | 5 |
| SEC-002 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-003 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-004 | security | 6 | 9 | 19 | 1 | 5 | 4 | 13 | 7 |
| SEC-005 | security | 0 | 0 | 4 | 0 | 0 | 0 | 3 | 2 |
| SEC-006 | security | 3 | 86 | 0 | 3 | 0 | 0 | 11 | 4 |
| SEC-007 | security | 3 | 74 | 7 | 47 | 0 | 0 | 9 | 5 |
| SEC-008 | security | 0 | 0 | 4 | 2 | 0 | 0 | 10 | 3 |
| SOIL-001 | soil | 6 | 2 | 14 | 22 | 0 | 0 | 5 | 5 |
| SOIL-002 | soil | 14 | 32 | 13 | 9 | 2 | 0 | 9 | 6 |
| SOIL-003 | soil | 3 | 3 | 15 | 0 | 0 | 1 | 0 | 4 |
| SOIL-004 | soil | 1 | 0 | 7 | 3 | 0 | 0 | 0 | 3 |
| SOIL-005 | soil | 7 | 0 | 0 | 8 | 0 | 0 | 1 | 3 |
| WX-001 | weather | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| WX-002 | weather | 13 | 21 | 6 | 31 | 8 | 1 | 13 | 7 |
| WX-003 | weather | 2 | 6 | 4 | 0 | 0 | 0 | 0 | 3 |
| WX-004 | weather | 3 | 0 | 0 | 1 | 0 | 0 | 9 | 3 |
| WX-005 | weather | 3 | 0 | 0 | 1 | 0 | 0 | 2 | 3 |
| WX-006 | weather | 6 | 1 | 0 | 1 | 0 | 0 | 11 | 4 |
| WX-007 | weather | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| WX-008 | weather | 3 | 6 | 0 | 5 | 0 | 1 | 2 | 5 |
| WX-009 | weather | 1 | 29 | 0 | 0 | 2 | 0 | 2 | 4 |
| WX-010 | weather | 1 | 0 | 0 | 2 | 0 | 0 | 2 | 3 |
