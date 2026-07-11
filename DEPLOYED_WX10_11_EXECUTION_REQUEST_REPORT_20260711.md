# WX-10.11a — Authorized Dispatch to Execution Request Boundary

Implemented an authoritative, idempotent execution-request envelope for `task` or `equipment` targets. The Decision-Service verifies the dispatch authorization, approved decision, and planned execution plan in one transaction, inserts one queued request and one `EXECUTION_REQUEST_CREATED` outbox row, and fails closed outside SoR mode.

This increment intentionally does **not** publish MQTT or call a task/equipment provider directly. Physical delivery and adapter receipt processing remain WX-10.11b, preserving a reviewable safety boundary.
