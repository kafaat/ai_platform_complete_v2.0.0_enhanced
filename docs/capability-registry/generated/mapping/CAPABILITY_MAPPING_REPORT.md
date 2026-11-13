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
- Multi-dimensional mappings: **42**
- Files scanned: **7166**
- Ambiguous artifacts queued: **234**
- Unmapped artifacts queued: **3410**

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
| DEC-010 | decision | 4 | 92 | 49 | 7 | 0 | 0 | 6 | 5 |
| FM-001 | farm_management | 16 | 2 | 28 | 12 | 1 | 0 | 40 | 6 |
| FM-002 | farm_management | 36 | 44 | 100 | 25 | 18 | 35 | 48 | 7 |
| FM-003 | farm_management | 13 | 56 | 5 | 65 | 3 | 2 | 15 | 7 |
| FM-004 | farm_management | 31 | 82 | 80 | 41 | 15 | 15 | 48 | 7 |
| FM-005 | farm_management | 9 | 0 | 0 | 6 | 3 | 1 | 7 | 5 |
| FM-006 | farm_management | 1 | 0 | 0 | 0 | 2 | 0 | 1 | 3 |
| FM-007 | farm_management | 8 | 19 | 8 | 0 | 1 | 4 | 6 | 6 |
| FM-008 | farm_management | 10 | 31 | 5 | 2 | 0 | 0 | 11 | 5 |
| GIS-001 | gis | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |
| GIS-002 | gis | 2 | 4 | 0 | 0 | 4 | 0 | 2 | 4 |
| GIS-003 | gis | 32 | 100 | 14 | 67 | 12 | 4 | 41 | 7 |
| GIS-004 | gis | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 3 |
| INT-001 | farm_management | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| INT-002 | farm_management | 7 | 15 | 2 | 100 | 0 | 0 | 21 | 5 |
| INT-003 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 1 |
| INT-004 | precision | 5 | 9 | 8 | 11 | 0 | 0 | 3 | 5 |
| IRR-001 | irrigation | 0 | 0 | 8 | 0 | 0 | 0 | 1 | 2 |
| IRR-002 | irrigation | 1 | 6 | 8 | 1 | 0 | 0 | 1 | 5 |
| IRR-003 | irrigation | 1 | 0 | 4 | 0 | 0 | 0 | 2 | 3 |
| IRR-004 | irrigation | 3 | 1 | 0 | 0 | 0 | 0 | 2 | 3 |
| IRR-005 | irrigation | 2 | 2 | 0 | 7 | 0 | 0 | 5 | 4 |
| IRR-006 | irrigation | 0 | 0 | 0 | 4 | 0 | 0 | 4 | 2 |
| IRR-007 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-008 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-009 | irrigation | 8 | 1 | 7 | 9 | 1 | 0 | 11 | 6 |
| IRR-010 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-001 | operations | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 |
| OPS-002 | operations | 3 | 7 | 6 | 3 | 1 | 0 | 7 | 6 |
| OPS-003 | operations | 3 | 2 | 4 | 7 | 6 | 16 | 11 | 7 |
| OPS-004 | operations | 3 | 12 | 14 | 12 | 0 | 21 | 28 | 6 |
| OPS-005 | operations | 2 | 2 | 9 | 14 | 1 | 13 | 11 | 7 |
| OPS-006 | operations | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| OPS-007 | operations | 0 | 0 | 3 | 0 | 0 | 1 | 0 | 2 |
| OPS-008 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PA-001 | precision | 10 | 34 | 8 | 2 | 1 | 0 | 10 | 6 |
| PA-002 | precision | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| PA-003 | precision | 3 | 4 | 9 | 1 | 0 | 0 | 4 | 5 |
| PA-004 | precision | 1 | 0 | 18 | 2 | 0 | 0 | 1 | 4 |
| PA-005 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| SAT-001 | satellite | 42 | 100 | 5 | 43 | 6 | 0 | 58 | 6 |
| SAT-002 | satellite | 0 | 1 | 0 | 1 | 1 | 0 | 5 | 4 |
| SAT-003 | satellite | 59 | 43 | 6 | 97 | 38 | 5 | 65 | 7 |
| SAT-004 | satellite | 9 | 4 | 5 | 13 | 3 | 0 | 8 | 6 |
| SAT-005 | satellite | 6 | 6 | 0 | 1 | 0 | 0 | 14 | 4 |
| SAT-006 | satellite | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 3 |
| SAT-007 | satellite | 1 | 1 | 0 | 0 | 0 | 0 | 3 | 3 |
| SAT-008 | satellite | 3 | 1 | 7 | 4 | 0 | 0 | 6 | 5 |
| SAT-009 | satellite | 12 | 52 | 0 | 15 | 2 | 1 | 28 | 6 |
| SEC-001 | security | 12 | 16 | 100 | 73 | 0 | 0 | 83 | 5 |
| SEC-002 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-003 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-004 | security | 5 | 9 | 19 | 1 | 3 | 4 | 10 | 7 |
| SEC-005 | security | 0 | 0 | 4 | 0 | 0 | 0 | 3 | 2 |
| SEC-006 | security | 3 | 85 | 0 | 3 | 0 | 0 | 11 | 4 |
| SEC-007 | security | 3 | 73 | 7 | 47 | 0 | 0 | 9 | 5 |
| SEC-008 | security | 0 | 0 | 4 | 2 | 0 | 0 | 9 | 3 |
| SOIL-001 | soil | 6 | 2 | 14 | 22 | 0 | 0 | 5 | 5 |
| SOIL-002 | soil | 10 | 30 | 6 | 7 | 2 | 0 | 4 | 6 |
| SOIL-003 | soil | 1 | 0 | 15 | 0 | 0 | 1 | 0 | 3 |
| SOIL-004 | soil | 1 | 0 | 7 | 3 | 0 | 0 | 0 | 3 |
| SOIL-005 | soil | 7 | 0 | 0 | 7 | 0 | 0 | 0 | 2 |
| WX-001 | weather | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| WX-002 | weather | 13 | 21 | 6 | 31 | 7 | 1 | 13 | 7 |
| WX-003 | weather | 2 | 6 | 4 | 0 | 0 | 0 | 0 | 3 |
| WX-004 | weather | 3 | 0 | 0 | 1 | 0 | 0 | 9 | 3 |
| WX-005 | weather | 3 | 0 | 0 | 1 | 0 | 0 | 2 | 3 |
| WX-006 | weather | 6 | 1 | 0 | 1 | 0 | 0 | 10 | 4 |
| WX-007 | weather | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| WX-008 | weather | 3 | 6 | 0 | 5 | 0 | 1 | 2 | 5 |
| WX-009 | weather | 1 | 29 | 0 | 0 | 2 | 0 | 2 | 4 |
| WX-010 | weather | 1 | 0 | 0 | 2 | 0 | 0 | 2 | 3 |
