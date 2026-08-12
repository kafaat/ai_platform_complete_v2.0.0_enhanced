# Capability Mapping — Raw Scanner Candidates (NOT authoritative)

> Raw static repository scan only. `mapped` here means the scanner found specific
> implementation-dimension evidence (backend/routes/db/events/web/mobile/tests) — an honest
> LOWER BOUND. The AUTHORITATIVE mapped/unmapped state is the management matrix
> (`docs/capability-registry/generated/management/coverage_dashboard.json`), which also
> credits registry-declared on-disk evidence this scanner cannot attribute. `governance` and
> `other_evidence` are reported but never promote a capability. This report does not assert
> runtime verification or production certification.

- Capabilities: **81**
- Mapped: **74**
- Unmapped: **7**
- Multi-dimensional mappings: **48**
- Files scanned: **4984**
- Ambiguous artifacts queued: **405**
- Unmapped artifacts queued: **2028**

## Capability coverage

| ID | Domain | Backend | Routes | DB | Events | Web | Mobile | Tests | Dimensions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DEC-001 | decision | 0 | 0 | 0 | 3 | 0 | 0 | 2 | 2 |
| DEC-002 | decision | 1 | 0 | 0 | 2 | 0 | 0 | 4 | 3 |
| DEC-003 | decision | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| DEC-004 | decision | 9 | 20 | 26 | 30 | 0 | 0 | 15 | 5 |
| DEC-005 | decision | 5 | 86 | 5 | 3 | 0 | 0 | 3 | 5 |
| DEC-006 | decision | 2 | 0 | 0 | 8 | 0 | 0 | 3 | 3 |
| DEC-007 | decision | 3 | 6 | 4 | 3 | 1 | 0 | 2 | 6 |
| DEC-008 | decision | 5 | 94 | 14 | 4 | 0 | 0 | 1 | 5 |
| DEC-009 | decision | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| DEC-010 | decision | 4 | 89 | 42 | 7 | 0 | 0 | 5 | 5 |
| FM-001 | farm_management | 15 | 2 | 20 | 4 | 1 | 0 | 23 | 6 |
| FM-002 | farm_management | 34 | 44 | 98 | 22 | 14 | 2 | 25 | 7 |
| FM-003 | farm_management | 13 | 56 | 5 | 54 | 2 | 2 | 11 | 7 |
| FM-004 | farm_management | 30 | 82 | 82 | 54 | 12 | 1 | 34 | 7 |
| FM-005 | farm_management | 6 | 0 | 0 | 7 | 3 | 1 | 5 | 5 |
| FM-006 | farm_management | 2 | 3 | 0 | 0 | 2 | 0 | 1 | 4 |
| FM-007 | farm_management | 8 | 24 | 10 | 1 | 1 | 1 | 5 | 7 |
| FM-008 | farm_management | 10 | 24 | 5 | 1 | 0 | 0 | 7 | 5 |
| GIS-001 | gis | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 2 |
| GIS-002 | gis | 2 | 3 | 0 | 0 | 2 | 0 | 2 | 4 |
| GIS-003 | gis | 22 | 100 | 10 | 51 | 12 | 0 | 36 | 6 |
| GIS-004 | gis | 1 | 0 | 1 | 0 | 0 | 0 | 1 | 3 |
| INT-001 | farm_management | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| INT-002 | farm_management | 6 | 15 | 2 | 66 | 0 | 0 | 8 | 5 |
| INT-003 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| INT-004 | precision | 4 | 9 | 8 | 13 | 0 | 0 | 3 | 5 |
| IRR-001 | irrigation | 0 | 0 | 8 | 0 | 0 | 0 | 1 | 2 |
| IRR-002 | irrigation | 2 | 6 | 8 | 1 | 0 | 0 | 0 | 4 |
| IRR-003 | irrigation | 1 | 0 | 4 | 0 | 0 | 0 | 1 | 3 |
| IRR-004 | irrigation | 9 | 2 | 3 | 3 | 2 | 0 | 7 | 6 |
| IRR-005 | irrigation | 3 | 2 | 0 | 9 | 3 | 0 | 8 | 5 |
| IRR-006 | irrigation | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 2 |
| IRR-007 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| IRR-008 | irrigation | 0 | 0 | 17 | 0 | 0 | 0 | 0 | 1 |
| IRR-009 | irrigation | 8 | 1 | 7 | 9 | 1 | 0 | 10 | 6 |
| IRR-010 | irrigation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-001 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-002 | operations | 3 | 7 | 6 | 1 | 1 | 0 | 4 | 6 |
| OPS-003 | operations | 9 | 7 | 7 | 45 | 22 | 1 | 19 | 7 |
| OPS-004 | operations | 3 | 12 | 14 | 10 | 0 | 12 | 21 | 6 |
| OPS-005 | operations | 2 | 2 | 9 | 6 | 1 | 0 | 1 | 6 |
| OPS-006 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OPS-007 | operations | 0 | 0 | 3 | 1 | 0 | 0 | 2 | 3 |
| OPS-008 | operations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| PA-001 | precision | 9 | 33 | 8 | 1 | 0 | 0 | 7 | 5 |
| PA-002 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| PA-003 | precision | 3 | 3 | 9 | 2 | 0 | 0 | 3 | 5 |
| PA-004 | precision | 1 | 0 | 18 | 2 | 0 | 0 | 1 | 4 |
| PA-005 | precision | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| SAT-001 | satellite | 36 | 65 | 3 | 32 | 5 | 0 | 42 | 6 |
| SAT-002 | satellite | 1 | 1 | 0 | 1 | 0 | 0 | 3 | 4 |
| SAT-003 | satellite | 100 | 83 | 44 | 100 | 49 | 6 | 100 | 7 |
| SAT-004 | satellite | 20 | 10 | 5 | 14 | 7 | 0 | 21 | 6 |
| SAT-005 | satellite | 8 | 24 | 0 | 1 | 0 | 0 | 9 | 4 |
| SAT-006 | satellite | 1 | 0 | 0 | 1 | 0 | 0 | 3 | 3 |
| SAT-007 | satellite | 2 | 1 | 0 | 0 | 0 | 0 | 3 | 3 |
| SAT-008 | satellite | 3 | 1 | 7 | 4 | 0 | 0 | 5 | 5 |
| SAT-009 | satellite | 12 | 68 | 0 | 12 | 1 | 0 | 21 | 5 |
| SEC-001 | security | 14 | 36 | 100 | 86 | 0 | 0 | 58 | 5 |
| SEC-002 | security | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
| SEC-003 | security | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 2 |
| SEC-004 | security | 7 | 21 | 23 | 4 | 5 | 4 | 16 | 7 |
| SEC-005 | security | 0 | 0 | 4 | 0 | 0 | 0 | 1 | 2 |
| SEC-006 | security | 2 | 7 | 0 | 1 | 0 | 0 | 8 | 4 |
| SEC-007 | security | 2 | 0 | 7 | 47 | 0 | 0 | 9 | 4 |
| SEC-008 | security | 0 | 0 | 0 | 1 | 0 | 0 | 6 | 2 |
| SOIL-001 | soil | 13 | 91 | 14 | 36 | 1 | 0 | 16 | 6 |
| SOIL-002 | soil | 14 | 35 | 9 | 6 | 5 | 0 | 11 | 6 |
| SOIL-003 | soil | 1 | 0 | 15 | 0 | 0 | 0 | 0 | 2 |
| SOIL-004 | soil | 1 | 0 | 7 | 3 | 0 | 0 | 1 | 4 |
| SOIL-005 | soil | 5 | 0 | 0 | 2 | 0 | 0 | 2 | 3 |
| WX-001 | weather | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| WX-002 | weather | 22 | 51 | 8 | 56 | 9 | 0 | 21 | 6 |
| WX-003 | weather | 4 | 6 | 4 | 0 | 0 | 0 | 4 | 4 |
| WX-004 | weather | 59 | 53 | 0 | 78 | 19 | 0 | 57 | 5 |
| WX-005 | weather | 8 | 29 | 0 | 6 | 2 | 0 | 6 | 5 |
| WX-006 | weather | 84 | 26 | 35 | 26 | 16 | 0 | 44 | 6 |
| WX-007 | weather | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| WX-008 | weather | 2 | 6 | 0 | 1 | 0 | 0 | 2 | 4 |
| WX-009 | weather | 2 | 29 | 0 | 0 | 2 | 0 | 1 | 4 |
| WX-010 | weather | 1 | 0 | 0 | 2 | 0 | 0 | 1 | 3 |
