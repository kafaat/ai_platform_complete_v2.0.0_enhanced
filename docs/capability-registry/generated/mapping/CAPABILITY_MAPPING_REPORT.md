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
- Multi-dimensional mappings: **46**
- Files scanned: **7773**
- Ambiguous artifacts queued: **266**
- Unmapped artifacts queued: **3705**

## Capability coverage

| ID | Domain | Backend | Routes | DB | Events | Web | Mobile | Tests | Dimensions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DEC-001 | decision | 2 | 0 | 0 | 3 | 0 | 0 | 3 | 3 |
| DEC-002 | decision | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| DEC-003 | decision | 3 | 0 | 0 | 0 | 0 | 0 | 3 | 2 |
| DEC-004 | decision | 6 | 5 | 16 | 5 | 0 | 0 | 10 | 5 |
| DEC-005 | decision | 0 | 0 | 10 | 1 | 0 | 0 | 3 | 3 |
| DEC-006 | decision | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| DEC-007 | decision | 4 | 8 | 4 | 3 | 1 | 0 | 5 | 6 |
| DEC-008 | decision | 0 | 1 | 2 | 1 | 0 | 0 | 1 | 4 |
| DEC-009 | decision | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| DEC-010 | decision | 4 | 93 | 59 | 8 | 0 | 0 | 9 | 5 |
| FM-001 | farm_management | 17 | 2 | 30 | 12 | 1 | 0 | 49 | 6 |
| FM-002 | farm_management | 39 | 44 | 100 | 30 | 20 | 35 | 67 | 7 |
| FM-003 | farm_management | 15 | 56 | 5 | 62 | 3 | 2 | 18 | 7 |
| FM-004 | farm_management | 34 | 82 | 68 | 51 | 20 | 15 | 63 | 7 |
| FM-005 | farm_management | 13 | 0 | 0 | 15 | 6 | 1 | 8 | 5 |
| FM-006 | farm_management | 1 | 0 | 0 | 0 | 2 | 0 | 1 | 3 |
| FM-007 | farm_management | 8 | 19 | 8 | 0 | 1 | 4 | 7 | 6 |
| FM-008 | farm_management | 10 | 31 | 5 | 2 | 0 | 0 | 11 | 5 |
| GIS-001 | gis | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |
| GIS-002 | gis | 2 | 4 | 0 | 0 | 4 | 0 | 2 | 4 |
| GIS-003 | gis | 33 | 100 | 11 | 69 | 13 | 4 | 43 | 7 |
| GIS-004 | gis | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 3 |
| INT-001 | farm_management | 0 | 3 | 0 | 0 | 0 | 0 | 1 | 2 |
| INT-002 | farm_management | 8 | 19 | 2 | 100 | 0 | 0 | 24 | 5 |
| INT-003 | irrigation | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 2 |
| INT-004 | precision | 5 | 9 | 8 | 12 | 0 | 0 | 3 | 5 |
| IRR-001 | irrigation | 0 | 0 | 8 | 0 | 0 | 0 | 1 | 2 |
| IRR-002 | irrigation | 1 | 6 | 8 | 3 | 0 | 0 | 3 | 5 |
| IRR-003 | irrigation | 1 | 0 | 4 | 0 | 0 | 0 | 3 | 3 |
| IRR-004 | irrigation | 3 | 1 | 0 | 0 | 0 | 0 | 2 | 3 |
| IRR-005 | irrigation | 2 | 2 | 0 | 7 | 0 | 0 | 5 | 4 |
| IRR-006 | irrigation | 0 | 0 | 0 | 4 | 0 | 0 | 5 | 2 |
| IRR-007 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-008 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-009 | irrigation | 9 | 1 | 7 | 8 | 2 | 0 | 14 | 6 |
| IRR-010 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-001 | operations | 0 | 0 | 20 | 9 | 0 | 1 | 4 | 4 |
| OPS-002 | operations | 4 | 9 | 6 | 4 | 1 | 0 | 8 | 6 |
| OPS-003 | operations | 10 | 28 | 48 | 19 | 6 | 18 | 24 | 7 |
| OPS-004 | operations | 3 | 12 | 14 | 12 | 0 | 21 | 28 | 6 |
| OPS-005 | operations | 2 | 2 | 9 | 14 | 1 | 13 | 12 | 7 |
| OPS-006 | operations | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| OPS-007 | operations | 0 | 0 | 3 | 0 | 0 | 1 | 1 | 3 |
| OPS-008 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PA-001 | precision | 9 | 34 | 8 | 2 | 1 | 0 | 11 | 6 |
| PA-002 | precision | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| PA-003 | precision | 4 | 4 | 12 | 1 | 0 | 0 | 5 | 5 |
| PA-004 | precision | 1 | 0 | 18 | 2 | 0 | 0 | 1 | 4 |
| PA-005 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| SAT-001 | satellite | 43 | 100 | 5 | 38 | 6 | 0 | 59 | 6 |
| SAT-002 | satellite | 0 | 1 | 0 | 1 | 1 | 0 | 5 | 4 |
| SAT-003 | satellite | 58 | 43 | 5 | 100 | 39 | 5 | 71 | 7 |
| SAT-004 | satellite | 9 | 4 | 5 | 13 | 3 | 0 | 8 | 6 |
| SAT-005 | satellite | 6 | 6 | 0 | 1 | 0 | 0 | 14 | 4 |
| SAT-006 | satellite | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 3 |
| SAT-007 | satellite | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 3 |
| SAT-008 | satellite | 3 | 1 | 7 | 4 | 0 | 0 | 6 | 5 |
| SAT-009 | satellite | 12 | 52 | 0 | 11 | 2 | 1 | 28 | 6 |
| SEC-001 | security | 16 | 19 | 100 | 62 | 0 | 0 | 93 | 5 |
| SEC-002 | security | 3 | 0 | 0 | 4 | 0 | 0 | 5 | 3 |
| SEC-003 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-004 | security | 6 | 9 | 19 | 1 | 5 | 5 | 15 | 7 |
| SEC-005 | security | 0 | 0 | 4 | 0 | 0 | 0 | 3 | 2 |
| SEC-006 | security | 3 | 88 | 0 | 3 | 0 | 0 | 13 | 4 |
| SEC-007 | security | 3 | 74 | 15 | 31 | 0 | 0 | 11 | 5 |
| SEC-008 | security | 0 | 0 | 4 | 3 | 0 | 0 | 10 | 3 |
| SOIL-001 | soil | 7 | 2 | 14 | 20 | 0 | 0 | 6 | 5 |
| SOIL-002 | soil | 13 | 32 | 14 | 13 | 3 | 1 | 10 | 7 |
| SOIL-003 | soil | 4 | 3 | 15 | 0 | 0 | 1 | 2 | 5 |
| SOIL-004 | soil | 3 | 6 | 7 | 3 | 0 | 0 | 0 | 4 |
| SOIL-005 | soil | 7 | 0 | 0 | 8 | 0 | 0 | 2 | 3 |
| WX-001 | weather | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| WX-002 | weather | 14 | 20 | 6 | 28 | 9 | 1 | 17 | 7 |
| WX-003 | weather | 2 | 6 | 4 | 0 | 0 | 0 | 1 | 4 |
| WX-004 | weather | 3 | 0 | 22 | 1 | 0 | 0 | 10 | 4 |
| WX-005 | weather | 3 | 0 | 0 | 1 | 0 | 0 | 4 | 3 |
| WX-006 | weather | 6 | 1 | 0 | 1 | 0 | 0 | 11 | 4 |
| WX-007 | weather | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| WX-008 | weather | 3 | 6 | 0 | 2 | 0 | 1 | 3 | 5 |
| WX-009 | weather | 1 | 29 | 0 | 0 | 2 | 0 | 2 | 4 |
| WX-010 | weather | 2 | 0 | 0 | 3 | 0 | 0 | 2 | 3 |
