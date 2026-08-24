# SAHOOL Static Event/NATS Contract Report

## Scope

Conservative static inventory of literal NATS/JetStream subjects. Dynamic subjects are listed but are not used to declare missing producers or consumers.

## Summary

| Metric | Value |
|---|---:|
| Python files scanned | 1178 |
| Resolved literal contracts | 2 |
| Dynamic contracts | 16 |
| Unique literal subjects | 2 |
| Matched subjects | 0 |
| Producer-only subjects | 1 |
| Consumer-only subjects | 1 |
| Cross-component duplicate durables | 0 |
| Runtime verified | No |
| Production certified | No |

## Review boundary

Producer-only and consumer-only entries are review candidates, not automatic defects. They can represent external integrations, future consumers, generic publishers, or dynamic subject construction.
