# SAHOOL Capability Traceability Report

Generated from the canonical capability registry. Links are repository evidence, not runtime certification.

## Coverage

- Capabilities: **81**
- Service linked: **73**
- API linked: **62**
- Test linked: **67**
- UI linked: **5**
- Mobile linked: **12**
- Owner assigned: **73**
- Fully traceable across all six surfaces: **3**

## Lowest traceability capabilities

| ID | Capability | Score | Missing surfaces |
|---|---|---:|---|
| INT-004 | External machinery integrations | 0 | service,api,test,ui,mobile,owner |
| PA-003 | Yield map ingestion | 0 | service,api,test,ui,mobile,owner |
| PA-004 | As-applied data | 17 | service,api,ui,mobile,owner |
| FM-005 | Crop and cultivar catalog | 33 | service,ui,mobile,owner |
| FM-006 | Farm economics | 33 | service,ui,mobile,owner |
| IRR-008 | Execution verification | 33 | api,test,ui,mobile |
| PA-005 | Machine telemetry | 33 | service,ui,mobile,owner |
| SAT-004 | NDMI | 33 | api,test,ui,mobile |
| WX-007 | Frost and heat risk | 33 | api,test,ui,mobile |
| FM-007 | Inventory and procurement | 50 | service,ui,owner |
| INT-001 | Public API and SDK | 50 | test,ui,mobile |
| INT-002 | Event bus integration | 50 | api,ui,mobile |
| IRR-001 | Water source registry | 50 | api,ui,mobile |
| IRR-002 | Water quality samples | 50 | test,ui,mobile |
| IRR-003 | Field water-source binding | 50 | api,ui,mobile |
| IRR-010 | Leaching and drainage safety | 50 | test,ui,mobile |
| OPS-005 | Offline mobile | 50 | service,ui,owner |
| OPS-007 | Maintenance | 50 | test,ui,mobile |
| OPS-008 | Workforce and worker identity | 50 | api,ui,mobile |
| SAT-002 | True color imagery | 50 | api,ui,mobile |

## Interpretation

A missing UI or mobile link is not automatically a defect: some capabilities are intentionally backend-only. Production maturity remains unchanged until runtime metrics, traces, receipts and audit evidence are supplied.
