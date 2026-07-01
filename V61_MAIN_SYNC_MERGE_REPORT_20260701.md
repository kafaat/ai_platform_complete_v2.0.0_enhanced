# V61 Main-Synced Merge Report — 2026-07-01

## Input
- Base uploaded from main: `sahool_v9.1.0_b08207a_full.zip`
- Feature source: `sahool_rc16_d5b1918_v61_soil_sampling_planner.zip`

## Merge Strategy
This package uses the uploaded main-synced file as the base, then reapplies the verified V58–V61 agent features without overwriting unrelated main changes.

Preserved from main:
- `/api/ai-agronomist/approvals/approve`
- `/api/ai-agronomist/approvals/deny`
- Existing actionable Chatbot approval UI that calls the approval endpoints
- Existing V63–V66 runtime/behavioral tests and files

Reapplied from V58–V61:
- Provider-native multi-round tool calling
- Provider tool audit fields: input_hash, result_summary, provider/model
- Field Boundary AI tools and panel
- Productivity Zones tools and panel
- Soil Sampling Planner tools and panel
- Capabilities and tool registry/schema updates

## Validation
Python targeted V55–V61 Harness tests:
- 33 passed

Python main continuity tests V63/V65/V66:
- 173 passed

Frontend static guards:
- 5 files passed
- 10 tests passed

## Notes
- No automatic boundary, productivity-zone, or soil-sampling writes are performed by chat.
- Mutating tools remain high-risk and require human approval.
- The merged package keeps main as the authority and adds V58–V61 capabilities on top.
