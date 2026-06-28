
# Executed Architectural Integration Patch

## Mandatory integrations

### 1. Single Source of Truth
Replace any local state builders with:

compose_field_state(signals, observations, indications)

Coordinator must consume CanonicalFieldState only.

### 2. Guardrail Hook
Insert:

User -> Intent -> MCP Tools -> CanonicalFieldState
-> Ponytail -> RecommendationEngine -> HumanReview

### 3. Recommendation Authority

Only RecommendationEngine may emit:
- recommendation
- prescription
- task
- dose

### 4. Persistence

Move:
- ReviewWorkflow
- FeedbackMetrics

from in-memory collections to PostgreSQL tables.

### 5. Remove duplicated orchestration

Delete/merge:
- local snapshot builders
- parallel orchestrators
- duplicated coordinator pipelines
