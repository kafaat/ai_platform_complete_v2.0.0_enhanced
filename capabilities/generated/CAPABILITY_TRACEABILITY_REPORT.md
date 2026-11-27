# SAHOOL Capability Traceability Report

Generated from the field-authority-resolved capability view. Canonical definition fields come from Registry v1; repository links remain projections and are not runtime certification.

## Coverage

- Capabilities: **81**
- Service linked: **73**
- API linked: **63**
- Test linked: **71**
- UI linked: **14**
- Mobile linked: **23**
- Owner assigned: **74**
- Fully traceable across all six surfaces: **8**

## Lowest traceability capabilities

| ID | Capability | Score | Missing surfaces |
|---|---|---:|---|
| INT-004 | External machinery integrations | 17 | service,api,test,ui,mobile |
| PA-004 | As-applied data | 17 | service,api,ui,mobile,owner |
| IRR-008 | Execution verification | 33 | api,test,ui,mobile |
| PA-003 | Yield map ingestion | 33 | service,ui,mobile,owner |
| PA-005 | Machine telemetry | 33 | service,ui,mobile,owner |
| SAT-004 | NDMI | 33 | api,test,ui,mobile |
| WX-007 | Frost and heat risk | 33 | api,test,ui,mobile |
| FM-005 | Crop and cultivar catalog | 50 | service,ui,owner |
| FM-006 | Farm economics | 50 | service,mobile,owner |
| FM-007 | Inventory and procurement | 50 | service,ui,owner |
| INT-002 | Event bus integration | 50 | api,ui,mobile |
| IRR-001 | Water source registry | 50 | api,ui,mobile |
| IRR-003 | Field water-source binding | 50 | api,ui,mobile |
| OPS-005 | Offline mobile | 50 | service,ui,owner |
| OPS-007 | Maintenance | 50 | test,ui,mobile |
| OPS-008 | Workforce and worker identity | 50 | api,ui,mobile |
| SAT-002 | True color imagery | 50 | api,ui,mobile |
| SEC-001 | Tenant RLS | 50 | api,ui,mobile |
| SEC-002 | Signed tenant assertion | 50 | api,ui,mobile |
| SEC-003 | Worker identity binding | 50 | api,ui,mobile |

## Interpretation

A missing UI or mobile link is not automatically a defect: some capabilities are intentionally backend-only. Production maturity remains unchanged until runtime metrics, traces, receipts and audit evidence are supplied.
