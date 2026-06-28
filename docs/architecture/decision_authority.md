# Decision Authority Matrix — SAHOOL

| Source / Layer | Produces | Must Not Produce | Enters |
|---|---|---|---|
| Weather | Signal | Recommendation / Prescription | Canonical Field State |
| Satellite / NDVI | Indication | Prescription | Evidence → Field State |
| Lab EC/pH/SAR | Evidence / Governing Signal | Direct decision | Evidence → Field State |
| RAG | Knowledge Annotation | Advice / Recommendation | Coordinator annotations only |
| Knowledge Graph | Reference Relation | Rule / Prescription | Coordinator annotations only |
| MCP Tools | Observation / Signal / Annotation | Task / Prescription / Decision | Field Context Coordinator |
| Field Context Coordinator | Context Bundle | Recommendation | Decision Firewall |
| Canonical Field State | Canonical State | UI command | Recommendation Engine |
| Recommendation Engine | FarmerView / BackendDetail | Task execution | Human Review / Prescription Engine |
| Human Review | Approved/Rejected recommendation | Raw field state mutation | Publication workflow |
| Prescription Engine | Prescription artifact from approved recommendation | Agronomic decision | Task/Export layer |

Non-negotiable rule: RAG, KG, MCP and UI artifacts are reference/context layers. The only decision path is Canonical Field State → Recommendation Engine → Human Review.
