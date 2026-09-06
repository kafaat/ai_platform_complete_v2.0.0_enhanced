# Capability Mapping — Raw Scanner Candidates (NOT authoritative)

> Raw static repository scan only. `mapped` here means the scanner found specific
> implementation-dimension evidence (backend/routes/db/events/web/mobile/tests) — an honest
> LOWER BOUND. The AUTHORITATIVE mapped/unmapped state is the management matrix
> (`docs/capability-registry/generated/management/coverage_dashboard.json`), which also
> credits registry-declared on-disk evidence this scanner cannot attribute. `governance` and
> `other_evidence` are reported but never promote a capability. This report does not assert
> runtime verification or production certification.

- Capabilities: **81**
- Mapped: **76**
- Unmapped: **5**
- Multi-dimensional mappings: **49**
- Files scanned: **5263**
- Ambiguous artifacts queued: **418**
- Unmapped artifacts queued: **2148**

## Capability coverage

| ID | Domain | Backend | Routes | DB | Events | Web | Mobile | Tests | Dimensions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DEC-001 | decision | 3 | 0 | 0 | 5 | 0 | 0 | 3 | 3 |
| DEC-002 | decision | 1 | 0 | 0 | 2 | 0 | 0 | 4 | 3 |
| DEC-003 | decision | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| DEC-004 | decision | 9 | 20 | 24 | 30 | 0 | 0 | 15 | 5 |
| DEC-005 | decision | 5 | 86 | 5 | 3 | 0 | 0 | 3 | 5 |
| DEC-006 | decision | 2 | 0 | 0 | 8 | 0 | 0 | 3 | 3 |
| DEC-007 | decision | 3 | 8 | 4 | 3 | 1 | 0 | 4 | 6 |
| DEC-008 | decision | 5 | 94 | 14 | 4 | 0 | 0 | 2 | 5 |
| DEC-009 | decision | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| DEC-010 | decision | 4 | 89 | 49 | 7 | 0 | 0 | 5 | 5 |
| FM-001 | farm_management | 15 | 2 | 20 | 6 | 1 | 0 | 27 | 6 |
| FM-002 | farm_management | 33 | 44 | 98 | 22 | 14 | 2 | 25 | 7 |
| FM-003 | farm_management | 13 | 56 | 5 | 61 | 2 | 2 | 12 | 7 |
| FM-004 | farm_management | 30 | 82 | 84 | 58 | 13 | 1 | 34 | 7 |
| FM-005 | farm_management | 6 | 0 | 0 | 7 | 3 | 1 | 7 | 5 |
| FM-006 | farm_management | 2 | 3 | 0 | 0 | 2 | 0 | 1 | 4 |
| FM-007 | farm_management | 8 | 25 | 8 | 1 | 1 | 1 | 5 | 7 |
| FM-008 | farm_management | 10 | 24 | 5 | 1 | 0 | 0 | 7 | 5 |
| GIS-001 | gis | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |
| GIS-002 | gis | 2 | 3 | 0 | 0 | 2 | 0 | 2 | 4 |
| GIS-003 | gis | 27 | 100 | 10 | 51 | 12 | 0 | 38 | 6 |
| GIS-004 | gis | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 3 |
| INT-001 | farm_management | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| INT-002 | farm_management | 6 | 15 | 2 | 67 | 0 | 0 | 9 | 5 |
| INT-003 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| INT-004 | precision | 5 | 9 | 8 | 11 | 0 | 0 | 3 | 5 |
| IRR-001 | irrigation | 0 | 0 | 8 | 0 | 0 | 0 | 1 | 2 |
| IRR-002 | irrigation | 2 | 6 | 8 | 1 | 0 | 0 | 0 | 4 |
| IRR-003 | irrigation | 1 | 0 | 4 | 0 | 0 | 0 | 1 | 3 |
| IRR-004 | irrigation | 9 | 2 | 3 | 3 | 2 | 0 | 7 | 6 |
| IRR-005 | irrigation | 3 | 2 | 0 | 12 | 3 | 0 | 8 | 5 |
| IRR-006 | irrigation | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 2 |
| IRR-007 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-008 | irrigation | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 1 |
| IRR-009 | irrigation | 8 | 1 | 7 | 9 | 1 | 0 | 10 | 6 |
| IRR-010 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-001 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-002 | operations | 3 | 7 | 6 | 1 | 1 | 0 | 4 | 6 |
| OPS-003 | operations | 9 | 7 | 7 | 45 | 22 | 1 | 19 | 7 |
| OPS-004 | operations | 3 | 12 | 14 | 9 | 0 | 12 | 21 | 6 |
| OPS-005 | operations | 2 | 2 | 9 | 6 | 1 | 0 | 1 | 6 |
| OPS-006 | operations | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| OPS-007 | operations | 0 | 0 | 3 | 1 | 0 | 0 | 2 | 3 |
| OPS-008 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PA-001 | precision | 9 | 33 | 8 | 1 | 0 | 0 | 7 | 5 |
| PA-002 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| PA-003 | precision | 4 | 4 | 9 | 2 | 0 | 0 | 4 | 5 |
| PA-004 | precision | 1 | 0 | 18 | 2 | 0 | 0 | 1 | 4 |
| PA-005 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| SAT-001 | satellite | 35 | 65 | 3 | 32 | 5 | 0 | 44 | 6 |
| SAT-002 | satellite | 1 | 1 | 0 | 1 | 0 | 0 | 3 | 4 |
| SAT-003 | satellite | 100 | 87 | 42 | 100 | 49 | 6 | 100 | 7 |
| SAT-004 | satellite | 20 | 10 | 5 | 15 | 7 | 0 | 21 | 6 |
| SAT-005 | satellite | 8 | 24 | 0 | 1 | 0 | 0 | 9 | 4 |
| SAT-006 | satellite | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 3 |
| SAT-007 | satellite | 2 | 1 | 0 | 0 | 0 | 0 | 3 | 3 |
| SAT-008 | satellite | 3 | 1 | 7 | 4 | 0 | 0 | 6 | 5 |
| SAT-009 | satellite | 12 | 68 | 0 | 12 | 1 | 0 | 22 | 5 |
| SEC-001 | security | 13 | 29 | 100 | 46 | 0 | 0 | 64 | 5 |
| SEC-002 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-003 | security | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| SEC-004 | security | 7 | 22 | 23 | 5 | 5 | 4 | 18 | 7 |
| SEC-005 | security | 0 | 0 | 4 | 0 | 0 | 0 | 1 | 2 |
| SEC-006 | security | 2 | 7 | 0 | 1 | 0 | 0 | 8 | 4 |
| SEC-007 | security | 2 | 0 | 7 | 52 | 0 | 0 | 10 | 4 |
| SEC-008 | security | 0 | 0 | 0 | 1 | 0 | 0 | 6 | 2 |
| SOIL-001 | soil | 13 | 92 | 14 | 36 | 1 | 0 | 17 | 6 |
| SOIL-002 | soil | 14 | 35 | 9 | 6 | 5 | 0 | 11 | 6 |
| SOIL-003 | soil | 1 | 0 | 15 | 0 | 0 | 0 | 0 | 2 |
| SOIL-004 | soil | 1 | 0 | 7 | 3 | 0 | 0 | 1 | 4 |
| SOIL-005 | soil | 5 | 0 | 0 | 2 | 0 | 0 | 2 | 3 |
| WX-001 | weather | 1 | 4 | 0 | 3 | 0 | 0 | 2 | 4 |
| WX-002 | weather | 23 | 62 | 8 | 56 | 9 | 0 | 23 | 6 |
| WX-003 | weather | 4 | 6 | 4 | 0 | 0 | 0 | 4 | 4 |
| WX-004 | weather | 59 | 48 | 0 | 82 | 19 | 0 | 60 | 5 |
| WX-005 | weather | 9 | 29 | 0 | 6 | 2 | 0 | 6 | 5 |
| WX-006 | weather | 84 | 26 | 33 | 28 | 17 | 0 | 46 | 6 |
| WX-007 | weather | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| WX-008 | weather | 2 | 6 | 0 | 1 | 0 | 0 | 2 | 4 |
| WX-009 | weather | 2 | 29 | 0 | 0 | 2 | 0 | 1 | 4 |
| WX-010 | weather | 1 | 0 | 0 | 2 | 0 | 0 | 1 | 3 |
